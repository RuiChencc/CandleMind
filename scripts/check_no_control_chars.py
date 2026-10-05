# -*- coding: utf-8 -*-
"""check_no_control_chars.py — P1 根因固化（审查 E-2026-09-30 env 控制字符）。

扫 pa_agent/ 全部 .py，找 ord<32 且非 tab(9)/LF(10)/CR(13) 的控制字符。
原因：edit 工具/TS 字符串链路处理 raw string 的 \\t \\b 时写过真实控制字符
（实例：executor.py 默认 env 路径 D:OpenCode<TAB>emp<BACKSPACE>inance）。
exit 1 = 发现污染；0 = 干净。可在 pre-commit 或 CI 挂载。
"""
import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "pa_agent"
BAD_CHARS = {o for o in range(32)} - {9, 10, 13}


def main() -> int:
    bad = 0
    for f in sorted(glob.glob(str(ROOT / "**" / "*.py"), recursive=True)):
        try:
            data = Path(f).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            data = Path(f).read_text(encoding="utf-8", errors="surrogateescape")
        for ch in data:
            if ord(ch) in BAD_CHARS:
                ln = 1 + data.count("\n", 0, data.index(ch))
                print(f"CONTROL ord={ord(ch)}: {f}:{ln}")
                bad += 1
                break
    if bad:
        print(f"FAIL: {bad} file(s) contain control chars (tab/newline allowed only)")
        return 1
    print("ALL CLEAN: pa_agent/ has no control chars (allowed: tab/LF/CR)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
