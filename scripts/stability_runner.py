# -*- coding: utf-8 -*-
"""stability_runner.py — B 步：固定同一 KlineFrame × N 次采样，量化 LLM 决策随机性。

与 offline_backtest.py 的区别：
  - offline_backtest：读历史 decision_log（不同时刻不同 frame）→ 历史分布，非稳定性
  - stability_runner：同一次 fetch 的同一 rows 重建 frame，喂 orchestrator N 次 →
    方向一致率 / conf 均值±std = LLM 随机性（io=552 同 frame 跑 3 次的原型自动化）

用法：
  python scripts/stability_runner.py --symbol XRPUSDT --tf 1h --bars 200 --n 5
成本：N=5 ≈ ¥0.09（dhap 计次）；每轮独立两阶段 LLM 调用，无状态共享。
输出：方向分布 / 一致率（众数占比）/ confidence mean±std。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PA_Agent 同 frame 稳定性采样")
    ap.add_argument("--symbol", default="XRPUSDT")
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--bars", type=int, default=200)
    ap.add_argument("--n", type=int, default=5)
    args = ap.parse_args(argv)

    # 1) 只 fetch 一次：同一 rows 反复重建 frame = 严格同输入
    from pa_agent.scheduler import build_frame, fetch_klines, symbol_exists

    exists = symbol_exists(args.symbol)
    if exists is False:
        print(f"未在币安找到交易对 {args.symbol}"); return 1
    rows = fetch_klines(args.symbol, args.tf, args.bars)
    if not rows:
        print("klines 为空"); return 1

    # 2) 一次装配 orchestrator（同 scheduler.run_analysis 内联）
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

    # 3) N 次 submit 同一 frame（每轮 build_frame 同输入 → 固定）
    results = []
    for i in range(args.n):
        tick = time.time()
        frame = build_frame(args.symbol, args.tf, rows)
        record = orchestrator.submit(frame, CancelToken(), on_event=lambda e: None)
        dec = (getattr(record, "stage2_decision", None) or {}).get("decision") or {}
        direction = dec.get("order_direction")
        order_type = dec.get("order_type")
        conf = dec.get("trade_confidence")
        results.append({"i": i, "direction": direction, "order_type": order_type,
                        "conf": conf})
        print(f"[{i+1}/{args.n}] direction={direction} order_type={order_type} "
              f"conf={conf} ({time.time()-tick:.1f}s)", flush=True)

    # 4) 汇总
    dirs = [(r["direction"] or r["order_type"] or "noop") for r in results]
    cnt = Counter(dirs)
    top = cnt.most_common(1)[0]
    agree = top[1] / len(results) * 100.0
    confs = [r["conf"] for r in results if r["conf"] is not None]
    print("\n===== stability summary =====")
    print(f"symbol={args.symbol} {args.tf} bars={args.bars} n={args.n}")
    print(f"方向分布: {dict(cnt)}")
    print(f"方向一致率: {agree:.0f}% (众数={top[0]})")
    if len(confs) >= 2:
        print(f"confidence: mean={statistics.mean(confs):.1f} "
              f"std={statistics.stdev(confs):.1f} (n={len(confs)})")

    # 5) 落盘一份原始采样供后续复用
    out_dir = Path(__file__).resolve().parent.parent / "records" / "decision_log"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"stability_{args.symbol}_{args.tf}_{int(time.time())}.json"
    out_path.write_text(json.dumps({
        "symbol": args.symbol, "tf": args.tf, "bars": args.bars, "n": args.n,
        "agree_pct": round(agree, 1), "mode": top[0],
        "conf_mean": (statistics.mean(confs) if confs else None),
        "conf_std": (statistics.stdev(confs) if len(confs) >= 2 else None),
        "runs": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
