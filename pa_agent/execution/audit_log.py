# -*- coding: utf-8 -*-
"""audit_log.py — 执行审计链（Phase 2 执行层）。

每次下单前生成 signal_id = hash(record_id + entry + stop + target + side + ts)，
追加写入 JSONL。字段按 2pa-agent-rust v0.5.0 对账格式设计：
  R 倍数 / MFE / MAE / 持仓 K 线数 / 费用 / 出场原因
（MFE/MAE 需持仓期间逐 bar 数据，PA 记录 kline_data 40-50 根可事后回算——
  真实 pending 59/60 条有 kline_data，实测 2026-09-28。落盘时先记 null，回算后回填。）

本模块只写 JSONL（append-only），绝不触碰 records/pending 原记录。
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import msvcrt  # Windows 跨进程文件锁（ws_bot 巡检线程 + schtasks 双写安全）
except ImportError:  # 非 Windows 降级为线程锁
    msvcrt = None


# 默认审计目录（可注入，便于测试隔离）
DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "records" / "execution_log"


# SL 挂单状态终态集（单一定义单一引用：pending_sl 巡检与 executor other_held 共用，C315 精神）
_TERMINAL_SL = {"FILLED", "GAP_CLOSED", "REDEPLOY_FAILED", "CANCELED", "EXPIRED"}


def derive_signal_id(record_id: str, entry: str, stop: str, target: str, side: str, ts_ms: int) -> str:
    """signal_id = sha256(record_id|entry|stop|target|side|ts) 前 16 位。

    与 2pa reconciler 语义一致：决策→id→audit→venue client order id，可回溯。
    """
    raw = "|".join([record_id, str(entry), str(stop), str(target), side, str(ts_ms)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def compute_mfe_mae(
    *,
    entry: float,
    stop: float,
    direction: str,
    kline_data: list,
    exit_price: Optional[float] = None,
) -> dict:
    """持仓期逐 bar 回算 MFE/MAE（绝对价 + R 倍数），2pa reconciler 对账语义。

    kline_data: 持仓期 bars（entry 后到 exit，newest-first，KlineBar dict 格式
      同 pending 记录，seq=1 最新）。真实持仓结束时应重新拉取覆盖持仓窗口的
      数据传入——决策时刻的 pending kline_data 是快照，不含持仓期未来 bar，
      不能直接用于回算。
    direction: 做多 / 做空。
    R = |entry - stop|；stop 为 0/None 时 R 倍数为 None。
    返回: {mfe, mae, mfe_r, mae_r, bars_used, exit_price}
      MFE(多) = max(high) - entry；MAE(多) = min(low) - entry（负 = 不利）
      MFE(空) = entry - min(low)；MAE(空) = entry - max(high)
    """
    long_ = direction in ("做多", "多", "BUY", "buy")
    r = abs(entry - stop) if stop else None
    highs = [float(b["high"]) for b in kline_data if isinstance(b, dict) and b.get("high") is not None]
    lows = [float(b["low"]) for b in kline_data if isinstance(b, dict) and b.get("low") is not None]
    if not highs or not lows:
        return {"mfe": None, "mae": None, "mfe_r": None, "mae_r": None,
                "bars_used": 0, "exit_price": exit_price}
    if long_:
        mfe, mae = max(highs) - entry, min(lows) - entry
    else:
        mfe, mae = entry - min(lows), entry - max(highs)
    return {
        "mfe": round(mfe, 6), "mae": round(mae, 6),
        "mfe_r": round(mfe / r, 4) if r else None,
        "mae_r": round(mae / r, 4) if r else None,
        "bars_used": len(highs), "exit_price": exit_price,
    }



class AuditLog:
    """append-only JSONL 审计日志。"""

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self._dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "execution_audit.jsonl"
        self._lock = threading.Lock()  # 进程内互斥（同进程多线程）

    # ---- 写 ----
    def record_submission(
        self,
        *,
        signal_id: str,
        record_id: str,
        symbol: str,
        direction: str,
        order_type: str,
        entry: float,
        stop: float,
        target: float,
        position_scale: float,
        net_rr: float,
        conf: Optional[float] = None,
    ) -> str:
        """下单提交前调用：写 submitted 行。返回 signal_id。"""
        row = {
            "signal_id": signal_id,
            "record_id": record_id,
            "symbol": symbol,
            "ts_submitted_ms": int(datetime.now().timestamp() * 1000),
            "direction": direction,
            "order_type": order_type,
            "entry": entry,
            "stop": stop,
            "target": target,
            "position_scale": position_scale,
            "net_rr": round(float(net_rr), 4),
            "confidence": conf,
            "venue_order_id": None,   # 下单后回填
            "filled_price": None,
            "outcome": None,          # 平仓后回填：TP/STOP/手动
            "r_multiple": None,       # 平仓后回填
            "mfe": None,              # 持仓期最大有利偏移（事后回算）
            "mae": None,              # 持仓期最大不利偏移（事后回算）
            "bars_held": None,
            "fees": None,
            "exit_reason": None,
            "source": "guardrails.phase2",
        }
        self._append(row)
        return signal_id

    def update_outcome(self, signal_id: str, **fields) -> None:
        """成交/回填 correction：追加 correction 行（append-only，非原子原位重写）。

        P0-1 升级（原实现重读全文件→重写，中途崩溃丢整个文件）：
        现在每笔回填追加一行 {signal_id, _correction: true, ts_update_ms, **fields}，
        读者用 snapshot() 按时间序叠加，correction 覆盖对应字段、保留主行原始字段。
        correction 行含 signal_id 即可独立解析；崩溃最多丢当前一行（重跑幂等）。
        """
        row = {
            "signal_id": signal_id,
            "_correction": True,
            "ts_update_ms": int(datetime.now().timestamp() * 1000),
            **fields,
        }
        self._append(row)

    # ---- 读 ----
    def entries(self, signal_id: Optional[str] = None):
        for row in self._read_all():
            if signal_id is None or row.get("signal_id") == signal_id:
                yield row

    def snapshot(self, signal_id: Optional[str] = None) -> list:
        """叠加读取：主行 + corrections（行序后写覆盖），返回最终态 dict 列表。

        供 --check-sl 等跨进程只读消费者使用；不修改文件。
        """
        merged: dict = {}
        order: list = []
        for row in self._read_all():
            sid = row.get("signal_id")
            if signal_id is not None and sid != signal_id:
                continue
            if sid not in merged:
                merged[sid] = {}
                order.append(sid)
            merged[sid].update(row)
        return [merged[sid] for sid in order]

    def pending_sl(self) -> list:
        """返回需要止损巡检的信号，供 --check-sl 巡检。

        两类：① 已挂 SL 且未收尾（sl_status 非终态）；② 已成交(FILLED)但无 SL 的行
        （venue_order_id 在场、outcome==FILLED、非 NO_POSITION）→ 补挂候选，
        由 check_sl 做安全核查（side==BUY + FIFO 未平量）后决定补挂或跳过。
        P0-20261001：原实现只巡已有 sl_order_id 的行 → 成交后无 SL 的单子永不
        巡检（1772121 裸露 9h 根因），故放宽；但仅限已成交行（outcome==FILLED），
        排除 outcome 为空/PENDING 的未成交历史行，避免每 5min 无效查单（P0 收紧）。
    """
        terminal = _TERMINAL_SL
        rows = []
        for r in self.snapshot():
            if r.get("sl_order_id") and r.get("sl_status") not in terminal:
                rows.append(r)
            elif (r.get("venue_order_id") and not r.get("sl_order_id")
                  and r.get("sl_status") != "NO_POSITION"
                  and r.get("outcome") == "FILLED"):
                rows.append(r)
        return rows

    # ---- 内部 ----
    def _append(self, row: dict) -> None:
        """追加一行，进程内/跨进程均串行。

        Windows 下用 msvcrt.locking 锁文件首字节区段（LOCKFILE 语义），
        防 ws_bot 秒级巡检线程与 schtasks 5min 进程同时 append 导致 JSONL 行交错。
        msvcrt.locking 需以 r+b 打开（不可 a 模式），写完 flush+解锁。
        """
        text = json.dumps(row, ensure_ascii=False) + "\n"
        with self._lock:
            with open(self._path, "a+", encoding="utf-8", newline="") as f:
                if msvcrt is not None:
                    f.flush()
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                    except OSError:
                        pass  # 锁竞争失败不阻塞审计（审计非关键路径）
                f.write(text)
                f.flush()
                if msvcrt is not None:
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass

    def _read_all(self):
        if not self._path.exists():
            return []
        out = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def _write_all(self, rows) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
