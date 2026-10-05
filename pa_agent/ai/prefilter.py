# -*- coding: utf-8 -*-
"""Prefilter: TA 模式预筛门（数据驱动门槛，2026-10-01 离线统计 325 决策定标）。

设计：stage1 诊断（detected_patterns / entry_setup_type / climax_risk）→ 判定。
- A 档（高信号放行）：ail（样本外 17.4% 泛化成立）——命中即标记 high
- B 档（低信号标记）：l2 / reversal_attempt / overlap / middle_range（n>=30 且旧数据
  <=5%），样本外 6.3% 不足以防行 -> 仅标记，enforce 暂缓
- 灰区（其余 tag）/ 无 tag：默认放行（灰区单独出现全量 19.4%、样本外 n=7 不可靠；
  B+灰 共现 4.0% 但拦 B 损失样本外 60% 信号——业务上不可行）

默认 report_only=True：只记录判定（records/execution_log/prefilter_report.jsonl），
不实际拦截 —— 观察期并行收集「预筛判定 vs LLM 实际信号」。enforce 前置条件：
样本外 B 组防行验证（<=5%）+ A 组信号率 >=12% 同时成立，10-07 数据复核。

样本标注（n<30 门槛剔除）：h3 n=10 / ioi n=8 / bull_gap n=5 / MTR n=1。
climax_risk=triggered 全量 10%（n=3）→ 不纳入禁行。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── 数据驱动门槛（2026-10-01 样本外验证定标；观察期每 7 天复核）────────────
# 样本外验证（前200 选门槛 → 后125 验证，Clopper-Pearson 口径）：
#   A(ail): 旧数据 15.6% -> 样本外 17.39% 泛化成立
#   B(l2/reversal_attempt/overlap/middle_range): 旧数据 <=5% -> 样本外 6.3%
#     不足以防行（拦 B 会损失样本外 60% 信号）-> enforce 暂缓，仅 report-only 观察
#   n<30 的 tag（h3/ioi/bull_gap/h1/breakout_pullback 等）均未达统计门槛，剔除
GATE_A_TAGS: frozenset[str] = frozenset({"ail"})
GATE_B_TAGS: frozenset[str] = frozenset({
    "l2", "reversal_attempt", "overlap", "middle_range",
})
# entry_setup_type 兜底档（detected_patterns 为空时用；est 未进 detected 时）
# A: H1 18.2% / H2 6.5% / breakout_pullback 15.8% —— 但 H2 样本外不足，观察期复核
# B: L2 0% / L1 0% / MTR 0% / wedge 0%（全量，L1 n=27 接近 30）
GATE_A_EST: frozenset[str] = frozenset({"h1", "h2", "breakout_pullback"})
GATE_B_EST: frozenset[str] = frozenset({"mtr", "wedge", "l2", "l1"})

#: 判定报告（JSONL 追加；观察期对比数据源）
REPORT_PATH: Path = (
    Path(__file__).resolve().parents[2] / "records" / "execution_log" / "prefilter_report.jsonl"
)

#: fail-open 累计计数（evaluate 异常静默放行时 bump；>=3 次告警）
_fail_open_count = 0


def bump_fail_open() -> int:
    """记录一次 fail-open（预筛异常放行），返回累计次数。"""
    global _fail_open_count
    _fail_open_count += 1
    return _fail_open_count


def _norm_tags(raw: Any) -> set[str]:
    if isinstance(raw, list):
        return {str(t).strip().lower() for t in raw if isinstance(t, str) and t.strip()}
    return set()


def evaluate(stage1_json: dict[str, Any], *, report_only: bool = True) -> dict[str, Any]:
    """判定 stage1 诊断是否放行 stage2。

    返回 dict：
      verdict: "pass" | "block"
      matched_a / matched_b: 命中的 tag 列表（排序）
      est: entry_setup_type 原文
      climax: climax_risk 原文
      basis: 判定依据（"tags" | "est_fallback" | "none"）
      report_only: 调用侧是否只记录（不拦截）
    """
    if not isinstance(stage1_json, dict):
        return _verdict("pass", [], [], "none", "none", "none", report_only)

    tags = _norm_tags(stage1_json.get("detected_patterns"))
    ba = stage1_json.get("bar_analysis")
    est = str((ba.get("entry_setup_type") or "none")).lower() if isinstance(ba, dict) else "none"
    climax = str(stage1_json.get("climax_risk") or "none").lower()

    matched_a = sorted(tags & GATE_A_TAGS)
    matched_b = sorted(tags & GATE_B_TAGS)

    if tags:
        # A 优先：同时命中 A/B 时放行（入场结构 + 环境标签共存，交 LLM 裁决）
        if matched_b and not matched_a:
            return _verdict("block", matched_a, matched_b, est, climax, "tags", report_only)
        return _verdict("pass", matched_a, matched_b, est, climax, "tags", report_only)

    # est 兜底（无 tag 时）
    if est in GATE_B_EST:
        return _verdict("block", [], [], est, climax, "est_fallback", report_only)
    if est in GATE_A_EST:
        return _verdict("pass", [est], [], est, climax, "est_fallback", report_only)
    return _verdict("pass", [], [], est, climax, "none", report_only)


def _verdict(
    verdict: str,
    matched_a: list[str],
    matched_b: list[str],
    est: str,
    climax: str,
    basis: str,
    report_only: bool,
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "matched_a": matched_a,
        "matched_b": matched_b,
        "est": est,
        "climax": climax,
        "basis": basis,
        "report_only": report_only,
    }


def append_report(row: dict[str, Any]) -> None:
    """追加一行判定报告（失败静默，不阻塞主流程）。"""
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with REPORT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def fail_open_count() -> int:
    """当前 fail-open 累计次数（供 two_stage 插桩处告警判断）。"""
    return _fail_open_count
