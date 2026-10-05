# -*- coding: utf-8 -*-
"""scheduler.py — 最小调度层（Phase 3 起点）：让 PA_Agent 自动分析币安标的并落 pending。

用法：
  python -m pa_agent.scheduler --symbol XRPUSDT --timeframe 1h --bars 200

职责（审查 P0 项）：拉币安 K 线 → 构造 KlineFrame → TwoStageOrchestrator.submit
（内部自动 save_full 落 records/pending）→ 供 executor 消费。
本模块不设定时器（铁律"不启守护"）；定时由外部任务计划器按需调用本 CLI。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pa_agent.data.base import IndicatorBundle, KlineBar, KlineFrame  # noqa: E402
from pa_agent.indicators.atr import atr_full  # noqa: E402
from pa_agent.indicators.ema import ema_full  # noqa: E402

# 行情源：data-api.binance.vision 公网可用（2026-09-28 实测 200 OK）；
# api.binance.com 超时（墙）；testnet.binance.vision 作备。
KLINES_BASES = ("https://data-api.binance.vision", "https://testnet.binance.vision")


def fetch_klines(symbol: str, interval: str, limit: int) -> list:
    """拉币安 K 线（oldest→newest）。双源各重试 2 次（C301 ≤3 次上限内）。"""
    last_err = None
    for _attempt in range(2):
        for base in KLINES_BASES:
            try:
                url = f"{base}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as r:
                    rows = json.loads(r.read().decode())
                if rows:
                    return rows
            except Exception as exc:  # noqa: BLE001
                last_err = exc
    raise ConnectionError(f"klines 拉取失败: {last_err}")


def build_frame(symbol: str, timeframe: str, rows_oldest_first: list, *, drop_last: bool = True) -> KlineFrame:
    """币安 klines（oldest-first）→ KlineFrame（newest-first，bars[0]=最近已收盘柱）。

    2026-10-04 信号质量检修：默认丢弃最新未收盘柱（freqtrade process_only_new_candles
    原则——策略只评估已收盘 K 线）。未收盘柱 close 盘中漂移 → 同一根 K 线被多轮巡检
    反复分析出同一信号（10-03 23:27/23:43 双推根因）。drop_last=False 保留未收盘柱
    （GUI 画 forming bar 走独立通道，不经本函数）。

    rows: [openTime, open, high, low, close, volume, closeTime, quoteVol, ...]
    """
    dropped = drop_last and len(rows_oldest_first) > 1
    if dropped:
        rows_oldest_first = rows_oldest_first[:-1]
    closes = [float(r[4]) for r in rows_oldest_first]
    highs = [float(r[2]) for r in rows_oldest_first]
    lows = [float(r[3]) for r in rows_oldest_first]
    # 指标 oldest-first 计算，再反转对齐 newest-first bars
    ema20 = tuple(reversed(ema_full(closes, 20)))
    atr14 = tuple(reversed(atr_full(highs, lows, closes, 14)))
    bars = []
    for i, r in enumerate(reversed(rows_oldest_first)):
        is_newest = i == 0
        o = float(r[1]); c = float(r[4])
        bars.append(KlineBar(
            seq=i + 1,
            ts_open=int(r[0]),
            open=o, high=float(r[2]), low=float(r[3]), close=c,
            volume=float(r[5]),
            amount=float(r[7]) if len(r) > 7 else 0.0,
            pct_chg=((c - o) / o) if o else None,
            closed=True if dropped else (not is_newest),
            timestamp_is_close=False,
        ))
    return KlineFrame(
        symbol=symbol,
        timeframe=timeframe,
        bars=tuple(bars),
        indicators=IndicatorBundle(ema20=ema20, atr14=atr14),
        snapshot_ts_local_ms=int(time.time() * 1000),
    )


def symbol_exists(symbol: str) -> bool | None:
    """币安 symbol 有效性校验（exchangeInfo 查询，零 LLM 成本；B2 修复前置）。

    三态：True=存在 / False=确定不存在（HTTP 400=无效 symbol，标记为不存在）/
    None=API 故障（网络异常，放行避免误杀——交给 fetch_klines 抛真实错误）。
    """
    api_errors = 0
    for base in KLINES_BASES:
        try:
            url = f"{base}/api/v3/exchangeInfo?symbol={symbol}"
            with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as r:
                data = json.loads(r.read().decode())
            return bool(data and data.get("symbols"))
        except urllib.error.HTTPError as he:
            # HTTP 4xx（如 400 symbol not found）→ 明确的不存在信号，非故障
            return False
        except Exception:  # noqa: BLE001
            api_errors += 1
            continue
    return None if api_errors >= len(KLINES_BASES) else False


def run_analysis(symbol: str, timeframe: str, bars: int, verbose: bool = True):
    """拉 K 线 → 构造 frame → 装配 orchestrator → submit（自动落 pending）。"""
    exists = symbol_exists(symbol)
    if exists is False:
        raise ValueError(
            f"未在币安找到交易对 {symbol}，请确认 symbol（如 XRPUSDT/BTCUSDT/ETHUSDT）"
        )
    # exists is None（API 故障）→ 放行，让 fetch_klines 抛真实错误
    rows = fetch_klines(symbol, timeframe, bars)
    frame = build_frame(symbol, timeframe, rows)
    if verbose:
        print(f"frame: {symbol} {timeframe} bars={len(frame.bars)} "
              f"newest_close={frame.bars[0].close} closed={frame.bars[0].closed} "
              f"oldest_close={frame.bars[-1].close} closed={frame.bars[-1].closed}")

    from pa_agent.ai.client_factory import create_ai_client
    from pa_agent.ai.json_validator import JsonValidator
    from pa_agent.ai.prompt_assembler import PromptAssembler
    from pa_agent.ai.router import route_strategy_files
    from pa_agent.config.paths import (EXPERIENCE_DIR, PROMPT_DIR,
                                        RECORDS_PENDING_DIR, SETTINGS_JSON_PATH)
    from pa_agent.config.settings import load_settings
    from pa_agent.orchestrator.two_stage import TwoStageOrchestrator
    from pa_agent.records.experience_reader import ExperienceReader
    from pa_agent.records.pending_writer import PendingWriter
    from pa_agent.util.threading import CancelToken

    settings = load_settings(SETTINGS_JSON_PATH)
    client = create_ai_client(settings.provider)
    exp_reader = ExperienceReader(experience_dir=EXPERIENCE_DIR)
    assembler = PromptAssembler(prompt_dir=PROMPT_DIR, experience_reader=exp_reader,
                                prompt_settings=settings.prompt)
    validator = JsonValidator(settings)
    pending_writer = PendingWriter(pending_dir=RECORDS_PENDING_DIR,
                                   api_key=settings.provider.api_key)
    orchestrator = TwoStageOrchestrator(client, assembler, route_strategy_files, validator,
                                        pending_writer, exp_reader, settings)
    record = orchestrator.submit(frame, CancelToken(), on_event=lambda e: None)
    st1 = getattr(record, "stage1", None) or {}
    gate = st1.get("gate_result") if isinstance(st1, dict) else getattr(st1, "gate_result", None)
    dec = (getattr(record, "stage2_decision", None) or {}).get("decision") or {}
    rid = getattr(record, "record_id", None)
    # record_id 不在 AnalysisRecord 模型上，语义 = pending_writer._build_basename(record)：
    # {本地时间串}_{symbol}_{timeframe}。record.meta 派生，对齐 audit_log.derive_signal_id 输入。
    _meta = getattr(record, "meta", None)
    if rid is None and _meta is not None:
        try:
            from datetime import datetime
            rid = datetime.fromtimestamp(_meta.timestamp_local_ms / 1000).strftime("%Y-%m-%d_%H-%M-%S") + f"_{_meta.symbol}_{_meta.timeframe}"
        except Exception:  # noqa: BLE001
            pass
    print(f"record: id={rid} gate={gate}")
    print(f"decision: {json.dumps(dec, ensure_ascii=False)[:220]}")
    # A: 决策持久化（2026-10 验收轮）——供 scripts/offline_backtest.py 消费。
    # 旁路写入：任何异常不阻断分析主流程（决策日志失败 ≠ 分析失败）。
    try:
        _log_dir = Path(__file__).resolve().parent.parent / "records" / "decision_log"
        _log_dir.mkdir(parents=True, exist_ok=True)
        _log_path = _log_dir / f"decision_{time.strftime('%Y%m%d')}.jsonl"
        _entry = {
            "ts": time.time(),
            "record_id": rid,
            "symbol": symbol,
            "timeframe": timeframe,
            "gate": gate,
            "direction": dec.get("order_direction"),
            "order_type": dec.get("order_type"),
            "confidence": dec.get("trade_confidence"),
            "entry": dec.get("entry_price"),
            "stop": dec.get("stop_loss_price"),
            "tp1": dec.get("take_profit_price"),
            "tp2": dec.get("take_profit_price_2"),
            "model": getattr(settings.provider, "model", None),
        }
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(_entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 旁路
        pass
    return record


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="PA_Agent 最小调度层（手动 CLI，非定时器）")
    ap.add_argument("--symbol", default="XRPUSDT")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--bars", type=int, default=200)
    args = ap.parse_args(argv)
    run_analysis(args.symbol, args.timeframe, args.bars)


if __name__ == "__main__":
    main()
