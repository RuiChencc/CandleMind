# -*- coding: utf-8 -*-
"""longconn.py — 飞书长连接事件接收层（双向对话投策，Phase 3 P1 对话链）。

transport 可插拔：
  优先 lark-oapi ws.Client（官方 SDK，网络恢复后 pip install）；
  不可装时手写 wss 客户端（标准库 ssl + WebSocket 帧，TODO 标注）。
  本模块核心 = 消息指令路由（不依赖网络，可本地单测）。

指令（B 形态基线：指定标的分析 + 对分析的追问）：
  "分析 <SYMBOL>"  → 复用 scheduler.run_analysis（headless 两阶段，已落地）
  "追问 <文本>"    → 复用 FreeChatSession（锚定最近分析，多轮追问）
  "帮助"           → 用法说明
回复：notify.feishu_notifier.send_chat_text（应用身份 im/v1/messages，已落地）。

常驻：本模块提供 handle_message()（单条事件处理），由 NSSM 托管服务或
手动拉起的循环调用——按"不启守护"铁律不写自启 while True。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: dialog 兜底日预算护栏（P0-A/P0-B）→ 持久化模块 pa_agent.feishu.budget
#: 计数落 records/execution_log/feishu_budget_<date>.json，重启读回；
#: per-chat ¥0.5 + 全局 ¥1.0 双限额（群聊互不挤占）。
from pa_agent.feishu.budget import budget_release, budget_reserve
from pa_agent.ai.llm_usage import pop_fallback_flag

#: 时间周期口语 → 标准 timeframe
TF_MAP = {
    "十五分线": "15m", "15分线": "15m", "15 分线": "15m", "15分钟线": "15m", "15 分钟线": "15m", "15分钟": "15m", "15m": "15m",
    "半小时线": "30m", "30分线": "30m", "30 分线": "30m", "30分钟线": "30m", "30 分钟线": "30m", "30m": "30m",
    "小时线": "1h", "1小时线": "1h", "1 小时线": "1h", "1小时": "1h", "1 小时": "1h", "1h": "1h", "1h分线": "1h",
    "日线": "1d", "1日线": "1d", "1 日线": "1d", "1d": "1d", "天线": "1d",
}
_TF_ALT = "|".join(re.escape(k) for k in TF_MAP)
# 20:01 实测：用户连打 "1h分线分析分析 XRPUSDT"（无空格）路由失败 → tf 词条补 1h分线 +
# (?:分析){0,2} 容忍连打（引擎回溯保证交替最长匹配）
ANALYZE_RE = re.compile(
    rf"^(?:(?P<tf>{_TF_ALT})\s*)?(?:分析|Analyze|analyse){{0,2}}\s*(?P<sym>[A-Za-z0-9]{{1,20}})$"
)
FOLLOWUP_RE = re.compile(r"^追问\s*(.*)$", re.S)
HELP_RE = re.compile(r"^帮助$")

# 最近一次分析记录（追问锚点；按 chat_id 隔离，多用户并发不互锚 #6）
_last_record_by_chat: dict = {}

# ── 追踪会话（2026-10-02 用户定义基础功能：追踪=持续监控，明确信号才推飞书）──
TRACK_ACTIVE_RE = re.compile(
    rf"^(?:追踪|跟踪|盯住|持续关注)\s*(?:(?P<tf>{_TF_ALT})\s*)?(?P<sym>[A-Za-z0-9]{{1,20}})$"
)
TRACK_STOP_RE = re.compile(r"^(?:停止追踪|取消追踪|别追踪|不追踪)\s*(?P<sym>[A-Za-z0-9]{1,20})?$")

_TRACKS_PATH = Path(__file__).resolve().parent.parent.parent / "records" / "tracks.json"
#: chat_id -> {symbol: timeframe}；_last_run[(chat_id, sym, tf)] -> epoch 秒（防周期内重复）
_tracks: dict = {}
_tracks_lock = threading.Lock()
_last_run: dict = {}
_MAX_TRACKS_PER_CHAT = 3  # 防单 chat 刷多个标的持续烧钱
_MAX_TRACKS_GLOBAL = 5    # 全局追踪目标上限（防多 chat 合计成本失控）
_TF_PERIOD_S = {"15m": 900, "30m": 1800, "1h": 3600, "1d": 86400}
#: 每标的每日估算成本（¥0.14/次 × 24h/周期小时）
_TF_PER_DAY_COST = {"15m": "13.4", "30m": "6.7", "1h": "3.4", "1d": "0.14"}


def _load_tracks() -> None:
    """bot 启动时读回追踪状态（防重启丢追踪）；损坏静默从零。"""
    global _tracks
    try:
        with open(_TRACKS_PATH, encoding="utf-8") as fh:
            data = json.loads(fh.read())
        if isinstance(data, dict):
            _tracks = {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
    except (OSError, ValueError, TypeError):
        _tracks = {}


def _save_tracks() -> None:
    """原子写盘（os.replace）；失败只影响重启恢复，不阻塞追踪。"""
    try:
        _TRACKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _TRACKS_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_tracks, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _TRACKS_PATH)
    except OSError:
        pass


def _register_track(chat_id: str, sym: str, tf: str) -> str:
    with _tracks_lock:
        cur = _tracks.setdefault(chat_id, {})
        if sym in cur and cur[sym] == tf:
            return f"已在追踪 {sym} {tf}（每周期 1 次分析≈¥0.14，约 ¥{_TF_PER_DAY_COST.get(tf, '3.4')}/天/标的）"
        if len(cur) >= _MAX_TRACKS_PER_CHAT:
            return f"追踪上限 {_MAX_TRACKS_PER_CHAT} 个标的。先「停止追踪 <币种>」再添加。"
        if sum(len(d) for d in _tracks.values()) >= _MAX_TRACKS_GLOBAL:
            return f"全局追踪上限 {_MAX_TRACKS_GLOBAL} 个标的（防成本失控）。停止部分追踪后再添加。"
        cur[sym] = tf
        _last_run[(chat_id, sym, tf)] = time.time()  # 注册即首跑（handle_message 承担）；防巡检线程立即重复分析烧钱
        _save_tracks()
    return f"已开始追踪 {sym} {tf}（每周期 1 次分析≈¥0.14，约 ¥{_TF_PER_DAY_COST.get(tf, '3.4')}/天/标的；有明确信号才推送，仅参考）"


def _stop_track(chat_id: str, sym: Optional[str]) -> str:
    with _tracks_lock:
        cur = _tracks.get(chat_id)
        if not cur:
            return "当前没有追踪中的标的。发送「追踪 <币种>」开始。"
        if sym:
            if sym in cur:
                del cur[sym]
                _save_tracks()
                return f"已停止追踪 {sym}"
            return f"未在追踪 {sym}。当前追踪：" + ("、".join(cur) if cur else "无")
        _tracks.pop(chat_id, None)
        _save_tracks()
        return "已停止全部追踪"


def _track_signal(dec: dict) -> bool:
    """明确交易信号判定：order_type 非空且非「不下单」。"""
    ot = (dec.get("order_type") or "").strip()
    return bool(ot) and ot != "不下单"


# 信号推送去重（2026-10-04 检修：23:27/23:43 同方向同价信号 16min 双推 = 一次出两次信号）
# 同 (chat,sym,tf) 在窗口内推过同方向 → 抑制重复；方向翻转是新信号放行。
# 窗口 = 追踪周期（15m=900s、1h=3600s）：同周期内最多推一次同方向信号（已收盘柱基准下
# 相邻两根已收盘柱连出同方向 = 连续信号，周期窗口防刷屏）。
_last_signal_pushed: dict = {}  # (chat, sym, tf) -> (direction, ts)


def _signal_push_ok(chat_id: str, sym: str, tf: str, dec: dict, now: float) -> bool:
    """信号推送去重门：窗口（=追踪周期）内同方向已推过 → False（记录抑制）；否则占位并返回 True。"""
    _dir = (dec.get("order_direction") or "").strip()
    key = (chat_id, sym, tf)
    _prev = _last_signal_pushed.get(key)
    _win = _TF_PERIOD_S.get(tf, 3600)
    if _dir and _prev and _prev[0] == _dir and now - _prev[1] < _win:
        logger.info("追踪信号去重抑制: %s %s %s dir=%s（%ds 内已推过同方向，窗口=%ds）",
                    sym, tf, chat_id, _dir, now - _prev[1], _win)
        return False
    _last_signal_pushed[key] = (_dir, now)
    return True


_AT_PREFIX_RE = re.compile(r"^@\S+\s*")

# 关键词模糊分析触发（免费、无 LLM）：看看/怎么样/查一下/行情 + 提取 symbol
# 无 \b 边界（CJK 是 \w，中文粘连 "分析XRPUSDT" 时 \b 匹配失败——实测验证过）
_FUZZY_WORDS = ("分析", "追踪", "看看", "看一下", "查一下", "怎么样", "如何", "行情")
_SYM_RE = re.compile(r"[A-Z]{2,10}(?:USDT|BUSD|USDC)?")


def route_text(text: str) -> tuple:
    """指令路由（纯函数，可单测）。返回 (kind, payload)。"""
    t = _AT_PREFIX_RE.sub("", (text or "")).strip()  # 群聊 @机器人 前缀剥除
    if not t:
        return ("ignore", None)
    m = ANALYZE_RE.match(t)
    if m:
        sym = m.group("sym").upper()
        tf = TF_MAP.get(m.group("tf"), "1h") if m.group("tf") else "1h"
        # 统一补 USDT 后缀（与 fuzzy 分支一致；"分析 XRP"→XRPUSDT 才能过 symbol 校验）
        if not sym.endswith(("USDT", "BUSD", "USDC")):
            sym += "USDT"
        return ("analyze", (sym, tf))
    m = TRACK_ACTIVE_RE.match(t)
    if m:
        sym = m.group("sym").upper()
        tf = TF_MAP.get(m.group("tf"), "1h") if m.group("tf") else "1h"
        if not sym.endswith(("USDT", "BUSD", "USDC")):
            sym += "USDT"
        return ("track", (sym, tf))
    m = TRACK_STOP_RE.match(t)
    if m:
        sym = m.group("sym").upper() if m.group("sym") else None
        if sym and not sym.endswith(("USDT", "BUSD", "USDC")):
            sym += "USDT"
        return ("track_stop", sym)
    m = FOLLOWUP_RE.match(t)
    if m:
        q = m.group(1).strip()
        return ("followup", q) if q else ("help", None)
    if HELP_RE.match(t):
        return ("help", None)
    # 关键词模糊：如 "XRP 现在怎么样" → analyze(XRPUSDT, 1h)；无 symbol 则落 unknown（回提示语）
    if any(w in t for w in _FUZZY_WORDS):
        sm = _SYM_RE.search(t.upper())
        if sm:
            sym = sm.group(0)
            if not sym.endswith(("USDT", "BUSD", "USDC")):
                sym += "USDT"
            tf = "1h"
            for k, v in TF_MAP.items():
                if k in t:
                    tf = v
                    break
            # 追踪词 → track（持续监控）；停止/取消词 → track_stop（防「别追踪了」误注册）
            if any(w in t for w in ("追踪", "跟踪", "盯住")):
                if any(w in t for w in ("停止", "取消", "别", "不追踪")):
                    return ("track_stop", sym)
                return ("track", (sym, tf))
            return ("analyze", (sym, tf))
    return ("unknown", t)  # 非空文本未匹配 → 提示语（不再静默）


def _assemble_context():
    """AppContext.bootstrap 装配（client/assembler/pending_writer/ledger/settings）。"""
    from pa_agent.app_context import AppContext
    ctx = AppContext.bootstrap()
    return ctx


def _fmt_decision(sym: str, tf: str, dec: dict) -> str:
    """把 stage2 decision 拼成完整对话回复（含理由/置信度/关键因素/观察点/风险）。"""
    order_type = dec.get("order_type") or "?"
    direction = dec.get("order_direction") or "—"
    head = f"📊 {sym} {tf} 分析完成\n决策：{order_type}（{direction}）"
    if dec.get("entry_price") or dec.get("take_profit_price"):
        entry = dec.get("entry_price") or "—"
        tp = dec.get("take_profit_price") or dec.get("take_profit_price_2") or "—"
        sl = dec.get("stop_loss_price") or "—"
        head += f"\n入场：{entry}｜止盈：{tp}｜止损：{sl}"
    lines = [head]
    reasoning = (dec.get("reasoning") or "").strip()
    if reasoning:
        lines.append("理由：" + (reasoning if len(reasoning) <= 260 else reasoning[:260] + "…"))
    diag_c = dec.get("diagnosis_confidence")
    trade_c = dec.get("trade_confidence")
    if diag_c is not None or trade_c is not None:
        lines.append(f"置信度：诊断 {diag_c or '—'}% ｜ 交易 {trade_c or '—'}%")
    for label, key in (("关键因素", "key_factors"), ("观察点", "watch_points")):
        items = dec.get(key) or []
        if items:
            lines.append(label + "：")
            for it in items[:4]:
                lines.append("· " + str(it)[:120])
    risk = (dec.get("risk_assessment") or "").strip()
    if risk:
        lines.append("风险：" + (risk if len(risk) <= 180 else risk[:180] + "…"))
    lines.append("回复「追问 <问题>」可继续对话")
    return "\n".join(lines)


def _bar_ts_label(record, timeframe: str = "") -> str:
    """分析基准柱（record.kline_data[0]=最近已收盘，newest-first）时间标注，供信号消息辨时效。

    2026-10-04 检修：基准柱 ts_open 是 K 线**开盘**时间（binance 数组 [0]），
    文案写「收盘K线」须用收盘时间 = 开盘 + 周期（15m→+15min），否则错位一个周期。
    """
    try:
        kd = getattr(record, "kline_data", None) or []
        if kd:
            period_s = _TF_PERIOD_S.get(timeframe or "", 3600)
            ts = (int(kd[0]["ts_open"]) + period_s * 1000) / 1000
            return "（基于 %s 收盘K线）" % time.strftime("%m-%d %H:%M", time.localtime(ts))
    except Exception:  # noqa: BLE001
        pass
    return ""


def handle_message(chat_id: str, text: str) -> str:
    """处理一条飞书消息，返回回复文本（发送由调用方用 send_chat_text 完成）。"""
    kind, payload = route_text(text)
    if kind == "ignore":
        return ""
    if kind == "unknown":
        # P0-3（2026-10 用户审查修正）：未匹配 → 单轮 dialog（非静默、非提示语）。
        # 直接 ctx.client.chat 单轮回答，不用 FreeChatSession（那是多轮追问用的，需锚点）。
        # LLM 失败才落免费提示语兜底；DRY_RUN 门在 ws_bot 层已拦 analyze/followup，dialog 同样拦。
        if not budget_reserve(chat_id):  # per-chat 20 次/日，全局 300 次/日（包月计次）
            return "今日 AI 对话次数已用完，请明天再试或使用指令：\n- 分析 <币种>（如：分析 XRPUSDT）"
        try:
            ctx = _assemble_context()
            reply = ctx.client.chat([
                {"role": "system", "content": "你是 PA_Agent 助手，简洁回答用户问题。交易指令请用：分析 <币种>，如 分析 XRPUSDT。"},
                {"role": "user", "content": payload},
            ])
            content = getattr(reply, "content", None) or str(reply)
            text = content.strip() or "（空回复）"
            # 若刚发生 provider fallback（dhap→商汤配额/熔断），末尾附一次提示
            flag = pop_fallback_flag()
            if flag:
                text += f"\n\n（已切至商汤额度：{flag.get('from')}→{flag.get('to')}，触发={flag.get('trigger')}）"
            return text
        except Exception as exc:  # noqa: BLE001
            budget_release(chat_id)  # LLM 失败回滚预扣（P0-新-1）
            return f"没看懂，且 AI 对话暂不可用：{exc}\n支持：\n- 分析 <币种>（如：分析 XRPUSDT）\n- 追问 <问题>（对最近一次分析追问）\n- 帮助"
    if kind == "help":
        return "PA Agent 对话投策：\n- 分析 <SYMBOL>：跑完整两阶段分析（如：分析 XRPUSDT）\n- 追问 <问题>：对最近一次分析追问（如：追问 止损放哪里合适）"
    if kind == "track":
        sym, tf = payload
        reply = _register_track(chat_id, sym, tf)
        # 建立基线：注册即首跑一次；有信号附完整决策，无信号只回确认
        try:
            from pa_agent.scheduler import run_analysis
            record = run_analysis(sym, tf, 200, verbose=False)
            _last_record_by_chat[chat_id] = record
            dec = (getattr(record, "stage2_decision", None) or {}).get("decision") or {}
            if _track_signal(dec):
                # 首跑回复（用户主动请求必回）同时占去重位，防注册后周期内巡检重复推同方向
                _signal_push_ok(chat_id, sym, tf, dec, time.time())
                return reply + "\n\n" + _fmt_decision(sym, tf, dec) + _bar_ts_label(record, tf)
        except Exception as exc:  # noqa: BLE001
            return reply + f"\n（首次分析失败：{exc}，下个周期自动重试）"
        return reply
    if kind == "track_stop":
        return _stop_track(chat_id, payload)
    if kind == "analyze":
        sym, tf = payload
        try:
            from pa_agent.scheduler import run_analysis
            record = run_analysis(sym, tf, 200, verbose=False)
            _last_record_by_chat[chat_id] = record
            if len(_last_record_by_chat) > 50:  # 内存护栏：只保留最近 50 个 chat 的记录
                for _old in list(_last_record_by_chat)[:-50]:
                    del _last_record_by_chat[_old]
            dec = (getattr(record, "stage2_decision", None) or {}).get("decision") or {}
            return _fmt_decision(sym, tf, dec)
        except Exception as exc:  # noqa: BLE001
            return f"分析失败：{exc}"
    if kind == "followup":
        _last_record = _last_record_by_chat.get(chat_id)
        if _last_record is None:
            return "还没有可追问的分析。先发「分析 XRPUSDT」生成一次分析。"
        try:
            ctx = _assemble_context()
            from pa_agent.orchestrator.free_chat import FreeChatSession
            from pa_agent.util.threading import CancelToken
            session = FreeChatSession(
                base_record=_last_record,
                client=ctx.client,
                assembler=ctx.assembler,
                pending_writer=ctx.pending_writer,
                ledger=ctx.ledger,
                settings=ctx.settings,
            )
            reply = session.send(payload, CancelToken())
            content = getattr(reply, "content", None) or str(reply)
            return content
        except Exception as exc:  # noqa: BLE001
            return f"追问失败：{exc}"
    return ""


def track_sweep(now: float | None = None) -> list:
    """追踪巡检：对到点的 (chat, sym, tf) 跑一次分析；有明确信号推飞书。

    由 ws_bot 的 track-watch 线程每 60s 调用（随 bot 同生死，无追踪 no-op 零成本）。
    锁内取到期项 → 锁外跑 LLM（不阻塞后续扫描）。返回本批执行清单。
    """
    now = now if now is not None else time.time()
    due: list = []
    with _tracks_lock:
        for c, d in list(_tracks.items()):
            for s, t in list(d.items()):
                if now - _last_run.get((c, s, t), 0.0) >= _TF_PERIOD_S.get(t, 3600):
                    _last_run[(c, s, t)] = now
                    due.append((c, s, t))
    executed = []
    for c, s, t in due:
        try:
            from pa_agent.scheduler import run_analysis
            record = run_analysis(s, t, 200, verbose=False)
            dec = (getattr(record, "stage2_decision", None) or {}).get("decision") or {}
            if _track_signal(dec) and _signal_push_ok(c, s, t, dec, now):
                from pa_agent.notify.feishu_notifier import send_chat_text
                send_chat_text("🎯 追踪信号 " + s + " " + t + _bar_ts_label(record, t) + "\n"
                             + _fmt_decision(s, t, dec)
                             + "\n⚠️ 仅参考，非交易指令，操作请自行判断", c)
            executed.append((c, s, t))
        except Exception as exc:  # noqa: BLE001
            logger.warning("追踪巡检 %s %s 失败: %s", s, t, exc)
            _last_run.pop((c, s, t), None)  # 失败下周期重试
    return executed
