# -*- coding: utf-8 -*-
# SOP-2: A 股 17 决策日线粗模拟（akshare 日线; 分钟线拉不到 2026-07）
# 精度: 日线级判定（同日 high/low 冲突保守记止损）— 粗判方向正确性
import json, glob, sys, datetime, os, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    import akshare as ak
except ImportError:
    print("akshare 缺失"); sys.exit(1)

files = sorted([f for f in glob.glob(r"D:\OpenCode\projects\PA_Agent\records\pending\*.json") if "异常" not in os.path.basename(f)])
rows = []
for f in files:
    d = json.load(open(f, encoding="utf-8"))
    m = d.get("meta") or {}
    sym = str(m.get("symbol") or "")
    if sym.endswith("USDT"): continue
    s1 = d.get("stage1_diagnosis") or {}
    dirn = (s1.get("direction") or "neutral") if isinstance(s1, dict) else "neutral"
    if dirn not in ("bullish", "bearish"): continue
    s2 = d.get("stage2_decision") or {}
    dec = s2.get("decision") or {} if isinstance(s2, dict) else {}
    if not (dec.get("entry_price") and dec.get("stop_loss_price") and (dec.get("take_profit_price") or dec.get("take_profit_price_2"))): continue
    rows.append({"sym": sym, "tf": str(m.get("timeframe")), "ts": int(m.get("timestamp_local_ms") or 0),
        "dir": dirn, "od": dec.get("order_direction"),
        "entry": float(dec["entry_price"]), "stop": float(dec["stop_loss_price"]),
        "tp1": float(dec.get("take_profit_price") or 0), "tp2": float(dec.get("take_profit_price_2") or 0)})
print(f"A 股完整价格决策: {len(rows)}")

def daily(sym, start, end):
    # 股票(6/0/3 开头) -> 新浪源（今日实测 OK，东财被限流）
    if sym[0] in ("6", "0", "3"):
        try:
            px = "sh" if sym[0] == "6" else "sz"
            df = ak.stock_zh_a_daily(symbol=px + sym, start_date=start, end_date=end, adjust="")
            if df is not None and len(df): return df, ""
            return None, "sina empty"
        except Exception as e:
            return None, f"sina {type(e).__name__}: {str(e)[:60]}"
    # ETF/基金(5/1 开头) -> 东财 fund_etf_hist_em（限流重试）
    errs = []
    for attempt in range(3):
        try:
            df = ak.fund_etf_hist_em(symbol=sym, period="daily", start_date=start, end_date=end, adjust="")
            if df is not None and len(df): return df, ""
            errs.append("fund empty")
        except Exception as e:
            errs.append(f"fund({attempt}) {type(e).__name__}: {str(e)[:40]}")
        if attempt < 2:
            time.sleep(3.0 * (attempt + 1))
    return None, " | ".join(errs)

results = []
for r in rows:
    if not r["ts"]:
        results.append([r, "无时间戳"]); continue
    d0 = datetime.datetime.fromtimestamp(r["ts"]/1000)
    df, err = daily(r["sym"], (d0-datetime.timedelta(days=1)).strftime("%Y%m%d"), (d0+datetime.timedelta(days=40)).strftime("%Y%m%d"))
    if df is None or len(df) == 0:
        results.append([r, f"拉数失败: {err}"]); continue
    dstr = d0.strftime("%Y-%m-%d")
    bars = df[[str(x)[:10] >= dstr for x in df[df.columns[0]].astype(str)]]
    if len(bars) == 0:
        results.append([r, "决策日后无K线"]); continue
    col_h = "最高" if "最高" in bars.columns else ("high" if "high" in bars.columns else None)
    col_l = "最低" if "最低" in bars.columns else ("low" if "low" in bars.columns else None)
    if col_h is None or col_l is None:
        results.append([r, f"列名识别失败: {list(bars.columns)[:8]}"]); continue
    r1 = r2 = None
    if r["dir"] == "bullish":
        r1 = (r["tp1"]-r["entry"])/(r["entry"]-r["stop"]) if r["tp1"] and r["entry"] > r["stop"] else 0
        r2 = (r["tp2"]-r["entry"])/(r["entry"]-r["stop"]) if r["tp2"] and r["entry"] > r["stop"] else r1
        hit = None
        for _, row in bars.iterrows():
            h, l = float(row[col_h]), float(row[col_l])
            if l <= r["stop"]: hit = "stop"; break
            if r["tp2"] and h >= r["tp2"]: hit = "tp2"; break
            if h >= r["tp1"]: hit = "tp1"; break
    else:
        r1 = (r["entry"]-r["tp1"])/(r["stop"]-r["entry"]) if r["tp1"] and r["stop"] > r["entry"] else 0
        r2 = (r["entry"]-r["tp2"])/(r["stop"]-r["entry"]) if r["tp2"] and r["stop"] > r["entry"] else r1
        hit = None
        for _, row in bars.iterrows():
            h, l = float(row[col_h]), float(row[col_l])
            if h >= r["stop"]: hit = "stop"; break
            if r["tp2"] and l <= r["tp2"]: hit = "tp2"; break
            if l <= r["tp1"]: hit = "tp1"; break
    if hit is None:
        results.append([r, "40天未触"]); continue
    R = {"stop": -1.0, "tp1": r1, "tp2": r2}[hit]
    results.append([r, f"{hit} R={R:+.2f}"])

for r, s in sorted(results, key=lambda x: x[0]["ts"]):
    print(f"  {r['sym']:8s} {r['tf']:4s} {r['dir']:7s} {str(r['od']):4s} -> {s}")
if results:
    ok = len(results)
    w1 = sum(1 for _, s in results if "tp1" in s and "R=+" in s)
    w2 = sum(1 for _, s in results if "tp2" in s and "R=+" in s)
    print(f"\ntp1判正确率: {100.0*w1/ok:.0f}% ({w1}/{ok})  tp2判正确率: {100.0*w2/ok:.0f}% ({w2}/{ok})")
    for nm, key in (("多头", "bullish"), ("空头", "bearish")):
        rs = [s for r, s in results if r["dir"] == key]
        if rs:
            w = sum(1 for s in rs if "tp1" in s and "R=+" in s)
            print(f"  {nm}(n={len(rs)}): tp1判胜 {w}  |> {[s.split(' ')[0] for s in rs]}")
