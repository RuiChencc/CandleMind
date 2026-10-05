# -*- coding: utf-8 -*-
"""budget.py — dialog 兜底日调用次数护栏（持久化 + 原子预扣）。

计费事实（用户确认）：dhap 包月 ¥50/12000 次 ≈ ¥0.00417/次，平台日硬顶 1000 次。
→ 护栏语义 =「次数」而非「金额」：防反复触发 dialog 刷爆月包 / 触达日顶，非防烧钱。
P0-A：计数落 records/execution_log/feishu_budget_YYYY-MM-DD.json（按日期 key），
      进程重启后读回 —— 次数语义是"每天最多 N 次"而非"每次运行最多 N 次"。
P0-B：每 chat_id 独立上限（防单人刷，默认 20 次/日）+ 全局上限（默认 300 次/日，
      300×30=9000 < 12000 月包留 25% 余量，且远低于平台日顶 1000）双判定；
      per-chat 判定在前（防单人刷优先）。
P0-新-1：budget_reserve 原子预扣（锁内 read-check-write；LLM 失败 budget_release 回滚）
      —— 消除 allow/charge 两段式中间隔 20-40s LLM 调用导致的并发双花。
P0-新-2：date 每次调用动态取（_today()），跨天自动切新文件；注入点支持真跨天模拟测试。
0 = 关闭护栏；负数 = 不限（不记账）。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date
from pathlib import Path

#: 单次 dialog = 1 次调用（包月按次计费，非按 token）
DIALOG_COST_UNITS = 1

_DEFAULT_GLOBAL = 300    # 次/日（全局）
_DEFAULT_PER_CHAT = 20   # 次/日（每 chat 防刷）

_lock = threading.Lock()
_log_dir_override: Path | None = None  # 测试注入


def _today() -> str:
    """当日日期串；独立函数便于测试注入跨天（运行时始终真实日期）。"""
    return date.today().isoformat()


def _budget_dir() -> Path:
    if _log_dir_override is not None:
        return _log_dir_override
    return Path(__file__).resolve().parent.parent.parent / "records" / "execution_log"


def _budget_file(today: str | None = None) -> Path:
    d = today or _today()
    return _budget_dir() / f"feishu_budget_{d}.json"


def _limits() -> tuple[float, float]:
    """(global_cnt, per_chat_cnt)。0=关闭护栏；负数=不限。"""
    try:
        from pa_agent.config.paths import SETTINGS_JSON_PATH
        from pa_agent.config.settings import load_settings
        feishu = getattr(load_settings(SETTINGS_JSON_PATH), "feishu", None)
        g = float(getattr(feishu, "llm_daily_calls", _DEFAULT_GLOBAL))
        p = float(getattr(feishu, "llm_per_chat_calls", _DEFAULT_PER_CHAT))
        return g, p
    except Exception:  # noqa: BLE001
        return _DEFAULT_GLOBAL, _DEFAULT_PER_CHAT  # 配置异常按保守默认


def _read(today: str) -> dict:
    """当日计数；文件不存在/损坏 → 从零开始。"""
    f = _budget_file(today)
    try:
        with open(f, encoding="utf-8") as fh:
            data = json.loads(fh.read())
        if isinstance(data, dict) and data.get("date") == today:
            return {
                "date": today,
                "total": float(data.get("total", 0.0)),
                "by_chat": dict(data.get("by_chat") or {}),
            }
    except (OSError, ValueError, TypeError):
        pass
    return {"date": today, "total": 0.0, "by_chat": {}}


def _write(data: dict) -> None:
    d = _budget_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        f = _budget_file(data["date"])
        tmp = f.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, indent=2))
        os.replace(tmp, f)  # 原子替换，防半写
    except OSError:
        pass  # 写失败只影响本日计数，不阻塞对话（护栏尽力而为）


def budget_reserve(chat_id: str | None) -> bool:
    """原子预扣：锁内 read-check-write。

    成功 = 已占 1 次调用额度（per-chat + 全局双判定，per-chat 在前）；
    LLM 调用失败后须调用 budget_release 回滚。
    """
    today = _today()
    global_cnt, per_chat_cnt = _limits()
    if global_cnt == 0:
        return False  # 0 = 关闭护栏
    if global_cnt < 0:
        return True   # 负数 = 不限（不记账）
    with _lock:
        data = _read(today)
        # per-chat 优先：单人刷先被拦（防挤占群聊）
        if per_chat_cnt > 0 and chat_id:
            spent = float(data["by_chat"].get(str(chat_id), 0.0))
            if spent + DIALOG_COST_UNITS - per_chat_cnt > 1e-9:
                return False
        # 全局上限（留整数容差，整数次数用 1e-9 同样安全）
        if data["total"] + DIALOG_COST_UNITS - global_cnt > 1e-9:
            return False
        data["total"] = round(data["total"] + DIALOG_COST_UNITS, 4)
        if chat_id:
            cid = str(chat_id)
            data["by_chat"][cid] = round(float(data["by_chat"].get(cid, 0.0)) + DIALOG_COST_UNITS, 4)
        _write(data)
        return True


def budget_release(chat_id: str | None) -> None:
    """回滚一次预扣（LLM 调用失败时；进程崩溃则保守多记，fail-closed 方向）。"""
    today = _today()
    with _lock:
        data = _read(today)
        data["total"] = max(0.0, round(data["total"] - DIALOG_COST_UNITS, 4))
        if chat_id:
            cid = str(chat_id)
            prev = float(data["by_chat"].get(cid, 0.0))
            data["by_chat"][cid] = max(0.0, round(prev - DIALOG_COST_UNITS, 4))
        _write(data)
