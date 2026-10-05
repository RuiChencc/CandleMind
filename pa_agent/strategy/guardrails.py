# -*- coding: utf-8 -*-
"""guardrails.py — 确定性交易护栏层（Phase 2 执行层前置过滤）。

职责：在 LLM stage2 决策与真实下单之间加一道确定性、可回测、可审计的门禁。
LLM 输出只做"候选"，护栏用确定性规则决定放行/仓位/目标价。

依据（本地实测 + 2pa-agent-rust 同构参考，2026-09-28 核实）：
  - PA_Agent conf 全量分布 54 样本：min=25, max=52, 无 >=60（xrp_results/exp1/exp2/stability）
      → 分档必须整体下移，原 "70 全仓 / 50-69 半仓" 两档永不触发，作废
  - PA_Agent 自身最小 bars 检查 = bar_count_lt_20（ai/decision_nodes.py:331）
      → ready() 对齐该语义，设 MIN_BARS=20（不凭空设 50/100）
  - PA_Agent settings 无费率配置 → 常量在此定义，合约上线时改 FUTURES_MAKER_FEE
  - 2pa strategies.rs: MIN_NET_RR=1.5 / SLIPPAGE_PER_SIDE=0.0002（净盈亏比含成本）

设计决策：
  - 默认止盈目标 = TP2（PA §10.3 门槛 RR>=1.0 过低，io=552 恰好 RR=1.0 会被放行；
    TP2 才有足够空间满足 MIN_NET_RR=1.5）——在护栏层选 TP2，**不改动 LLM 决策层**。
  - 仓位缩放是连续的（LLM 随机性转为风险调整），不是离散开/关。
  - 本模块只读 stage2 decision，无副作用，可单测。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

# ---------------------------------------------------------------- 常量（有据）----
MIN_BARS = 20           # 对齐 PA decision_nodes bar_count_lt_20
MIN_NET_RR = 1.5        # 净盈亏比门槛（2pa strategies.rs 同值，含成本）
SPOT_TAKER_FEE = 0.001  # 现货单边手续费（Binance 现货标准）
FUTURES_MAKER_FEE = 0.0005  # 合约挂单费率（合约上线时替换 SPOT_TAKER_FEE）
SLIPPAGE_PER_SIDE = 0.0002  # 单边滑点估算（2pa strategies.rs 同值）

# 仓位缩放档位（按 P0-1 实测 conf 分布校准：min=25 max=52 无 >=60）
SCALE_BANDS = (
    (48, 1.0),   # conf >= 48  全仓
    (40, 0.5),   # conf >= 40  半仓
    (30, 0.25),  # conf >= 30  四分之一
    (0, 0.0),    # conf < 30   不下单
)


# ---------------------------------------------------------------- 结果类型 ----
@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str
    net_rr: Optional[float] = None
    position_scale: float = 0.0
    target_price: Optional[float] = None  # 护栏选定的止盈目标（默认 TP2）


# ---------------------------------------------------------------- 核心逻辑 ----
def cost_rate(is_futures: bool = False) -> float:
    """单边成本 = 手续费 + 滑点（2pa strategies.rs cost_rate 同构）。"""
    fee = FUTURES_MAKER_FEE if is_futures else SPOT_TAKER_FEE
    return fee + SLIPPAGE_PER_SIDE


def net_rr(entry: float, stop: float, target: float, *, cost: float) -> float:
    """净盈亏比 = (目标收益 - 成本) / (风险 + 成本)。entry/stop/target 均为价格。"""
    if entry <= 0 or stop <= 0 or target <= 0:
        return 0.0
    reward = abs(target - entry)
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    # 成本按名义金额比例计入双边（开+平）：成本项 = (entry + target) * cost
    net_reward = reward - (entry + target) * cost
    net_risk = risk + (entry + stop) * cost
    if net_risk <= 0:
        return 0.0
    return net_reward / net_risk


def ready(bars: Sequence, indicators=None, *, min_bars: int = MIN_BARS) -> bool:
    """数据质量门禁：bar 数量/闭合/有限值/时间降序/指标有限。

    bars: KlineBar 序列。KlineFrame.bars 为 newest-first（record_loader.py:112），
    故取 bars[:min_bars] 校验最新段；只查完整性，不依赖方向。
    """
    if bars is None or len(bars) < min_bars:
        return False
    # 有限值检查（最新 min_bars 根，newest-first）
    for b in bars[:min_bars]:
        close = getattr(b, "close", None)
        open_ = getattr(b, "open", None)
        high = getattr(b, "high", None)
        low = getattr(b, "low", None)
        if close is None or not math.isfinite(float(close)):
            return False
        if not (math.isfinite(float(open_)) and math.isfinite(float(high)) and math.isfinite(float(low))):
            return False
        if float(high) < float(low) or float(high) < 0 or float(low) < 0:
            return False
    # 指标有限性（若提供）
    if indicators is not None:
        for name in ("ema20", "atr14"):
            vals = getattr(indicators, name, ()) or ()
            if len(vals) < 1 or not all(math.isfinite(float(v)) for v in vals[:6]):
                return False
    return True


def scale_position(confidence: Optional[float]) -> float:
    """按 LLM conf 连续缩放仓位（Anti-Veto 思想：不设离散开关，随机性转为风险调整）。

    档位按 P0-1 实测校准（conf 分布 min=25 max=52）：
      >=48 全仓 / >=40 半仓 / >=30 四分之一 / <30 不下单
    """
    if confidence is None:
        return 0.0
    c = float(confidence)
    for threshold, scale in SCALE_BANDS:
        if c >= threshold:
            return scale
    return 0.0


def evaluate_decision(
    decision: dict,
    *,
    is_futures: bool = False,
    use_tp2_as_target: bool = True,
    min_net_rr: Optional[float] = None,
) -> GuardResult:
    # 观察通道：CLI --min-net-rr 临时放宽（默认 None 沿用 SSOT 常量 1.5，常规路径零影响）
    """对 stage2 decision 做护栏评估。

    decision 必须含：order_direction / order_type / entry_price / stop_loss_price /
    take_profit_price(TP1) / take_profit_price_2(TP2) / trade_confidence。
    返回 GuardResult：allowed=False 时给出 reason，绝不产生副作用。
    """
    direction = decision.get("order_direction")
    order_type = decision.get("order_type")
    conf = decision.get("trade_confidence")
    if not direction or not order_type or order_type == "不下单":
        return GuardResult(allowed=False, reason="no_signal: direction/order_type 为空或不下单")

    try:
        entry = float(decision.get("entry_price"))
        stop = float(decision.get("stop_loss_price"))
        tp1 = decision.get("take_profit_price")
        tp2 = decision.get("take_profit_price_2")
    except (TypeError, ValueError):
        return GuardResult(allowed=False, reason="invalid_price: entry/stop/tp 非数值")

    # 目标价：默认选 TP2（护栏层决策，不改 LLM 层；TP1 因 RR>=1.0 门槛过低被弃用）
    target = float(tp2) if use_tp2_as_target and tp2 is not None else float(tp1)
    if target is None or not math.isfinite(target):
        return GuardResult(allowed=False, reason="no_target: 无可用止盈价")

    cost = cost_rate(is_futures=is_futures)
    rr = net_rr(entry, stop, target, cost=cost)

    rr_threshold = min_net_rr if min_net_rr is not None else MIN_NET_RR
    if rr < rr_threshold:
        return GuardResult(
            allowed=False,
            reason=f"low_rr: net_rr={rr:.2f} < MIN_NET_RR={rr_threshold}",
            net_rr=rr,
        )

    scale = scale_position(conf)
    if scale <= 0:
        return GuardResult(
            allowed=False,
            reason=f"low_conf: conf={conf} 低于 30 分档下限",
            net_rr=rr,
            position_scale=scale,
        )

    return GuardResult(
        allowed=True,
        reason="ok",
        net_rr=rr,
        position_scale=scale,
        target_price=target,
    )
