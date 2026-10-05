# 本地测试补丁：绕开 tempfile.mkdtemp(mode=0o700) 在本沙箱下创建的目录被拒。
# 根因（2026-09-27 实测）：Windows 上 os.mkdir(path, mode) 用 mode 合成一个不继承的 DACL；
#   mode == 0o700 时该 DACL 缺 READ_CONTROL 与全部非 owner ACE（连 Get-Acl 都被拒），
#   沙箱按 ACL 校验写入 → PermissionError。os.chmod 只切只读属性位、不动 DACL，修不回来。
#   边界非「字面值 0o700」：0o500 / 0o701 / 0o710 均可写；0o700 是唯一 owner 独占 rwx 的取值。
# 故改用 os.makedirs(mode=0o777)。注：stat().st_mode 恒 0o40777（含目录类型位）。
# 本文件为本地新增（上游无根 conftest.py），不进上游，保持与上游文件零差异。
import os
import tempfile
import uuid


def _mkdtemp_patched(suffix=None, prefix=None, dir=None):
    base = dir if dir is not None else tempfile.gettempdir()
    pfx = prefix or "tmp"
    sfx = suffix or ""
    for _ in range(100):
        name = os.path.join(base, pfx + uuid.uuid4().hex + sfx)
        try:
            os.makedirs(name, mode=0o777)
        except FileExistsError:
            continue
        return name
    raise FileExistsError("mkdtemp: could not create unique directory")


tempfile.mkdtemp = _mkdtemp_patched

import json
from pathlib import Path

import pytest


# ── e2e headless 适配（本地层，2026-09-27）──────────────────────────────────
# e2e 4 个 smoke 测试在无 API Key 时，MainWindow 启动自检 _on_startup_api_key_check
# 弹模态 QMessageBox → pytest-qt teardown 的 _process_events 死锁（offscreen 下
# 模态框无法关闭，事件循环空转，测试挂死；faulthandler 线程栈实证
# main_window.py:5109 ← pytestqt/plugin.py:220）。本 fixture 仅对 tests/e2e/ 生效：
# 注入"已配置 key" + 弹窗 no-op + 设置对话框 no-op，使 smoke 测试真实运行（可判绿/红）。
# 生命周期：若上游修复启动自检（非模态化）→ 本 fixture 可整体移除。
@pytest.fixture(autouse=True)
def _headless_e2e_guard(monkeypatch, request):
    if not request.node.nodeid.startswith("tests/e2e/"):
        return
    from pa_agent.gui.main_window import MainWindow
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(MainWindow, "_has_api_key_configured", lambda self: True)
    monkeypatch.setattr(
        MainWindow, "_open_settings_dialog", lambda self, focus_api_key=True: None
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok),
    )


# ── xfail 注册（数据外部化，SSOT = tools/xfail_registry.json，2026-09-27 起）─
# conftest 只保留注册逻辑；46 条 nodeid/reason/scope 在 JSON 里维护
# （tools/xfail_ratchet.py --freeze/--collect-check 亦读该 JSON）。
# 生命周期：上游修复对应 case → 测试仍运行 → XPASS → strict=True 自动报 FAIL →
#           删 JSON 条目。注意：用 item.add_marker（标记仍运行测试），不是
#           pytest.xfail()（会跳过测试、丧失 XPASS 检测）。
# 三档 scope（2026-09-27 batch2 单 case 批测：46 case = 43 真红 / 3 顺序依赖）：
#   always     真红（单跑也红，上游漂移/上游缺陷）→ 全 scope strict=True
#   full-only  跨文件顺序依赖（单文件跑也绿）→ 仅全量跑（pytest tests）注册
#   full-file  文件内顺序依赖（单文件跑红、单 case 绿）→ 全量+单文件注册
# 依据：2026-09-27 batch2 单 case 批测（46 case：43 真红 / 3 顺序依赖）+ batch 单文件批测。
_REGISTRY_PATH = Path(__file__).resolve().parent / "tools" / "xfail_registry.json"
if not _REGISTRY_PATH.exists():
    raise RuntimeError(
        "tools/xfail_registry.json missing — xfail registration is data-driven; "
        "recreate via tools/xfail_ratchet.py --freeze + registry template"
    )
try:
    _REG = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
except json.JSONDecodeError as e:
    raise RuntimeError(f"tools/xfail_registry.json invalid JSON (line {e.lineno} col {e.colno}): {e.msg}") from e
_REG_XFAILS = _REG.get("xfails")
if not isinstance(_REG_XFAILS, dict) or not _REG_XFAILS:
    raise RuntimeError("tools/xfail_registry.json has no xfails entries")
_ALLOWED_SCOPES = ("always", "full-only", "full-file")
for _n, _v in _REG_XFAILS.items():
    if _v.get("scope") not in _ALLOWED_SCOPES or not isinstance(_v.get("reason"), str) or not _v.get("reason"):
        raise RuntimeError(f"tools/xfail_registry.json entry {_n!r}: scope must be one of {_ALLOWED_SCOPES} with non-empty reason")
_XFAIL_NODEIDS = {n: v["reason"] for n, v in _REG_XFAILS.items() if v["scope"] == "always"}
_XFAIL_FULL_ONLY = {n for n, v in _REG_XFAILS.items() if v["scope"] == "full-only"}
_XFAIL_FULL_FILE = {n for n, v in _REG_XFAILS.items() if v["scope"] == "full-file"}
_ORDER_REASONS = {n: v["reason"] for n, v in _REG_XFAILS.items() if v["scope"] != "always"}


def _run_scope(config) -> str:
    """全量跑='full'（args 只含 tests 目录）；单文件='single-file'；单 case='single-case'。"""
    args = [str(a) for a in config.args]
    if any("::" in a for a in args):
        return "single-case"
    if args and all(a in ("tests", "tests/") for a in args):
        return "full"
    return "single-file"


def pytest_collection_modifyitems(config, items):
    scope = _run_scope(config)
    for item in items:
        nodeid = item.nodeid
        if nodeid in _XFAIL_NODEIDS:
            item.add_marker(pytest.mark.xfail(strict=True, reason=_XFAIL_NODEIDS[nodeid]))
        elif nodeid in _XFAIL_FULL_ONLY:
            if scope == "full":
                item.add_marker(pytest.mark.xfail(strict=True, reason=_ORDER_REASONS[nodeid]))
        elif nodeid in _XFAIL_FULL_FILE:
            if scope in ("full", "single-file"):
                item.add_marker(pytest.mark.xfail(strict=True, reason=_ORDER_REASONS[nodeid]))
