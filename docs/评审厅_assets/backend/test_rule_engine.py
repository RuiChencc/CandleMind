# -*- coding: utf-8 -*-
"""test_rule_engine.py · 评分公式/分歧/verdict 自动校验

答辩口径铁律（与 SOP v3 §1、UZI v2.11 一致）：
  overall = fund_score * 0.6 + consensus_score * 0.4
  verdict: >=80 strong_buy / >=65 hold_like / >=50 watch / else avoid
  分歧: |agent_score - rule_score| > 30 -> flagged=True
  评委数: 51 位（8 大流派）

运行: python -m unittest test_rule_engine -v"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine.rule_engine import (
    calc_overall, verdict_of, mark_disputes, consensus_of, analyze, VERDICT_THRESHOLD
)
from engine.data_provider import DataProvider


class TestFormula(unittest.TestCase):
    """评分公式校验"""

    def test_overall_known(self):
        # 三只演示股新口径（demo-data.js 与后端公式一致）
        self.assertEqual(calc_overall(78, 60.44), 70.98)   # 茅台 600519
        self.assertEqual(calc_overall(58, 56.29), 57.32)   # 平安 000001
        self.assertEqual(calc_overall(66, 64.85), 65.54)   # 宁德 300750

    def test_overall_weights_sum_to_one(self):
        """基本面 60% + 共识 40% = 100%"""
        # 同一份评委，fund=consensus=70 => overall=70
        self.assertEqual(calc_overall(70, 70), 70.0)


class TestVerdict(unittest.TestCase):
    """verdict 阈值映射校验（80/65/50）"""

    def test_thresholds(self):
        self.assertEqual(verdict_of(80), "strong_buy")
        self.assertEqual(verdict_of(79.9), "hold_like")
        self.assertEqual(verdict_of(65), "hold_like")
        self.assertEqual(verdict_of(64.9), "watch")
        self.assertEqual(verdict_of(50), "watch")
        self.assertEqual(verdict_of(49.9), "avoid")
        self.assertEqual(verdict_of(0), "avoid")

    def test_threshold_order(self):
        """阈值按降序排列，避免低级阈值覆盖"""
        thresholds = [t for t, _ in VERDICT_THRESHOLD]
        self.assertEqual(thresholds, sorted(thresholds, reverse=True))


class TestDispute(unittest.TestCase):
    """分歧标记 |agent-rule|>30"""

    def test_flagged_above_30(self):
        judges = [{"rule_score": 60, "agent_score": 91}]  # gap=31
        self.assertTrue(mark_disputes(judges)[0]["flagged"])

    def test_not_flagged_at_30(self):
        judges = [{"rule_score": 60, "agent_score": 90}]  # gap=30 不算
        self.assertFalse(mark_disputes(judges)[0]["flagged"])

    def test_consensus_weight(self):
        """游资组权重 0.5，其余 1.0"""
        judges = [
            {"school": "游资", "rule_score": 100, "agent_score": 100},
            {"school": "经典价值", "rule_score": 0, "agent_score": 0},
        ]
        # 加权均值 = (100*0.5 + 0*1) / (0.5+1) = 50/1.5 = 33.33
        self.assertAlmostEqual(consensus_of(judges), 33.33, places=1)


class TestDataProvider(unittest.TestCase):
    """数据层校验"""

    def setUp(self):
        self.dp = DataProvider()

    def test_supported_stocks(self):
        # 20 只 A 股覆盖 10 板块（与 demo_deep.json 一致）
        self.assertEqual(len(self.dp.supported), 20)
        for c in ["600519", "000858", "000001", "600036", "601398", "601628",
                  "000002", "600048", "300750", "002594", "688981", "002415",
                  "300059", "002475", "600276", "000538", "000333", "600887",
                  "600760", "600900"]:
            self.assertIn(c, self.dp.supported, f"{c} 应在 supported 列表")

    def test_invalid_code_raises(self):
        with self.assertRaises(KeyError):
            self.dp.load("999999")

    def test_judges_count_is_51(self):
        for code in self.dp.supported:
            self.assertEqual(len(self.dp.load(code)["judges"]), 51,
                             f"{code} 评委数应为 51")

    def test_judges_school_distribution(self):
        """8 大流派全覆盖"""
        for code in self.dp.supported:
            schools = {j["school"] for j in self.dp.load(code)["judges"]}
            self.assertGreaterEqual(len(schools), 8, f"{code} 应覆盖至少 8 大流派")


class TestEndToEnd(unittest.TestCase):
    """主入口 analyze(code, provider) 端到端"""

    EXPECTED_VERDICT = {
        # 20 只演示股（与 demo_deep.json 一致）
        "600519": "hold_like", "000858": "watch", "000001": "watch",
        "600036": "hold_like", "601398": "hold_like", "601628": "watch",
        "000002": "avoid", "600048": "avoid", "300750": "hold_like",
        "002594": "hold_like", "688981": "watch", "002415": "watch",
        "300059": "watch", "002475": "watch", "600276": "watch",
        "000538": "watch", "000333": "hold_like", "600887": "watch",
        "600760": "watch", "600900": "hold_like",
    }

    def setUp(self):
        self.dp = DataProvider()

    def test_analyze_overall_formula_consistent(self):
        """analyze 输出的 overall 必须满足 0.6*fund + 0.4*consensus"""
        for code in self.dp.supported:
            r = analyze(code, self.dp)
            expected = round(r["fund_score"] * 0.6 + r["consensus_score"] * 0.4, 2)
            self.assertEqual(r["overall_score"], expected,
                             f"{code} overall {r['overall_score']} != fund*0.6+consensus*0.4={expected}")

    def test_analyze_verdict_threshold(self):
        """verdict 必须按阈值 80/65/50 映射"""
        for code, expected_v in self.EXPECTED_VERDICT.items():
            r = analyze(code, self.dp)
            self.assertEqual(r["verdict"], expected_v,
                             f"{code} overall={r['overall_score']} verdict 应为 {expected_v}")

    def test_analyze_has_at_least_2_disputes(self):
        """每只股票至少 2 个分歧点（雷达图高亮需要）"""
        for code in self.dp.supported:
            r = analyze(code, self.dp)
            disputes = [j for j in r["judges"] if j["flagged"]]
            self.assertGreaterEqual(len(disputes), 2,
                                    f"{code} 应至少有 2 个分歧点，实际 {len(disputes)}")


if __name__ == "__main__":
    unittest.main()