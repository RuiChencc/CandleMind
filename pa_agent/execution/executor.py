# -*- coding: utf-8 -*-
"""executor.py — 执行层（Phase 2 收尾）：pending → guardrails → 现货测试网下单 → audit 回填。

默认 --dry-run（只读 pending + 护栏评估 + 打印订单参数，绝不下单）；
--live 才真实下单（测试网）。撤单用 DELETE（POST /api/v3/order 是下单语义，勿混）。
clientOrderId = signal_id：决策→audit→venue 完整闭环（2pa PA_CLIENT_ORDER_PREFIX 思想），
查单/撤单可用 origClientOrderId=signal_id，无需记忆 orderId。

符号白名单：pending 目录默认含 A 股记录（000001/600172 等），executor 只处理
WATCHLIST 内符号（币安），防跨市场误下单。A 股记录跳过并计数。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import json
import os
import re
import sys
import time

try:
    import msvcrt  # Windows 跨进程文件锁（audit_log.py:21-24 先例；状态文件并发写防护）
except ImportError:  # 非 Windows 降级为无锁
    msvcrt = None
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pa_agent.strategy.guardrails import evaluate_decision, scale_position
from pa_agent.execution.audit_log import AuditLog, _TERMINAL_SL, derive_signal_id

# 币安执行白名单（Phase 2 目标市场；A 股 pending 记录据此隔离）。
# 优先读 config/binance_watchlist.json（{"symbols": [...]}），不存在/格式错回退默认。
WATCHLIST_DEFAULT = ("XRPUSDT", "ADAUSDT")
# 信号年龄上限（2026-10-02 定制方案步骤2）：决策时间超过该秒数视为过期，拒单。
# 依据：手动/自动信号都应在决策后 1h 内执行，过期价格路径已不可信（验证层审查）。
MAX_SIGNAL_AGE_S = 3600
BASE = "https://testnet.binance.vision"   # 现货测试网
DEFAULT_PENDING = Path(__file__).resolve().parent.parent.parent / "records" / "pending"


def load_watchlist() -> tuple:
    """读 config/binance_watchlist.json 返回符号白名单；缺失/非法回退默认。"""
    cfg = Path(__file__).resolve().parent.parent.parent / "config" / "binance_watchlist.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        syms = data.get("symbols")
        if isinstance(syms, list) and all(isinstance(s, str) and s for s in syms):
            return tuple(syms)
    except (OSError, ValueError):
        pass
    return WATCHLIST_DEFAULT


WATCHLIST = load_watchlist()


class BinanceSpotExecutor:
    """现货测试网执行器（单次调用，非守护）。"""

    def __init__(self, api_key: str, secret: str, base: str = BASE) -> None:
        self._key = api_key
        self._secret = secret
        self._base = base

    # ---- 签名请求 ----
    def _server_time(self) -> int:
        with urllib.request.urlopen(
            urllib.request.Request(self._base + "/api/v3/time"), timeout=12
        ) as r:
            return int(json.loads(r.read().decode())["serverTime"])

    def _public_get(self, path: str, params: Optional[dict] = None) -> tuple:
        """无签名公开端点 GET（exchangeInfo/ticker 不接受 timestamp/signature → -1104）。

        _sl_probe.py 已证实例：签名参数会被公开端点拒绝（"Not all sent parameters
        were read"）→ 公开信息一律走本方法，签名只用于账户/下单/撤单/查单。
        """
        url = self._base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return 200, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:200]

    def _signed(self, path: str, params: dict, method: str = "GET"):
        p = dict(params); p["timestamp"] = self._server_time()
        qs = urllib.parse.urlencode(p)
        sig = hmac.new(self._secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
        url = self._base + path + "?" + qs + "&signature=" + sig
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": self._key}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return 200, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:200]

    # ---- 下单/查单/撤单 ----
    def place_limit(self, symbol: str, side: str, qty: str, price: str, client_order_id: str):
        return self._signed("/api/v3/order", {
            "symbol": symbol, "side": side, "type": "LIMIT",
            "quantity": qty, "price": price, "timeInForce": "GTC",
            "newClientOrderId": client_order_id,
        }, method="POST")

    def query_by_client_id(self, symbol: str, client_order_id: str):
        return self._signed("/api/v3/order", {
            "symbol": symbol, "origClientOrderId": client_order_id,
        })

    def cancel_by_client_id(self, symbol: str, client_order_id: str):
        # 撤单必须 DELETE（实测：POST 会被当"下单"请求，-1102 缺 side/type）
        return self._signed("/api/v3/order", {
            "symbol": symbol, "origClientOrderId": client_order_id,
        }, method="DELETE")

    def open_orders(self, symbol: str):
        return self._signed("/api/v3/openOrders", {"symbol": symbol})

    # ---- P0-1 止损三件套 ----
    def _tick_size(self, symbol: str) -> float:
        """从 exchangeInfo 取 tickSize（PRICE_FILTER），失败回退 0.0001。"""
        c, b = self._public_get("/api/v3/exchangeInfo", {"symbol": symbol})
        if c == 200 and isinstance(b, dict):
            try:
                filt = b["symbols"][0]["filters"]
                for f in filt:
                    if f.get("filterType") == "PRICE_FILTER":
                        return float(f["tickSize"])
            except (KeyError, IndexError, TypeError, ValueError):
                pass
        return 0.0001

    def market_price(self, symbol: str) -> Optional[float]:
        c, b = self._public_get("/api/v3/ticker/price", {"symbol": symbol})
        if c == 200 and isinstance(b, dict):
            try:
                return float(b.get("price"))
            except (TypeError, ValueError):
                return None
        return None

    def place_stop_loss_limit(self, symbol: str, side: str, qty: str, stop_price: float,
                              client_order_id: str) -> tuple:
        """P0-1/3 止损挂单：STOP_LOSS_LIMIT（现货唯一合法止损型）。

        price = stop_price * (1 - SLIPPAGE_FRAC)，SLIPPAGE_FRAC = max(0.002, 5*tick/stop_price)：
        0.2% 或 5 tick 取大（实测 4 种 price 取值交易所全接受，ε 只受成交质量约束；
        闪崩时 price 低于现价 → 触发后限价在下方仍大概率成交，不成交由 --check-sl 三态兜底）。
        SELL 侧（做多保护）：stop_price 须 < 市价（实测 -2010 反向拒绝）。
        """
        tick = self._tick_size(symbol)
        frac = max(0.002, 5 * tick / stop_price) if stop_price > 0 else 0.002
        px = stop_price * (1 - frac)
        px = round(px, self._price_precision(symbol))
        return self._signed("/api/v3/order", {
            "symbol": symbol, "side": side, "type": "STOP_LOSS_LIMIT",
            "quantity": qty, "stopPrice": f"{stop_price:.6f}".rstrip("0").rstrip("."),
            "price": f"{px:.6f}".rstrip("0").rstrip("."), "timeInForce": "GTC",
            "newClientOrderId": client_order_id,
        }, method="POST")

    def _price_precision(self, symbol: str) -> int:
        c, b = self._public_get("/api/v3/exchangeInfo", {"symbol": symbol})
        if c == 200 and isinstance(b, dict):
            try:
                for f in b["symbols"][0]["filters"]:
                    if f.get("filterType") == "PRICE_FILTER":
                        ts = f["tickSize"]
                        precision = max(0, len(ts.rstrip("0").split(".")[-1]))
                        return precision
            except (KeyError, IndexError, TypeError, ValueError):
                pass
        return 4

    def place_market(self, symbol: str, side: str, qty: str, client_order_id: str) -> tuple:
        """市价单（入场市价单 / 止损兜底市价平仓）。"""
        return self._signed("/api/v3/order", {
            "symbol": symbol, "side": side, "type": "MARKET",
            "quantity": qty, "newClientOrderId": client_order_id,
        }, method="POST")

    def query_order_by_client_id(self, symbol: str, client_order_id: str):
        """查单（GET /api/v3/order），fills 数组含成交明细。"""
        return self._signed("/api/v3/order", {
            "symbol": symbol, "origClientOrderId": client_order_id,
        })



# P0-20261002 fix-3（再修）：余额查询连续失败升级告警——状态机（firing/resolved）+ 跨进程持久化。
#   用户审查 P0：schtasks 每 5min 起新进程 → 进程内 dict 清零 → count 永远=1 → 告警永不触发。
#   状态落盘 records/execution_log/balance_alert_state.json，每次读→增→判→写（os.replace 原子写）。
_BALANCE_ALERT_STATE_PATH = Path(__file__).resolve().parent.parent.parent / "records" / "execution_log" / "balance_alert_state.json"
_BALANCE_ALERT_THRESHOLD = 6  # 用户 P1-3：5min×6=30min，币安偶发 5xx 不触发（15min 过敏感）
_BALANCE_ALERT_COOLDOWN_S = 6 * 3600


def _load_balance_alert_state() -> dict:
    """读状态文件（不存在/损坏 → 空 dict，不阻断主流程）。"""
    try:
        with open(_BALANCE_ALERT_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_balance_alert_state(state: dict) -> None:
    """写状态文件（temp + os.replace 原子写，防半写损坏）。"""
    try:
        os.makedirs(os.path.dirname(os.fspath(_BALANCE_ALERT_STATE_PATH)), exist_ok=True)
        tmp = Path(os.fspath(_BALANCE_ALERT_STATE_PATH)).with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _BALANCE_ALERT_STATE_PATH)
    except OSError as e:
        print(f"  [状态持久化失败] {e!r}")


def _locked_balance_alert(fn):
    """msvcrt 锁包住整段 read-modify-write（用户 P1-1：RunCycle 1h + SL_Watch 5min
    双进程并发 → 无锁会丢一次 count；os.replace 只防半写不防竞态）。

    锁文件 = 独立 <state>.lock（a+b 追加句柄常驻），状态文件每次整体 os.replace——
    若锁在状态文件自身句柄上，impl 内 replace 目标被自身句柄占用 → Windows PermissionError。"""
    def wrapper(sym, sid, *a):
        sp = Path(os.fspath(_BALANCE_ALERT_STATE_PATH))
        sp.parent.mkdir(parents=True, exist_ok=True)
        lock_path = sp.with_suffix(sp.suffix + ".lock")
        try:
            with open(lock_path, "a+b") as lf:
                if msvcrt is not None:
                    if lf.seek(0, 2) == 0:  # 空锁文件写 1 字节占位（msvcrt 锁空文件失败）
                        lf.write(b"\0")
                        lf.flush()
                    lf.seek(0)
                    msvcrt.locking(lf.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    return fn(sym, sid, *a)
                finally:
                    if msvcrt is not None:
                        lf.seek(0)
                        msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            return fn(sym, sid, *a)  # 锁失败降级：直接执行（不阻断主流程）
    return wrapper


def _prune_alert_state(st_all: dict) -> dict:
    """P2-20261002：清理不在 watchlist 的 symbol 残留（symbol 移出白名单后状态不再更新，长期累积）。"""
    try:
        wl = set(load_watchlist())
    except Exception:
        return st_all
    return {k: v for k, v in st_all.items() if k in wl}


def _balance_fail_bump_impl(sym: str, sid: str, code: int) -> bool:
    """余额查询失败累计（跨进程）：读→count+1→判阈值/冷却→触发升级告警→写。返回是否触发。"""
    st_all = _prune_alert_state(_load_balance_alert_state())
    st = st_all.setdefault(sym, {"firing": False, "last_sent_ts": 0.0, "count": 0})
    st["count"] += 1
    alerted = False
    if st["count"] >= _BALANCE_ALERT_THRESHOLD:
        now = time.time()
        if not st["firing"] or now - st["last_sent_ts"] >= _BALANCE_ALERT_COOLDOWN_S:
            _fire_balance_fail_escalation(sym, sid, st["count"], code)
            st["firing"] = True
            st["last_sent_ts"] = now
            alerted = True
    _save_balance_alert_state(st_all)
    return alerted


def _balance_alert_clear_impl(sym: str, sid: str) -> bool:
    """余额查询成功恢复：若 firing → 发「已恢复」通知 + 复位。返回是否发送。"""
    st_all = _prune_alert_state(_load_balance_alert_state())
    st = st_all.get(sym)
    if st and st["firing"]:
        _fire_balance_resolved_notice(sym, sid)
        st["firing"] = False
        st["count"] = 0
        _save_balance_alert_state(st_all)
        return True
    return False


_balance_fail_bump = _locked_balance_alert(_balance_fail_bump_impl)
_balance_alert_clear = _locked_balance_alert(_balance_alert_clear_impl)


def _fire_balance_fail_escalation(sym: str, sid: str, count: int, code: int) -> None:
    """余额查询连续失败 ≥阈值触发飞书告警（仅升级时调用，失败不阻断主流程）。"""
    try:
        from pa_agent.notify.feishu_notifier import _send_feishu_text_alert
    except Exception as e:
        print(f"  [告警发送失败] feishu_notifier 不可用: {e!r}")
        return
    try:
        text = (
            "PA Agent 余额查询持续失败升级告警\n"
            f"symbol: {sym}\n"
            f"signal_id: {sid}\n"
            f"累计失败: {count} 次 (阈值 {_BALANCE_ALERT_THRESHOLD})\n"
            f"最近 code: {code}\n"
            "该 symbol 持仓 row 可能长期裸露——请检查 API key / IP 白名单 / 网络。"
        )
        _send_feishu_text_alert(text, log_label="余额查询升级告警")
    except Exception as e:
        print(f"  [告警发送失败] {e!r}")


def _fire_balance_resolved_notice(sym: str, sid: str) -> None:
    """余额查询恢复后发「已恢复」通知（状态机 resolved 沿）。"""
    try:
        from pa_agent.notify.feishu_notifier import _send_feishu_text_alert
    except Exception as e:
        print(f"  [告警发送失败] feishu_notifier 不可用: {e!r}")
        return
    try:
        text = (
            "PA Agent 余额查询已恢复\n"
            f"symbol: {sym}\n"
            f"signal_id: {sid}\n"
            "此前持续失败升级告警已解除——持仓保护链路恢复正常巡检。"
        )
        _send_feishu_text_alert(text, log_label="余额查询恢复通知")
    except Exception as e:
        print(f"  [告警发送失败] {e!r}")
def run_executor(
    pending_dir: Path,
    *,
    watchlist: tuple = WATCHLIST,
    base_qty: float = 4.0,
    live: bool = False,
    auto_cancel: bool = True,
    api_key: Optional[str] = None,
    secret: Optional[str] = None,
    min_net_rr: Optional[float] = None,
) -> dict:
    """扫 pending → 白名单过滤 → guardrails → (live) 下单 → audit。

    返回统计 dict。dry-run 只打印，live 需要 api_key/secret。
    """
    stats = {"scanned": 0, "not_in_watchlist": 0, "no_signal": 0,
             "blocked": 0, "approved": 0, "orders": 0, "already": 0, "has_position": 0, "stale_signal": 0}
    al = AuditLog()
    ex = BinanceSpotExecutor(api_key, secret) if live and api_key and secret else None
    # 幂等（P0-自动触发前提）：本进程后续轮次已提交过的 record_id 不再重复下单。
    # derive_signal_id 含毫秒时间戳 → 同 pending 文件每轮都会生成新 sid，
    # 若不按 record_id 去重，schtasks 5min 定时会连环重复下单（实测无幂等）。
    already_seen = {r.get("record_id") for r in al.snapshot() if r.get("record_id")}
    # 叠仓护栏：audit 中该 symbol 已有"在场单"→ 新决策跳过（防 scheduler 每轮
    # 新 pending 触发同 symbol 连环加仓）。在场判定 = 活性 SL（sl_status=PLACED）
    # 或未平挂单（status in NEW/PARTIALLY_FILLED：限价/突破未成交，仓位可能已入）。
    _HELD_STATUS = ("NEW", "PARTIALLY_FILLED")
    # 终态 outcome 的行不算在场（实测：auto_cancel 撤单后 status 仍残留 NEW，
    # 若不排除，历史撤单会让 symbol 永久 held → 真实信号永远被拦，2026-09-30 实证）
    _TERMINAL_OUTCOME = {"CANCELED", "FILLED", "STOP_PLACE_FAILED", "REJECTED", "EXPIRED"}
    held_syms = {r.get("symbol") for r in al.snapshot()
                 if r.get("symbol")
                 and (r.get("sl_status") == "PLACED"
                      or (r.get("status") in _HELD_STATUS
                          and r.get("outcome") not in _TERMINAL_OUTCOME))}

    for f in sorted(Path(pending_dir).glob("*.json")):
        try:
            rec = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        stats["scanned"] += 1
        meta = rec.get("meta") or {}
        symbol = meta.get("symbol")
        if symbol not in watchlist:
            stats["not_in_watchlist"] += 1
            continue
        dec = (rec.get("stage2_decision") or {}).get("decision") or {}
        direction = dec.get("order_direction")
        order_type = dec.get("order_type")
        if not direction or not order_type or order_type == "不下单":
            stats["no_signal"] += 1
            continue
        rec_id = rec.get("record_id") or f.stem
        if rec_id in already_seen:
            stats["already"] += 1
            # ---- P0-B 已见单补查（2026-10-01 缺口修复）：先挂单后成交 → 补挂 SL 防裸露 ----
            # 触发条件：live 且 audit 行未收尾（无 SL、无终态 outcome、状态仍在场）→ 查交易所实时成交。
            # 幂等：已挂 SL 的行 sl_order_id 非空 → 跳过（手动补挂 1817279 即不再重复）。
            if ex is not None:
                row = next((r for r in al.snapshot()
                            if r.get("record_id") == rec_id), None)
                if (row and row.get("venue_order_id")
                        and not row.get("sl_order_id")
                        and row.get("outcome") not in ("CANCELED", "REJECTED", "EXPIRED", "STOP_PLACE_FAILED")
                        and (row.get("status") in _HELD_STATUS
                             or row.get("outcome") == "FILLED"
                             or not row.get("status"))):
                    cq, bq = ex._signed("/api/v3/order",
                                        {"symbol": symbol, "orderId": row["venue_order_id"]})
                    if cq == 200 and isinstance(bq, dict) and bq.get("status") == "FILLED":
                        # P0-20261001 安全补挂：_guard_fill 内做 side==BUY + 平仓时间线双核查
                        st = _guard_fill(ex, al, row)
                        if st == "placed":
                            print(f"  [已见单补挂SL] {rec_id}: 安全核查通过 -> SL 已挂")
                        elif st == "no_position":
                            print(f"  [已见单跳过] {rec_id}: 已平仓/非做多 -> NO_POSITION")
            continue
        if symbol in held_syms:
            stats["has_position"] += 1
            continue
        # ---- 信号年龄校验（2026-10-02 定制方案步骤2）：决策超过 1h 视为过期拒单 ----
        sig_ts = meta.get("timestamp_local_ms")
        if sig_ts:
            age_s = (time.time() * 1000 - int(sig_ts)) / 1000.0
            if age_s > MAX_SIGNAL_AGE_S:
                stats["stale_signal"] = stats.get("stale_signal", 0) + 1
                print(f"  [拦截] {f.name}: 信号过期 age={age_s/3600.0:.1f}h > {MAX_SIGNAL_AGE_S/3600.0:.0f}h (ts={sig_ts})")
                continue
        g = evaluate_decision(dec, min_net_rr=min_net_rr)
        if not g.allowed:
            stats["blocked"] += 1
            print(f"  [拦截] {f.name}: {g.reason}")
            continue
        stats["approved"] += 1
        # 目标价/数量：TP2 为目标；qty = base_qty * scale
        qty = max(1.0, base_qty * g.position_scale)
        entry_price = float(dec.get("entry_price"))
        stop_loss = float(dec.get("stop_loss_price") or 0.0)
        print(f"  [放行] {f.name}: {direction} {order_type} entry={entry_price} "
              f"target(TP2)={g.target_price} scale={g.position_scale} qty={qty:.2f} net_rr={round(g.net_rr,3)}")
        if not live or ex is None:
            continue
        # ---- P0-1 现货边界：现货无借币做空（实测 -2010 超卖必拒）→ 做空信号跳过 ----
        if direction in ("做空", "空"):
            stats["spot_no_short"] = stats.get("spot_no_short", 0) + 1
            print(f"  [跳过] {f.name}: {direction} 现货执行层不支持(spot_no_short)；合约 key 区域封锁无路径 → 做空侧永久放弃，仅统计")
            continue
        # ---- live：下单 + 审计 ----
        side = "BUY"
        sid = derive_signal_id(rec.get("record_id") or f.stem,
                               str(entry_price), str(stop_loss),
                               str(g.target_price), side, int(time.time() * 1000))
        al.record_submission(signal_id=sid, record_id=f.stem, symbol=symbol,
                             direction=direction, order_type=order_type,
                             entry=entry_price, stop=stop_loss,
                             target=g.target_price, position_scale=g.position_scale,
                             net_rr=g.net_rr, conf=dec.get("trade_confidence"))
        # ---- P0-4 order_type 分支（决策三型：限价/突破/市价）----
        if order_type == "突破单":
            # 现货无原生突破单，实测映射：BUY STOP_LOSS_LIMIT（stopPrice>市价 = 上穿触发买入，
            # -2010 实测反向拒绝）。price = stop*(1+frac) 追涨侧。
            tick = ex._tick_size(symbol)
            frac = max(0.002, 5 * tick / entry_price) if entry_price > 0 else 0.002
            px = round(entry_price * (1 + frac), ex._price_precision(symbol))
            c, b = ex._signed("/api/v3/order", {
                "symbol": symbol, "side": side, "type": "STOP_LOSS_LIMIT",
                "quantity": f"{qty:.2f}", "stopPrice": f"{entry_price:.6f}".rstrip("0").rstrip("."),
                "price": f"{px:.6f}".rstrip("0").rstrip("."), "timeInForce": "GTC",
                "newClientOrderId": sid}, method="POST")
        elif order_type == "市价单":
            c, b = ex.place_market(symbol, side, f"{qty:.2f}", sid)
        else:  # 限价单（默认）
            # P0-A 修复：入场限价 = entry_price（原实现误用 TP2 target_price 当入场价）
            c, b = ex.place_limit(symbol, side, f"{qty:.2f}", f"{entry_price:.6f}".rstrip("0").rstrip("."), sid)
        print(f"    下单[{order_type}]: code={c} {json.dumps(b, ensure_ascii=False)[:140] if isinstance(b, dict) else b}")
        if c != 200 or not isinstance(b, dict) or not b.get("orderId"):
            al.update_outcome(sid, outcome="REJECTED", exit_reason=f"place_failed:{c}")
            continue
        stats["orders"] += 1
        oid = b["orderId"]
        al.update_outcome(sid, venue_order_id=str(oid), status=b.get("status"))
        # 现货做多（BUY）FILLED → 止损三件套（P0-1/3：挂 SLL + 部分成交校准 + 失败兜底）
        if b.get("status") in ("FILLED", "PARTIALLY_FILLED"):
            # 1) filled_price 回填（P0-B）：fills 加权均价，无 fills 用累计报价/量
            filled_price = None
            fills = b.get("fills") or []
            if fills:
                tot_q, tot_v = 0.0, 0.0
                for f in fills:
                    fq = float(f.get("qty") or 0); fp = float(f.get("price") or 0)
                    tot_q += fq; tot_v += fq * fp
                if tot_q > 0:
                    filled_price = round(tot_v / tot_q, 6)
            if filled_price is None:
                cq = float(b.get("cummulativeQuoteQty") or 0); eq = float(b.get("executedQty") or 0)
                if eq and cq:
                    filled_price = round(cq / eq, 6)
            # 2) 部分成交校准：SL 量 = 实际成交 executedQty（现货无 reduceOnly → 必须对齐，防反向开仓）
            sl_qty = float(b.get("executedQty") or 0) or qty
            if sl_qty <= 0:
                sl_qty = qty
            al.update_outcome(sid, outcome="FILLED", venue_order_id=str(oid),
                              filled_price=filled_price, executed_qty=sl_qty,
                              sl_qty=sl_qty)
            # 3) 挂止损：重试 3 次（退避 1s/2s），全失败 → 市价平仓防裸露（STOP_PLACE_FAILED）
            if stop_loss and stop_loss > 0:
                sl_cid = f"{sid}-SL"
                ok = False
                last_err = ""
                for attempt in range(3):
                    c3, b3 = ex.place_stop_loss_limit(symbol, "SELL", f"{sl_qty:.2f}",
                                                      stop_loss, sl_cid)
                    if c3 == 200 and isinstance(b3, dict) and b3.get("orderId"):
                        al.update_outcome(sid, sl_order_id=str(b3["orderId"]),
                                          sl_status="PLACED", sl_stop_price=stop_loss,
                                          sl_type="STOP_LOSS_LIMIT", sl_cid=sl_cid)
                        ok = True
                        print(f"    止损挂单: id={b3['orderId']} stop={stop_loss} qty={sl_qty:.2f}")
                        break
                    last_err = f"{c3} {b3.get('msg','')[:60] if isinstance(b3, dict) else b3}"
                    time.sleep(1 + attempt)
                if not ok:
                    print(f"    止损挂单失败(3次): {last_err} -> 市价平仓")
                    c4, b4 = ex.place_market(symbol, "SELL", f"{sl_qty:.2f}", f"{sid}-EMG")
                    emg_code = c4
                    al.update_outcome(sid, outcome="STOP_PLACE_FAILED",
                                      exit_reason=f"sl_fail:{last_err[:50]}",
                                      emergency_closed=(c4 == 200),
                                      sl_status="PLACE_FAILED")
            else:
                al.update_outcome(sid, outcome="FILLED", exit_reason="no_stop_price",
                                  sl_status="SKIPPED")
        # auto_cancel 仅对市价单生效（市价单 NEW = 流动性异常，撤了防卡单）；
        # 限价/突破单豁免（挂单等待本就是其策略语义，撤单 = 信号白放行，2026-09-30 实证被撤）
        elif auto_cancel and b.get("status") == "NEW" and order_type == "市价单":
            c2, b2 = ex.cancel_by_client_id(symbol, sid)
            al.update_outcome(sid, outcome="CANCELED", exit_reason="auto_cancel",
                              venue_order_id=str(oid))
            print(f"    撤单(auto): code={c2} status={(b2 or {}).get('status') if isinstance(b2, dict) else b2}")
        elif order_type == "突破单" and b.get("status") in (None, "NEW"):
            # 突破单（条件单）未触发：实证币安条件单 POST 响应 status=null（2026-10 测试网），
            # 但单真实在场（NEW）。不撤销、不 auto_cancel（显式排除），保留由 --check-sl/超时接续。
            al.update_outcome(sid, outcome="PENDING", exit_reason="breakout_wait",
                              venue_order_id=str(oid), sl_status="NA_ENTRY")

    return stats


def _fifo_remaining(ex, sym) -> tuple:
    """P0-20261001 持仓核对：全量拉同 symbol 成交，FIFO 配对 → (rem, seen_order_ids)。

    ⚠️ 强假设（P0）：FIFO 是自建逻辑近似，仅在「PA_Agent 是唯一交易通道」时成立。
      —— 币安现货只有余额、无持仓对象，FIFO 按时间顺序把 SELL 平给最旧 BUY，是
         逻辑配对；若用户在币安 App 手动买卖同一 symbol，myTrades 会出现 audit
         未追踪的 orderId → 配对错乱 → 判据失真。调用方(_guard_fill)必须用返回的
         seen_order_ids 与 audit 已知 venue_order_id 比对，检测外部成交并告警。

     窗口化（P1，观察期后）：FIFO 起点必须覆盖「最早可能未平 BUY」，而 audit 未收尾
       状态本身是 FIFO 判据的产出 → 循环依赖，不能作窗口起点；真正起点 = 余额基准
       快照（净持仓=0 时点）。观察期主网全量拉（测试网 <10 条无收益），窗口化待
       P2 position 聚合（余额快照 + 成交对账）一并设计。
    """
    trades = []
    from_id = 0
    params = {"symbol": sym, "limit": 1000}
    while True:
        p = dict(params)
        p["fromId"] = from_id
        c, b = ex._signed("/api/v3/myTrades", p)
        if c != 200 or not isinstance(b, list) or not b:
            break
        trades.extend(b)
        if len(b) < 1000:
            break
        nxt = max(int(t["id"]) for t in b) + 1
        if nxt <= from_id:
            break
        from_id = nxt
    # 时间升序（time 优先，同刻按 id）保证 FIFO 稳定
    trades.sort(key=lambda x: (x.get("time") or 0, x.get("id") or 0))
    seen = {str(t.get("orderId")) for t in trades}
    queue = []  # list[ [orderId, 未平量] ]
    for t in trades:
        qty = float(t.get("qty") or 0)
        if t.get("isBuyer"):
            queue.append([str(t.get("orderId")), qty])
        else:
            left = qty
            while left > 0 and queue:
                head = queue[0]
                if head[1] <= left:
                    left -= head[1]
                    queue.pop(0)
                else:
                    head[1] -= left
                    left = 0
            # left 残留 = 卖超我方持仓（账户预置余额/预置库存），不记账
    rem = {}
    for oid, q in queue:
        rem[oid] = rem.get(oid, 0.0) + q
    return rem, seen


def _place_sl(ex, al, sid, sym, sl_qty, stop) -> str:
    """补挂 SELL SLL（3 次重试 → 失败市价平仓兜底），成功补写 outcome=FILLED。返回 placed/skip。

    FIFO 正常路径与外部成交余额兜底路径共用同一补挂链（含 outcome 补写，P1 闭环）。
    """
    sl_cid = f"{sid}-SL"
    ok = False
    last_err = ""
    for attempt in range(3):
        c3, b3 = ex.place_stop_loss_limit(sym, "SELL", f"{sl_qty:.2f}", stop, sl_cid)
        if c3 == 200 and isinstance(b3, dict) and b3.get("orderId"):
            al.update_outcome(sid, outcome="FILLED", sl_order_id=str(b3["orderId"]),
                              sl_status="PLACED", sl_stop_price=stop, sl_type="STOP_LOSS_LIMIT",
                              sl_cid=sl_cid, executed_qty=sl_qty, sl_qty=sl_qty)
            ok = True
            break
        last_err = f"{c3} {(b3 or {}).get('msg', '')[:60] if isinstance(b3, dict) else b3}"
        time.sleep(1 + attempt)
    if not ok:
        c4, b4 = ex.place_market(sym, "SELL", f"{sl_qty:.2f}", f"{sid}-EMG")
        al.update_outcome(sid, outcome="STOP_PLACE_FAILED", exit_reason=f"sl_fail:{last_err[:50]}",
                          emergency_closed=(c4 == 200), sl_status="PLACE_FAILED")
        return "skip"
    return "placed"


def _guard_fill(ex, al, row) -> str:
    """P0-20261001 安全补挂 SL：side==BUY + FIFO 未平量核查，通过才补挂。

    前置核查（防反向开仓 / 防"已平仓后补挂无保护 SELL"）：
      1) 交易所 order.side == BUY（SELL FILLED = 平仓单，补挂 = 反向开仓风险，标 NO_POSITION）
      2) FIFO 对账：该 BUY orderId 未平量 >= 本单量 → 仓位仍在 → 补挂；
         未平量 < 本单量（已被后来 SELL 平掉）→ NO_POSITION。
         修复：多 BUY 叠加时 SELL 只平最旧 BUY，不误判较新持仓仍挂保护。
    通过 → 挂 SELL SLL（3 次重试 → 失败市价平仓），SL 量 = 未平量。
     余额兜底（外部成交分支）安全前提 = 单 symbol 单仓位（PA_Agent watchlist
       每 symbol 叠仓护栏成立）；若有其他未收尾持仓行在场 → 余额归属不明 → 挂起
       转人工（P0-20261002），防自动挂 SL 触发时平掉其他行仓位。
    返回: "placed" | "no_position" | "skip"
    """
    sid = row.get("signal_id")
    sym = row.get("symbol")
    oid = row.get("venue_order_id")
    if not oid or not sid or not sym:
        return "skip"
    c, b = ex._signed("/api/v3/order", {"symbol": sym, "orderId": oid})
    if c != 200 or not isinstance(b, dict) or b.get("status") != "FILLED":
        return "skip"
    if b.get("side") != "BUY":
        al.update_outcome(sid, sl_status="NO_POSITION", exit_reason=f"side={b.get('side')}")
        return "no_position"
    # P0-2026-10-01 FIFO 对账：SELL 平最旧 BUY，逐单分配，多 BUY 叠加不误判
    fill_qty = float(b.get("executedQty") or 0) or 4.0
    rem, seen = _fifo_remaining(ex, sym)
    # P0 异常检测：myTrades 出现 audit 未追踪的 orderId = 非 PA_Agent 成交（手动 App/外部通道）
    # → FIFO 单通道假设失效，不再信任 FIFO 结果（外部 SELL 可能平错对象 → 误判 NO_POSITION
    #   会漏挂保护）。余额兜底（唯一真相 = 交易所余额）：free+locked >= 本单量 fill_qty
    #   → 保守补挂（宁可多挂，不可裸露）；不足 → NO_POSITION。
    #   skip 仅用于两种「判据不足」：①余额归属不明（其他未收尾持仓行在场，P0-20261002
    #   注：strays 含 PA 历史测试单（假阳性）也可接受——余额兜底天然处理：余额够就挂、
    #      不够就 NO_POSITION，无需假设订单来源格式（币安 App clientOrderId 格式未验证，
    #      P2 观察期后探测）。
    known = {str(r.get("venue_order_id")) for r in al.snapshot() if r.get("venue_order_id")}
    stray = sorted(seen - known)
    if stray:
        print(f"  [FIFO告警] {sid}: 检测到外部成交 orderId={stray[:5]}（不在 audit）"
              f"→ FIFO 单通道假设失效，改用余额兜底判据")
        # P0-2026-10-02 误挂防护：余额兜底安全前提 = 该 symbol 单仓位。
        # 其他未收尾持仓行（pending_sl 候选，排除本行）在场 → 余额可能属于他人，
        # 自动挂 SL 触发时平掉其他行仓位 → 挂起转人工（保持待巡检，5min 持续告警）。
        # P0-20261002 fix-2（再修）：数据源 al.snapshot() + 终态集改用 audit_log._TERMINAL_SL。
        #   用户审查 P0：初版只写 3 个终态漏 FILLED/GAP_CLOSED/REDEPLOY_FAILED/EXPIRED →
        #   SL 已成交(FILLED)的 row 本已平仓却仍算在场 → 本 row 误 skip → 挂不上 SL → 裸露。
        #   终态 = SL 已收尾 = 该 row 无持仓；单一定义单一引用（audit_log.py 模块级常量）。
        other_held = [r for r in al.snapshot()
                      if r.get("symbol") == sym
                      and r.get("signal_id") != sid
                      and r.get("venue_order_id")
                      and r.get("sl_status") not in _TERMINAL_SL]
        if other_held:
            print(f"  [FIFO挂起] {sid}: 该 symbol 存在其他未收尾持仓行 {len(other_held)} 个"
                  f"→ 余额归属不明，挂起转人工核查（防误挂平其他仓位）")
            return "skip"
        _cb, _bb = ex._signed("/api/v3/account", {"omitZeroBalances": "true"})
        if _cb != 200 or not isinstance(_bb, dict):
            # P0-20261002 fix-3（再修）：跨进程持久化累计（见模块级注释）。
            print(f"  [FIFO挂起] {sid}: 余额查询失败 code={_cb} → 判据不足，挂起转人工")
            _balance_fail_bump(sym, sid, _cb)
            return "skip"
        _balance_alert_clear(sym, sid)
        bal = 0.0
        for a in _bb.get("balances", []):
            if a.get("asset") == sym.replace("USDT", ""):
                bal = float(a.get("free") or 0) + float(a.get("locked") or 0)
        print(f"  [FIFO兜底] {sid}: free+locked={bal:.2f} vs 本单量 {fill_qty:.2f}")
        # P1 trade-off：挂 fill_qty（本单量近似）。现货 SLL 挂单不占余额，触发时
        #   余额决定成交——余额够才保护、不够仍裸露；挂 fill_qty 是唯一无外部假设的量。
        if bal >= fill_qty * 0.999:
            return _place_sl(ex, al, sid, sym, fill_qty, row.get("stop") or 0.0)
        al.update_outcome(sid, sl_status="NO_POSITION", exit_reason=f"balance={bal:.2f}<{fill_qty:.2f}")
        return "no_position"
    remaining = float(rem.get(str(oid), 0.0))
    if remaining < fill_qty * 0.999:
        al.update_outcome(sid, sl_status="NO_POSITION", exit_reason=f"fifo_remaining={remaining:.2f}<{fill_qty:.2f}")
        return "no_position"
    sl_qty = max(1.0, remaining)  # 按未平量补挂，防叠加场景挂多
    return _place_sl(ex, al, sid, sym, sl_qty, row.get("stop") or 0.0)


def check_sl(ex, al) -> dict:
    """P0-2 巡检保护性止损（SELL SLL）：三态判定，幂等（只处理 sl_status 未收尾）。

    判定（status × 市价 vs stopPrice 双条件，SELL 侧触发线 = 市价下穿 stopPrice）：
      未触发     status=NEW 且 市价 >  stopPrice          → 跳过
      触发未成交 status=NEW 且 市价 <= stopPrice          → 立即市价平仓残余 GAP_CLOSED
      已成交     status=FILLED/PARTIALLY_FILLED → 对齐 executedQty，无操作
      丢失       status=CANCELED/EXPIRED        → 默认重挂；失败市价平 REDEPLOY_FAILED。
                 PA_AGENT_SL_REDEPLOY=0 时用户显式撤停 → 标记终态退出，不改动
    """
    stats = {"scanned": 0, "skip": 0, "gap_closed": 0, "filled": 0, "redeploy": 0}
    for r in al.pending_sl():
        sym = r.get("symbol")
        if not sym:
            continue
        stats["scanned"] += 1
        sid = r["signal_id"]
        # P0-2026-10-01 入口复核：无 sl_order_id 的行（成交后从未挂 SL，pending_sl 放宽入巡检）
        # 本就没有单可查 → 直接走 _guard_fill 安全核查，不发无意义的查单请求。
        if not r.get("sl_order_id"):
            st = _guard_fill(ex, al, r)
            if st == "placed":
                stats["redeploy"] += 1
                print(f"  [补挂] {sid}: 成交无 SL -> FIFO核查后补挂")
            elif st == "no_position":
                stats["skip"] += 1
                print(f"  [已平跳过] {sid}: NO_POSITION(已平/非做多)")
            elif st == "skip":
                print(f"  [跳过] {sid}: FIFO/order 核查失败")
            continue
        sl_cid = r.get("sl_cid") or f"{sid}-SL"
        c, b = ex.query_order_by_client_id(sym, sl_cid)
        if c != 200 or not isinstance(b, dict):
            print(f"  [查单失败] {sid} sl_cid={sl_cid}: code={c}")
            continue
        st, sid = b.get("status"), r["signal_id"]
        st, sid = b.get("status"), r["signal_id"]
        if st in ("FILLED", "PARTIALLY_FILLED"):
            al.update_outcome(sid, sl_status="FILLED", sl_exit_status=st,
                              sl_filled_qty=b.get("executedQty"))
            stats["filled"] += 1
            print(f"  [SL已成交] {sid}: status={st} qty={b.get('executedQty')}")
        elif st in ("CANCELED", "EXPIRED", "REJECTED"):
            # 丢失 → 默认重挂（保护性止损不丢位）；PA_AGENT_SL_REDEPLOY=0 时
            # 视为用户已手动撤停（audit 无法区分用户撤 vs 系统撤，显式开关为准），
            # 标记终态 sl_status=CANCELED 退出巡检，不再重挂、不动仓。
            if os.environ.get("PA_AGENT_SL_REDEPLOY", "1") != "1":
                al.update_outcome(sid, sl_status="CANCELED",
                                  exit_reason="user_disabled_redeploy")
                stats["skip"] += 1
                print(f"  [SL重挂已禁用] {sid}: 标记终态退出巡检 (PA_AGENT_SL_REDEPLOY=0)")
                continue
            price = ex.market_price(sym)
            stop = r.get("sl_stop_price") or 0.0
            qty = r.get("sl_qty") or r.get("executed_qty") or 4.0
            c3, b3 = ex.place_stop_loss_limit(sym, "SELL", f"{qty:.2f}", stop, sl_cid)
            if c3 == 200 and isinstance(b3, dict) and b3.get("orderId"):
                al.update_outcome(sid, sl_status="PLACED", sl_order_id=str(b3["orderId"]),
                                  sl_redeploy=1)
                stats["redeploy"] += 1
                print(f"  [SL重挂] {sid}: id={b3['orderId']} stop={stop}")
            else:
                # 市价平仓
                c4, b4 = ex.place_market(sym, "SELL", f"{qty:.2f}", f"{sid}-EMG-REDEPLOY")
                al.update_outcome(sid, sl_status="REDEPLOY_FAILED",
                                  exit_reason=f"sl_redeploy_fail:{c4}", emergency_closed=(c4 == 200))
                stats["redeploy"] += 1
                print(f"  [SL重挂失败->市价平] {sid}: code={c4} {(not isinstance(b4, dict) or b4.get('status'))}")
        else:
            # status == NEW：用市价 vs stopPrice 区分未触发/触发未成交
            mkt = ex.market_price(sym)
            stop = r.get("sl_stop_price") or 0.0
            if mkt is None:
                print(f"  [行情失败] {sid}")
                continue
            if mkt <= stop:
                qty = r.get("sl_qty") or r.get("executed_qty") or 4.0
                c5, b5 = ex.place_market(sym, "SELL", f"{qty:.2f}", f"{sid}-EMG")
                al.update_outcome(sid, sl_status="GAP_CLOSED",
                                  exit_reason=f"trigger_no_fill mkt={mkt} stop={stop}",
                                  emergency_closed=(c5 == 200))
                stats["gap_closed"] += 1
                print(f"  [触发未成交->市价平] {sid}: mkt={mkt} <= stop={stop} -> {c5}")
            else:
                stats["skip"] += 1
                print(f"  [未触发] {sid}: mkt={mkt} > stop={stop}")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="PA_Agent 币安执行层（默认 dry-run）")
    ap.add_argument("--pending", default=str(DEFAULT_PENDING))
    ap.add_argument("--base-qty", type=float, default=4.0)
    ap.add_argument("--live", action="store_true", help="真实下单（现货测试网）")
    ap.add_argument("--no-auto-cancel", action="store_true")
    ap.add_argument("--min-net-rr", type=float, default=None,
                    help="观察通道：临时放宽净盈亏比门槛（默认 None=SSOT MIN_NET_RR=1.5）")
    ap.add_argument("--check-sl", action="store_true",
                    help="P0-2 三态巡检保护性止损（幂等；配合 schtasks 每 5 分钟）")
    args = ap.parse_args()

    key = secret = None
    if args.live or args.check_sl:
        envf = os.environ.get("BINANCE_TEST_ENV", r"D:\OpenCode\temp\binance_testnet.env")
        env = {}
        for line in open(envf, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k] = v
        key, secret = env.get("BINANCE_TEST_API_KEY"), env.get("BINANCE_TEST_SECRET")
        if not key or not secret:
            print("--live/--check-sl 需要 binance_testnet.env（BINANCE_TEST_API_KEY/SECRET）"); sys.exit(1)

    if args.check_sl:
        ex = BinanceSpotExecutor(key, secret)
        al = AuditLog()
        st = check_sl(ex, al)
        print(f"check-sl 统计: scanned={st['scanned']} 未触发={st['skip']} "
              f"触发未成交平仓={st['gap_closed']} 已成交={st['filled']} 重挂={st['redeploy']}")
        return

    stats = run_executor(args.pending, base_qty=args.base_qty, live=args.live,
                         auto_cancel=not args.no_auto_cancel,
                         api_key=key, secret=secret, min_net_rr=args.min_net_rr)
    print(f"统计: scanned={stats['scanned']} 非白名单={stats['not_in_watchlist']} "
          f"无信号={stats['no_signal']} 拦截={stats['blocked']} 放行={stats['approved']} "
          f"下单={stats['orders']} 已成交跳过={stats.get('already', 0)} "
          f"持仓拦截={stats.get('has_position', 0)}" +
          (f" 做空跳过={stats.get('spot_no_short', 0)}" if stats.get("spot_no_short") else ""))
    mode = "LIVE" if args.live else "DRY-RUN（未下单）"
    if args.min_net_rr is not None:
        mode += f"（观察通道 min_net_rr={args.min_net_rr}）"
    print("模式:", mode)


if __name__ == "__main__":
    main()
