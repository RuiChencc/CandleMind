# -*- coding: utf-8 -*-
"""方向正确率回测（历史决策假设收益验证，零 LLM 成本）。

用法: python scripts/backtest_direction_accuracy.py [--window-hours 24]
数据: records/pending/*.json 中带完整价格字段（entry/stop/tp1/tp2）的 crypto 决策
行情: data-api.binance.vision 现货 klines（本地 = UTC+8，已验证对齐）
模拟: 决策时刻后 window-hours 内，先触 tp1 -> +R1，先触 stop -> -1R，超时 -> 0R
"""
import json
import os
import sys
import argparse
import glob
import urllib.request
import datetime
from collections import defaultdict

BAR_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000}
TZ_SHIFT_MS = 8 * 3600 * 1000  # local(UTC+8) -> UTC
DATA_API = "https://data-api.binance.vision/api/v3/klines"


def get_klines(symbol: str, interval: str, start_ms: int, limit: int = 500):
    url = f"{DATA_API}?symbol={symbol}&interval={interval}&startTime={start_ms}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def simulate(decision: dict, klines: list, target: str = "tp1", strict_tp1: bool = False) -> tuple:
    """返回 (R, 结局, 时间线)。target=tp1: 先触tp1 => +R1；target=tp2: 先触tp2 => +R2
    （tp2 模式下 tp1 先触不结算，只记时间线；任模式先触 stop => -1.0；超时 => 0.0）
    strict_tp1(P0-1 假胜语义): tp1 先触不立即结算，窗口内再触 stop => -1.0(实亏)；未再触 => +R1。"""
    events = []
    if decision["dir"] == "bullish":
        hit_sl = lambda k: float(k[3]) <= decision["stop"]
        hit_t1 = lambda k: float(k[2]) >= decision["tp1"]
        hit_t2 = lambda k: float(k[2]) >= decision["tp2"]
        r1 = (decision["tp1"] - decision["entry"]) / (decision["entry"] - decision["stop"])
        r2 = (decision["tp2"] - decision["entry"]) / (decision["entry"] - decision["stop"])
    else:
        hit_sl = lambda k: float(k[2]) >= decision["stop"]
        hit_t1 = lambda k: float(k[3]) <= decision["tp1"]
        hit_t2 = lambda k: float(k[3]) <= decision["tp2"]
        r1 = (decision["entry"] - decision["tp1"]) / (decision["stop"] - decision["entry"])
        r2 = (decision["entry"] - decision["tp2"]) / (decision["stop"] - decision["entry"])
    t_start = decision["ts_ms"] - TZ_SHIFT_MS
    if strict_tp1 and target == "tp1":
        # P0-1: tp1 先触不立即结算；窗口内再触 stop => -1.0(实亏)；未再触 => +R1
        tp1_seen = False
        for k in klines:
            if k[0] < t_start:
                continue
            if hit_sl(k):
                if tp1_seen:
                    return -1.0, "假胜(tp1后止损)", events + [("stop", k[0])]
                return -1.0, "先触止损", events + [("stop", k[0])]
            if hit_t1(k) and not tp1_seen:
                tp1_seen = True
                events.append(("tp1", k[0]))
        if tp1_seen:
            return r1, "tp1活胜", events
        return 0.0, "窗口未触", events
    for k in klines:
        if k[0] < t_start:
            continue
        if hit_sl(k):
            return -1.0, "先触止损", events + [("stop", k[0])]
        if hit_t1(k):
            if target == "tp1":
                return r1, "先触tp1", events + [("tp1", k[0])]
            events.append(("tp1", k[0]))  # tp2 模式: 只记不结算
        if hit_t2(k):
            return r2, "先触tp2", events + [("tp2", k[0])]
    return 0.0, "窗口未触", events


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=float, default=24.0)
    ap.add_argument("--target", choices=["tp1", "tp2", "both"], default="tp1",
                    help="判定目标: tp1(1:1 R, 默认)/tp2(2:1+ R)/both(打印触达时间线)")
    ap.add_argument("--strict-tp1", action="store_true",
                    help="P0-1 假胜语义: tp1 先触后窗口内再触 stop => -1.0(实亏)")
    ap.add_argument("--pending-dir", default=r"D:\OpenCode\projects\PA_Agent\records\pending")
    args = ap.parse_args()
    window_ms = int(args.window_hours * 3600 * 1000)

    files = sorted(glob.glob(os.path.join(args.pending_dir, "*.json")))
    decs = []
    for f in files:
        if "异常" in os.path.basename(f):
            continue
        d = json.load(open(f, encoding="utf-8"))
        m = d.get("meta") or {}
        sym = str(m.get("symbol") or "")
        if not sym.endswith("USDT"):
            continue  # 只验证 crypto（A 股历史决策非当前方向）
        s1 = d.get("stage1_diagnosis") or {}
        dirn = (s1.get("direction") or "neutral") if isinstance(s1, dict) else "neutral"
        if dirn not in ("bullish", "bearish"):
            continue
        s2 = d.get("stage2_decision") or {}
        dec = s2.get("decision") or {} if isinstance(s2, dict) else {}
        if not (dec.get("entry_price") and dec.get("stop_loss_price") and dec.get("take_profit_price")):
            continue
        decs.append({
            "sym": sym, "tf": str(m.get("timeframe")), "ts_ms": int(m.get("timestamp_local_ms") or 0),
            "dir": dirn, "entry": float(dec["entry_price"]), "stop": float(dec["stop_loss_price"]),
            "tp1": float(dec["take_profit_price"]),
            "tp2": float(dec.get("take_profit_price_2") or 0) or float(dec["take_profit_price"]),
        })
    if not decs:
        print("无可验证决策（crypto + 完整价格字段）")
        return
    print(f"可验证决策: {len(decs)}")
    results = []
    for d in decs:
        bar = BAR_MS.get(d["tf"])
        if not bar:
            results.append((d, 0.0, f"tf={d['tf']} 无K线间隔"))
            continue
        limit = min(500, int(window_ms / bar) + 2)
        try:
            kl = get_klines(d["sym"], d["tf"], d["ts_ms"] - TZ_SHIFT_MS - bar, limit)
            r, why, evts = simulate(d, kl, args.target, strict_tp1=args.strict_tp1)
            results.append((d, r, why, evts))
        except Exception as e:
            results.append((d, 0.0, f"拉数失败 {type(e).__name__}: {e}", []))
    for d, r, why, evts in results:
        print(f"  {d['sym']:9s} {d['tf']:3s} {d['dir']:7s} entry={d['entry']:.4f} -> R={r:+.2f} ({why})")
        if args.target == "both" and evts:
            for ev, t in evts:
                print(f"      {datetime.datetime.utcfromtimestamp(t/1000)} [{ev}]")
    settle = "tp2" if args.target in ("tp2", "both") else "tp1"
    wins = sum(1 for _, r, _, _ in results if r > 0)
    avg = sum(r for _, r, _, _ in results) / len(results)
    print(f"\n方向正确率({settle}结算): {100.0*wins/len(results):.1f}%  ({wins}/{len(results)})  平均R: {avg:+.2f}")
    by_dir = defaultdict(list)
    for d, r, _, _ in results:
        by_dir[d["dir"]].append(r)
    for k, rs in by_dir.items():
        print(f"  {k}: n={len(rs)} 平均R={sum(rs)/len(rs):+.2f} 胜率={100.0*sum(1 for x in rs if x>0)/len(rs):.0f}%")


if __name__ == "__main__":
    main()
