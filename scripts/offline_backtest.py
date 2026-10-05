# -*- coding: utf-8 -*-
"""offline_backtest.py — A 步产物：读 records/decision_log/*.jsonl，输出决策分布 + 一致性基线。

用途：
  - 验证埋点落盘（A 验收）
  - 给 B（stability_runner）提供同 symbol×timeframe 方向一致率的量化基线
  - 阈值不预设 80%（训练知识估值，A 跑完后按实际方差反推）

局限：本脚本统计决策分布，不含盈亏回测（拉后续 K 线模拟成交 = YAGNI，
待 decision_log 积累 ≥30 行后在 C 阶段扩展）。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "records" / "decision_log"


def load_rows(log_dir: Path = LOG_DIR) -> list[dict]:
    rows = []
    for p in sorted(log_dir.glob("decision_*.jsonl")):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    print(f"[skip] 坏行: {p.name}: {line[:60]}", file=sys.stderr)
    return rows


def main() -> int:
    rows = load_rows()
    if not rows:
        print("decision_log 为空——先跑 python -m pa_agent.scheduler 至少 1 次")
        return 1
    print(f"总决策记录: {len(rows)}")
    dirs = defaultdict(int)
    for r in rows:
        dirs[r.get("direction") or "(无)"] += 1
    print("方向分布:", dict(dirs))
    confs = [float(r["confidence"]) for r in rows if r.get("confidence") is not None]
    if confs:
        print(f"confidence: n={len(confs)} min={min(confs)} max={max(confs)} mean={sum(confs)/len(confs):.1f}")
    # 注意：这是「历史分布」（不同时刻不同 frame），不能测 LLM 随机性稳定性——
    # 不同 frame 方向本就不该一致。稳定性测试用 scripts/stability_runner.py（固定同 frame × N）。
    groups = defaultdict(list)
    for r in rows:
        groups[(r.get("symbol"), r.get("timeframe"))].append(r)
    print("\n历史分布（同 symbol×tf 方向分布，非稳定性指标）:")
    for (sym, tf), gs in sorted(groups.items()):
        if len(gs) < 2:
            continue
        counts = defaultdict(int)
        for r in gs:
            counts[r.get("direction") or "(无)"] += 1
        mode, mode_n = max(counts.items(), key=lambda kv: kv[1])
        print(f"  {sym} {tf}: n={len(gs)} 众数={mode} ({mode_n}/{len(gs)} = {mode_n/len(gs)*100:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
