# -*- coding: utf-8 -*-
"""direction_stability_scan.py — B+ 步：批量历史 frame 滑窗采样，测 LLM 方向翻转率。

与 stability_runner.py（单 frame × N）的区别：
  - stability_runner：固定当前 frame × N → LLM 随机性（同输入同 time 语义）
  - direction_stability_scan：30 天 1h 滑窗（每 STEP_H 取 200-bar 窗口）× N 次 →
    方向一致率 / 翻转 case 列表 / conf σ 分布。样本必然包含有信号窗口 → 测"翻转率"。

用法：
  python scripts/direction_stability_scan.py --days 30 --step-h 8 --n 3 --symbol XRPUSDT --tf 1h
输出：
  - 总体方向一致率（mode 占比 / case 数）
  - 不一致 case：窗口时间 + N 次方向/conf
  - 落盘 records/decision_log/scan_<ts>.json

成本：~65 帧 × 3 次 × 2 LLM 调用/次 ≈ 390 次 dhap ≈ ¥1.6（¥50/12000 次）；
时间 ≈ 3h（实测单次分析 ~60s）。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

KLINES_BASES = ("https://data-api.binance.vision", "https://testnet.binance.vision")


def fetch_klines_range(symbol: str, interval: str, start_ms: int, limit: int = 1000) -> list:
    """拉 [start_ms, +limit 根] 的 klines（oldest→newest）。双源各重试 2 次（同 fetch_klines）。"""
    last_err = None
    for _attempt in range(2):
        for base in KLINES_BASES:
            try:
                url = (f"{base}/api/v3/klines?symbol={symbol}&interval={interval}"
                       f"&startTime={start_ms}&limit={limit}")
                with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as r:
                    rows = json.loads(r.read().decode())
                if rows:
                    return rows
            except Exception as exc:  # noqa: BLE001
                last_err = exc
    raise ConnectionError(f"klines 拉取失败: {last_err}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PA_Agent 历史滑窗方向稳定性扫描")
    ap.add_argument("--symbol", default="XRPUSDT")
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--step-h", type=int, default=8)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--bars", type=int, default=200)
    args = ap.parse_args(argv)

    # 1) 单次拉取全量历史（避免重复网络）
    from pa_agent.scheduler import symbol_exists

    exists = symbol_exists(args.symbol)
    if exists is False:
        print(f"未在币安找到交易对 {args.symbol}"); return 1
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - args.days * 24 * 3600 * 1000
    rows_all = fetch_klines_range(args.symbol, args.tf, start_ms, limit=1000)
    print(f"pulled: {len(rows_all)} bars from {args.days}d window")

    # 2) 装配 orchestrator（同 scheduler.run_analysis / stability_runner）
    from pa_agent.ai.client_factory import create_ai_client
    from pa_agent.ai.json_validator import JsonValidator
    from pa_agent.ai.prompt_assembler import PromptAssembler
    from pa_agent.ai.router import route_strategy_files
    from pa_agent.config.paths import (EXPERIENCE_DIR, PROMPT_DIR,
                                        SETTINGS_JSON_PATH)
    from pa_agent.config.settings import load_settings
    from pa_agent.orchestrator.two_stage import TwoStageOrchestrator
    from pa_agent.records.experience_reader import ExperienceReader
    from pa_agent.records.pending_writer import PendingWriter
    from pa_agent.util.threading import CancelToken
    from pa_agent.scheduler import build_frame

    settings = load_settings(SETTINGS_JSON_PATH)
    client = create_ai_client(settings.provider)
    exp_reader = ExperienceReader(experience_dir=EXPERIENCE_DIR)
    assembler = PromptAssembler(prompt_dir=PROMPT_DIR, experience_reader=exp_reader,
                                prompt_settings=settings.prompt)
    validator = JsonValidator(settings)
    # 独立临时 pending，避免污染正式 records/pending（195+ 文件）
    import tempfile
    pending_dir = Path(tempfile.mkdtemp(prefix="scan_pending_"))
    pending_writer = PendingWriter(pending_dir=pending_dir,
                                   api_key=settings.provider.api_key)
    orchestrator = TwoStageOrchestrator(client, assembler, route_strategy_files, validator,
                                        pending_writer, exp_reader, settings)

    # 3) 滑窗切片采样
    step_bars = max(1, args.step_h)
    frames = []
    i = len(rows_all) - args.bars
    while i > 0:
        frames.append(i)
        i -= step_bars
    frames.reverse()
    print(f"frames: {len(frames)} (step={args.step_h}h, window={args.bars}bar)")

    results = []
    for fi, idx in enumerate(frames):
        window = rows_all[idx:idx + args.bars]
        if len(window) < args.bars:
            break
        window_ts = window[0][0]  # 窗口起始 openTime ms
        window_iso = time.strftime("%Y-%m-%d %H:%M", time.localtime(window_ts / 1000))
        dirs_this = []
        for k in range(args.n):
            tick = time.time()
            frame = build_frame(args.symbol, args.tf, window)
            record = orchestrator.submit(frame, CancelToken(), on_event=lambda e: None)
            dec = (getattr(record, "stage2_decision", None) or {}).get("decision") or {}
            direction = dec.get("order_direction")
            order_type = dec.get("order_type")
            conf = dec.get("trade_confidence")
            dirs_this.append({"direction": direction, "order_type": order_type, "conf": conf})
            print(f"[{fi+1}/{len(frames)}] {window_iso} k={k+1} dir={direction} "
                  f"type={order_type} conf={conf} ({time.time()-tick:.0f}s)", flush=True)
        results.append({"window_idx": idx, "ts_ms": window_ts, "iso": window_iso, "runs": dirs_this})

    # 4) 汇总 —— 两组一致率分别统计：
    #    dir_consistency = order_direction（long/short/None）  —— 方向层
    #    type_consistency = order_type（限价/突破/市价/不下单） —— 执行层（io=552 翻转发生层，C 判据）
    #    C 准入按 type_consistency；direction 整帧 None 不算方向反转（方向一致率按非 None 帧计）
    print("\n===== scan summary =====")
    total_runs = 0
    all_dir = []    # 每 run 的 direction 标签
    all_type = []   # 每 run 的 order_type 标签
    dir_inconsistent = []   # 方向层不一致（存在 direction 非 None 且帧内方向不同）
    type_inconsistent = []  # 执行层不一致（帧内 order_type 不同）
    for r in results:
        runs = r["runs"]
        total_runs += len(runs)
        dirs = [x["direction"] or "noop" for x in runs]
        types = [x["order_type"] or "noop" for x in runs]
        all_dir.extend(dirs)
        all_type.extend(types)
        has_dir_signal = any(x["direction"] for x in runs)
        if has_dir_signal and len(set(dirs)) > 1:
            dir_inconsistent.append({"iso": r["iso"], "dirs": dirs,
                                     "confs": [x["conf"] for x in runs]})
        if len(set(types)) > 1:
            type_inconsistent.append({"iso": r["iso"], "types": types,
                                      "confs": [x["conf"] for x in runs]})
    ctd = Counter(all_dir)
    ctt = Counter(all_type)
    topd = ctd.most_common(1)[0]
    topt = ctt.most_common(1)[0]
    agree_d = topd[1] / total_runs * 100.0 if total_runs else 0.0
    agree_t = topt[1] / total_runs * 100.0 if total_runs else 0.0
    print(f"frames={len(results)} total_runs={total_runs}")
    print(f"[direction] 分布: {dict(ctd)}  一致率(众数占比): {agree_d:.0f}% (众数={topd[0]})")
    print(f"[order_type] 分布: {dict(ctt)}  一致率(众数占比): {agree_t:.0f}% (众数={topt[0]})  ← C 准入判据")
    print(f"direction 不一致 frame: {len(dir_inconsistent)}")
    for inc in dir_inconsistent[:20]:
        print(f"  {inc['iso']} dirs={inc['dirs']} confs={inc['confs']}")
    print(f"order_type 不一致 frame: {len(type_inconsistent)}")
    for inc in type_inconsistent[:20]:
        print(f"  {inc['iso']} types={inc['types']} confs={inc['confs']}")

    # 5) 落盘
    out_dir = Path(__file__).resolve().parent.parent / "records" / "decision_log"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"scan_{args.symbol}_{args.tf}_{int(time.time())}.json"
    out_path.write_text(json.dumps({
        "symbol": args.symbol, "tf": args.tf, "days": args.days,
        "step_h": args.step_h, "n": args.n, "bars": args.bars,
        "frames": len(results), "total_runs": total_runs,
        "direction_consistency": round(agree_d, 1),
        "direction_mode": topd[0],
        "direction_distribution": dict(ctd),
        "type_consistency": round(agree_t, 1),
        "type_mode": topt[0],
        "type_distribution": dict(ctt),
        "direction_inconsistent_count": len(dir_inconsistent),
        "type_inconsistent_count": len(type_inconsistent),
        "inconsistent": type_inconsistent,  # C 判据层的不一致 case
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
