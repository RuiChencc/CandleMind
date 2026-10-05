"""xfail_ratchet: 冻结 xfail 注册清单，只允许缩小不允许增长（本地层，2026-09-27）。

用法:
    python tools/xfail_ratchet.py            # 读 tools/xfail_registry.json 注册数，与冻结值比对
    python tools/xfail_ratchet.py --freeze   # 把当前注册数写进 xfail_ratchet.json
    python tools/xfail_ratchet.py --collect-check  # 跑 pytest --collect-only 比对注册
                                         # nodeid 是否全部仍被收集（防静默失配）

注册数据 SSOT = tools/xfail_registry.json（conftest 与 ratchet 同源读取，2026-09-27 外部化）。

机制（开源 skip/xfail ratchet 模式）:
    - xfailed 计数 > 冻结值 → FAIL（新引入了预期失败，需确认）
    - xfailed 计数 < 冻结值 且无 XPASS → WARN（某 case 变绿了但标记还在，需清理）
    - XPASS → strict=True 已自动报 FAIL（上游已修复，删标记）
    - --collect-check: 注册的 nodeid 若已不在 pytest 收集集（上游删测试/改名）
      → FAIL，防止「注册 46 条但实际只命中 44 条」的假 OK
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFTEST = ROOT / "conftest.py"
REGISTRY = ROOT / "tools" / "xfail_registry.json"
RATCHET_JSON = ROOT / "tools" / "xfail_ratchet.json"
PYTHON = r"C:/Users/Abily/AppData/Local/Programs/Python/Python314/python.exe"


def registered_nodeids() -> dict[str, str]:
    """SSOT = tools/xfail_registry.json (conftest + ratchet 同源, 2026-09-27 外部化).

    fail-closed: registry 缺失或空 -> 显式失败, 禁止 "0 条注册" 的假 OK.
    """
    if not REGISTRY.exists():
        print("FAIL: tools/xfail_registry.json missing (data-driven xfail SSOT)")
        sys.exit(2)
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    xfails = reg.get("xfails")
    if not isinstance(xfails, dict) or not xfails:
        print("FAIL: tools/xfail_registry.json has no xfails entries")
        sys.exit(2)
    return {n: v.get("reason", "") for n, v in xfails.items()}


def main() -> None:
    reg = registered_nodeids()
    n = len(reg)
    frozen = 0
    if RATCHET_JSON.exists():
        frozen = json.loads(RATCHET_JSON.read_text(encoding="utf-8")).get("xfail_count", 0)

    if "--collect-check" in sys.argv:
        import os
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        r = subprocess.run(
            [PYTHON, "-m", "pytest", "tests", "--collect-only", "-p", "no:cacheprovider"],
            cwd=ROOT, capture_output=True, text=True, timeout=300, env=env,
        )
        # 非 -q 的 --collect-only 输出逐 nodeid（路径格式，含 Windows 反斜杠或正斜杠）
        collected = set()
        for ln in r.stdout.splitlines():
            m = re.search(r"(tests[\\/][^:]+::[^\s]+)", ln)
            if m:
                collected.add(m.group(1))
        missing = [k for k in reg if k not in collected]
        if missing:
            print(f"FAIL: {len(missing)}/{n} registered nodeids NOT collected:")
            for k in missing:
                print("  ", k)
            sys.exit(1)
        print(f"OK: all {n} registered nodeids collected (total collected={len(collected)})")
        return

    if "--freeze" in sys.argv:
        RATCHET_JSON.write_text(
            json.dumps({"xfail_count": n, "frozen_at": "2026-09-27"}, indent=2),
            encoding="utf-8",
        )
        print(f"frozen xfail_count={n}")
        return

    print(f"registered={n} frozen={frozen}")
    if frozen and n > frozen:
        print("FAIL: xfail 计数增长（新引入预期失败），需确认")
        sys.exit(1)
    if frozen and n < frozen:
        print("WARN: xfail 计数缩小（部分 case 已变绿），需清理标记")
    else:
        print("OK: 与冻结值一致（或首次运行，先用 --freeze 冻结）")


if __name__ == "__main__":
    main()
