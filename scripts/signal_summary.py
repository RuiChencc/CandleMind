# -*- coding: utf-8 -*-
# 7 天观察统计工具：signal_summary.py
# 输出指标（用户审查③要的三数）：
#   1) 信号密度：窗口内 pending 决策 order_direction != 不下单 的次数 / 总量
#   2) 成交回报：executor 真实下单 + SL 挂单（audit 中 orderId/sl_order_id 非空）次数
#   3) LLM 成本估算：轮次数 × ¥0.07/币 单价（从 run_cycle/bypass 窗口日志估）
# 用法：python scripts/signal_summary.py [--days 7] [--symbol XRPUSDT,ADAUSDT]
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # GBK 控制台 ¥ 兼容

ROOT = Path(__file__).resolve().parent.parent
COST_PER_CYCLE = 0.14  # 2 币 × ¥0.07/币（调频后 1h 驱动口径）

def load_pending(window_days):
    files = sorted((ROOT / "records" / "pending").glob("*.json"))
    cutoff = time.time() - window_days * 86400
    rows = []
    for f in files:
        try:
            rec = json.load(open(f, encoding="utf-8"))
            meta = rec.get("meta") or {}
            ts = float(meta.get("timestamp_local_ms") or 0) / 1000
            if not ts or ts < cutoff:
                continue
            dec = ((rec.get("stage2_decision") or {}).get("decision") or {})
            rows.append({
                "file": f.name, "symbol": meta.get("symbol") or "?",
                "ts": ts, "stance": meta.get("decision_stance") or "",
                "direction": dec.get("order_direction") or "",
                "order_type": dec.get("order_type") or "",
            })
        except Exception:
            continue
    return rows

def load_audit():
    """executor 审计（AuditLog.snapshot 合并口径）：真实下单 = 有 venue_order_id；
    挂 SL = 有 sl_order_id。禁直接读 JSONL 原文（correction 行会重复计数）。"""
    sys.path.insert(0, str(ROOT))
    try:
        from pa_agent.execution.audit_log import AuditLog
        return AuditLog().snapshot()
    except Exception:
        return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()
    pend = load_pending(a.days)
    if not pend:
        print("窗口内无 pending 决策（可能无分析或时间在窗口外）")
    else:
        n = len(pend)
        sig = [r for r in pend if r["direction"] and r["order_type"] != "不下单"]
        by_sym = Counter(r["symbol"] for r in pend)
        sig_sym = Counter(r["symbol"] for r in sig)
        print(f"== 1) 信号密度（{a.days}天窗口）==")
        for s, c in sorted(by_sym.items()):
            print(f"  {s}: 决策 {c} 次 / 有信号 {sig_sym.get(s, 0)} 次 / 信号率 {sig_sym.get(s,0)/c:.1%}")
        print(f"  合计: 决策 {n} / 有信号 {len(sig)} / 信号率 {len(sig)/n:.1%}")
        for r in sig[:8]:
            print(f"    SIGNAL {r['file']}: {r['direction']} {r['order_type']}")
    aud = load_audit()
    placed = [r for r in aud if r.get("venue_order_id")]
    sl = [r for r in aud if r.get("sl_order_id")]
    # 观察通道试验单：net_rr < MIN_NET_RR(1.5) 而仍下单 = 接线试验（RR=1.31 手动放行类），不作策略证据
    trial = [r for r in placed if isinstance(r.get("net_rr"), (int, float)) and r.get("net_rr") < 1.5]
    strat = [r for r in placed if r not in trial]
    print(f"== 2) executor 成交回报（审计累计）==")
    print(f"  真实下单 {len(placed)} 次 / 挂 SL {len(sl)} 次 / 全部审计行 {len(aud)}")
    if trial:
        print(f"  ⚠ 其中 {len(trial)} 次为观察通道试验单（net_rr<1.5），不作策略证据：")
        for r in trial:
            print(f"    TRIAL {r.get('record_id','?')[:20]}: net_rr={r.get('net_rr')} status={r.get('status')}")
    for r in strat[-5:]:
        print(f"    ORDER {r.get('record_id','?')[:20]}: status={r.get('status')} sl_status={r.get('sl_status')}")
    print(f"== 3) LLM 成本估算 ==")
    # 过去已发生：以窗口内决策行数上界折算（真实轮次可能更多——部分轮次产出'不下单'仍计费）
    n_cycles = len(pend) // 2 + (1 if len(pend) % 2 else 0)  # 每 cycle 2 币
    print(f"  过去(窗口已发生,上界): 决策 {len(pend)} 个 ≈ {n_cycles} 轮 × ¥0.14 ≈ ¥{n_cycles*COST_PER_CYCLE:.2f} "
          f"(其中 {len(pend)} 决策混合了历史 5m/15m/1h 时代,非纯 1h 口径)")
    # 未来 7 天预期：1h 驱动 24 轮/天 × 7 天 = 168 轮（K 线驱动每周期仅 1 次分析）
    expected = 24 * 7 * COST_PER_CYCLE
    print(f"  未来(1h 驱动 7 天预期): 24轮/天 × 7天 = 168 轮 × ¥0.14 ≈ ¥{expected:.2f} "
          f"(¥{expected/7:.2f}/天)")

if __name__ == "__main__":
    sys.exit(main())
