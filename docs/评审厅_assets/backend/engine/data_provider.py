# -*- coding: utf-8 -*-
"""data_provider.py · 预设演示数据加载（快速档零外部依赖的基础）

演示数据源：demo_deep.json（51 位真实投资评委名单生成，20 只 A 股覆盖 10 板块）。
真实模式可扩展：akshare/xueqiu 拉取行情 → 规则引擎动态评分（渐进式披露三层加载）。
"""

import json
import os
from pathlib import Path

# engine/ -> backend/ -> assets/ -> frontend/data/demo_deep.json
_DEMO_PATH = Path(__file__).resolve().parent.parent.parent / "frontend" / "data" / "demo_deep.json"
# 码道生成的项目目录结构可能不同，支持环境变量覆盖
_DEMO_PATH = Path(os.environ.get("DEMO_JSON_PATH", str(_DEMO_PATH)))

_SUPPORTED = None  # 启动时从 demo_deep.json 动态加载


class DataProvider:
    """统一数据层：load(code) -> stock dict。预设兜底，接口与真实源一致。"""

    def __init__(self):
        self._cache: dict = {}
        self._load_demo()

    def _load_demo(self):
        if not _DEMO_PATH.exists():
            raise FileNotFoundError(f"预设数据缺失: {_DEMO_PATH}，请先放置 demo_deep.json")
        with open(_DEMO_PATH, encoding="utf-8") as f:
            self._demo = json.load(f)["stocks"]
        global _SUPPORTED
        _SUPPORTED = tuple(self._demo.keys())  # 20 只动态化

    def load(self, code: str) -> dict:
        code = str(code).split(".")[0] if "." in str(code) else str(code)
        s = self._demo.get(code)
        if s is None:
            raise KeyError(f"股票代码 {code} 不在预设演示数据中，支持: {_SUPPORTED}")
        import copy
        return copy.deepcopy(s)

    @property
    def supported(self) -> tuple:
        return tuple(self._demo.keys())  # 动态：20 只


if __name__ == "__main__":
    dp = DataProvider()
    for c in _SUPPORTED:
        s = dp.load(c)
        print(c, s["name"], "judges=", len(s["judges"]))
