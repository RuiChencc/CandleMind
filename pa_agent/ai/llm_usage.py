# -*- coding: utf-8 -*-
"""llm_usage.py — 模块级 LLM 调用计数器 + provider 切换调度。

v3 终态方案（2026-09-30 三轮审查定稿）：
- 计数出口与 deepseek_client.chat()/stream_chat() 内部埋点绑定
- 配额预切：日均节奏感知（elapsed_days/30 × cut_ratio）
- 失败熔断：allowed_fails 连续失败 → cooldown_seconds 冷却
- 滑动窗口：商汤 5h 1500 次基于时间戳列表（弹旧条目）
- 持久化：records/execution_log/llm_usage_<provider>_<bucket>.json
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()
_log_dir_override: Path | None = None


def _log_dir() -> Path:
    if _log_dir_override is not None:
        return _log_dir_override
    return Path(__file__).resolve().parent.parent.parent / "records" / "execution_log"


def _now_ts() -> float:
    return time.time()


def _ym() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _dhap_file() -> Path:
    return _log_dir() / f"llm_usage_dhap_{_ym()}.json"


def _read_dhap() -> dict:
    f = _dhap_file()
    try:
        with open(f, encoding="utf-8") as fh:
            data = json.loads(fh.read())
        if isinstance(data, dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"month": _ym(), "count": 0, "fail_streak": 0, "last_failure_ts": 0.0,
            "cooldown_until": 0.0, "cooldown_count": 0}


def _write_dhap(data: dict) -> None:
    d = _log_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        f = _dhap_file()
        tmp = f.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, indent=2))
        os.replace(tmp, f)
    except OSError:
        pass


def _sn_file() -> Path:
    return _log_dir() / f"llm_usage_sensenova_{_today()}.json"


def _read_sn_timestamps() -> list[float]:
    f = _sn_file()
    try:
        with open(f, encoding="utf-8") as fh:
            data = json.loads(fh.read())
        if isinstance(data, dict) and isinstance(data.get("timestamps"), list):
            return [float(t) for t in data["timestamps"]]
    except (OSError, ValueError, TypeError):
        pass
    return []


def _write_sn_timestamps(ts_list: list[float]) -> None:
    d = _log_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        f = _sn_file()
        tmp = f.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"date": _today(), "timestamps": ts_list},
                                ensure_ascii=False, indent=2))
        os.replace(tmp, f)
    except OSError:
        pass


def monthly_total(provider: str = "dhap") -> int:
    if provider == "dhap":
        with _lock:
            return int(_read_dhap().get("count", 0))
    if provider == "sensenova":
        with _lock:
            return len(_read_sn_timestamps())
    return 0


def window_count(provider: str, window_seconds: int) -> int:
    if provider != "sensenova":
        return 0
    cutoff = _now_ts() - window_seconds
    with _lock:
        ts = _read_sn_timestamps()
        return sum(1 for t in ts if t > cutoff)


def record_call(provider: str) -> None:
    if provider == "dhap":
        with _lock:
            data = _read_dhap()
            data["count"] = int(data.get("count", 0)) + 1
            data["fail_streak"] = 0
            _write_dhap(data)
    elif provider == "sensenova":
        with _lock:
            ts = _read_sn_timestamps()
            # 弹 5h 前旧条目（保持时间戳列表 ≈ 当前滑窗有效集）
            cutoff = _now_ts() - 5 * 3600
            ts = [t for t in ts if t > cutoff]
            ts.append(_now_ts())
            _write_sn_timestamps(ts)


def record_failure(provider: str) -> int:
    if provider != "dhap":
        return 0
    with _lock:
        data = _read_dhap()
        data["fail_streak"] = int(data.get("fail_streak", 0)) + 1
        data["last_failure_ts"] = _now_ts()
        _write_dhap(data)
        return data["fail_streak"]


def should_cut_quota(dhap_monthly_limit: int, cut_ratio: float = 1.1) -> bool:
    if dhap_monthly_limit <= 0:
        return False
    with _lock:
        data = _read_dhap()
    used = int(data.get("count", 0))
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elapsed_days = max(1, (now - month_start).days + (now.hour / 24.0))
    month_ratio = min(1.0, elapsed_days / 30.0)
    return used >= dhap_monthly_limit * month_ratio * cut_ratio


def is_cooled_down(provider: str, allowed_fails: int, cooldown_seconds: int) -> bool:
    if provider != "dhap":
        return False
    with _lock:
        data = _read_dhap()
    fail_streak = int(data.get("fail_streak", 0))
    cooldown_until = float(data.get("cooldown_until", 0.0))
    return fail_streak >= allowed_fails and _now_ts() < cooldown_until


def enter_cooldown(provider: str, cooldown_seconds: int) -> None:
    if provider != "dhap":
        return
    with _lock:
        data = _read_dhap()
        data["cooldown_until"] = _now_ts() + cooldown_seconds
        data["cooldown_count"] = int(data.get("cooldown_count", 0)) + 1
        _write_dhap(data)


def clear_cooldown(provider: str) -> None:
    if provider != "dhap":
        return
    with _lock:
        data = _read_dhap()
        data["cooldown_until"] = 0.0
        _write_dhap(data)


_fallback_flag: dict[str, str | float] = {}
_audit_log: list[dict] = []


def mark_fallback(from_provider: str, to_provider: str, trigger: str) -> None:
    with _lock:
        _fallback_flag["from"] = from_provider
        _fallback_flag["to"] = to_provider
        _fallback_flag["trigger"] = trigger
        _fallback_flag["ts"] = _now_ts()
        _audit_log.append({
            "ts": _now_ts(),
            "provider": to_provider,
            "from_provider": from_provider,
            "trigger": trigger,
        })
        if len(_audit_log) > 1000:
            _audit_log.pop(0)


def pop_fallback_flag() -> dict | None:
    with _lock:
        if not _fallback_flag:
            return None
        flag = dict(_fallback_flag)
        _fallback_flag.clear()
        return flag


def recent_audit(limit: int = 50) -> list[dict]:
    with _lock:
        return list(_audit_log[-limit:])
