# -*- coding: utf-8 -*-
"""run_cycle.py — PA_Agent 自动交易闭环（schtasks 1h K 线驱动拉起）。

频率设计（2026-09-30 审查后由 5min 改为 1h）：scheduler 是 1h 分析，
K 线 1h 才收盘——5min 轮询 = 同一根 K 线跑 12 次，LLM 成本白烧
（¥1200/月 → ¥100/月）。每次触发恰好在一根 1h K 线收盘后的稳定窗口。

非守护进程：由 OS 定时器（schtasks）每次拉起新进程，跑完即退
（无 while 循环、无孤儿进程，符合「不启守护」铁律）。

闭环：scheduler 分析白名单符号 → 落 records/pending →
      executor --live 消费（record_id 幂等 + 叠仓护栏已内置）→ audit。

日志落 temp/cycle.log（追加）。

观察通道（2026-09-30 审查定稿）：仅验证接线链路（下单→SL→成交→平仓），
不验证策略盈利——弱信号成交 ≠ 策略有效证据。观察期至 10-07 自动恢复 SSOT
MIN_NET_RR=1.5（到期日志见 executor 模式行）。详见 :30-34 常量注释。
"""
import json
import re
import subprocess
import sys
import time
from datetime import date

# 观察通道（2026-09-30 二轮审定）：观察期不放宽——1.5 恒守看真实信号密度（RR<1.5
# 成交 = 接线试验单，不作策略证据，signal_summary 标注）。默认 None = SSOT MIN_NET_RR=1.5；
# 仅当未来某轮真做"接线试验"时临时改 1.0，到期日（OBS_EXPIRE）后自动恢复 None
# （铁律：无恢复计划的放宽 = 永久改生产路径；此机制为防御护栏，当前不激活）。
OBS_MIN_NET_RR: float | None = None
OBS_EXPIRE = date(2026, 10, 7)
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "temp" / "cycle.log"
SYMBOLS = ("XRPUSDT", "ADAUSDT")  # 与 executor WATCHLIST_DEFAULT 对齐


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=str(ROOT), capture_output=True, text=True,
        timeout=timeout, errors="replace",
    )


def _tf_window_minutes(timeframe: str) -> float | None:
    """K 线周期 → 去重窗口分钟（0.92×周期：1h→55min / 4h→221min；与周期解耦，
    改 cycle 周期不需要改此函数）。不识别 → None = 守卫放行。"""
    m = re.fullmatch(r"(\d+)([mhdw])", (timeframe or "").strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    mins = {"m": 1, "h": 60, "d": 1440, "w": 10080}[unit] * n
    return round(mins * 0.92)


def _recent_pending(symbol: str, timeframe: str = "1h") -> bool:
    """K 线去重守卫：最新 pending 的分析时间距今 < 周期×0.92
    → 该 K 线已分析过，跳过 LLM 重分析（防手动重跑/异常触发重复烧钱）。
    窗口由 meta.timeframe 推导（与周期解耦）；无法推导/异常 → 放行（省分析不省安全）。"""
    try:
        cands = sorted(
            (ROOT / "records" / "pending").glob(f"*_{symbol}_*.json"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not cands:
            return False
        rec = json.load(open(cands[0], encoding="utf-8"))
        # 窗口以"最新 pending 自己的周期"为准（落后于当前周期配置时按旧周期判）
        w = _tf_window_minutes((rec.get("meta") or {}).get("timeframe") or timeframe)
        if w is None:
            return False
        ts = (rec.get("meta") or {}).get("timestamp_local_ms")
        if not ts:
            return False
        return (time.time() * 1000 - float(ts)) < w * 60_000
    except Exception:  # noqa: BLE001 守卫失效则放行分析（保守省分析不省安全）
        return False


def main() -> int:
    rc_final = 0
    # 1) 分析白名单符号（每符号 ~40s；单个失败不阻断后续/执行）
    for sym in SYMBOLS:
        if _recent_pending(sym, "1h"):
            log(f"scheduler {sym}: SKIP（同 K 线已分析过，省 LLM 成本）")
            continue
        try:
            r = _run([sys.executable, "-m", "pa_agent.scheduler",
                      "--symbol", sym, "--timeframe", "1h", "--bars", "200"], 240)
        except subprocess.TimeoutExpired:
            log(f"scheduler {sym}: TIMEOUT")
            continue
        log(f"scheduler {sym}: rc={r.returncode}")
        if r.returncode != 0:
            log("  stderr: " + (r.stderr or "")[-300:].strip())
    # 2) 执行消费（幂等 + 叠仓护栏；当前信号池全额拦截属正常）
    rr = OBS_MIN_NET_RR
    if rr is not None and date.today() >= OBS_EXPIRE:
        log("[观察通道] 已到期，自动恢复 SSOT MIN_NET_RR=1.5（后续信号按 1.5 门槛评估）")
        rr = None
    try:
        cmd = [sys.executable, "-m", "pa_agent.execution.executor", "--live",
               "--pending", str(ROOT / "records" / "pending")]
        if rr is not None:
            cmd += ["--min-net-rr", str(rr)]
            # 观察通道状态由 executor 模式行标注（LIVE（观察通道…）），此处不逐轮刷屏
        r2 = _run(cmd, 300)
    except subprocess.TimeoutExpired:
        log("executor: TIMEOUT")
        return 2
    log(f"executor: rc={r2.returncode}")
    for line in (r2.stdout or "").strip().splitlines()[-6:]:
        log("  " + line.strip())
    if r2.returncode != 0:
        rc_final = r2.returncode
    return rc_final


if __name__ == "__main__":
    sys.exit(main())
