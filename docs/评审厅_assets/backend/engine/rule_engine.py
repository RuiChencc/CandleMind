# -*- coding: utf-8 -*-
"""rule_engine.py · 赛博评审厅规则引擎参考实现（喂给码道的规格参考）

评分公式（答辩口径，与 UZI v2.11 一致）：
    overall = fund_score x 0.6 + consensus_score x 0.4

规则引擎职责：
1. 按 A-I 九类投资风格 51 位虚拟评委（预设数据见 data_provider.py）输出骨架评分
2. 汇总共识分 consensus_score
3. 分歧标记：|agent_score - rule_score| > 30 时 flagged=True
4. verdict 映射（阈值 80/65/50/35）：
   >=80: strong_buy(值得重仓)  >=65: hold_like(可以蹲一蹲)
   >=50: watch(观望)           else: avoid(规避)
"""

SCHOOLS = {
    "classic_value": "经典价值",
    "growth": "成长",
    "macro": "宏观对冲",
    "technical": "技术趋势",
    "china_value": "中国价投",
    "youzi": "游资",
    "quant": "量化",
    "trend": "趋势",
    "reverse": "逆向",
    "serenity": "Serenity卡位",
}

VERDICT_THRESHOLD = [(80, "strong_buy"), (65, "hold_like"), (50, "watch")]


def verdict_of(overall: float) -> str:
    for th, v in VERDICT_THRESHOLD:
        if overall >= th:
            return v
    return "avoid"


def calc_overall(fund_score: float, consensus_score: float) -> float:
    """汇总公式：基本面体系分 60% + 评委共识分 40%。"""
    return round(fund_score * 0.6 + consensus_score * 0.4, 2)


def mark_disputes(judges: list[dict]) -> list[dict]:
    """遍历评委，|agent - rule| > 30 标记分歧点。"""
    for j in judges:
        j["flagged"] = abs(j.get("agent_score", j["rule_score"]) - j["rule_score"]) > 30
    return judges


def consensus_of(judges: list[dict]) -> float:
    """共识分 = 全部评委 agent_score 加权均值（游资组按权重 0.5，其余 1.0）。"""
    total_w = 0.0
    total_s = 0.0
    for j in judges:
        w = 0.5 if j.get("school") in ("游资",) else 1.0
        total_w += w
        total_s += j.get("agent_score", j["rule_score"]) * w
    return round(total_s / total_w, 2) if total_w else 0.0


def analyze(code: str, provider) -> dict:
    """主入口：输入股票代码，输出完整评审 JSON（快速档·秒级·零LLM）。"""
    stock = provider.load(code)
    judges = mark_disputes([dict(j) for j in stock["judges"]])
    consensus = consensus_of(judges)
    overall = calc_overall(stock["fund_score"], consensus)
    stock["consensus_score"] = consensus
    stock["overall_score"] = overall
    stock["verdict"] = verdict_of(overall)
    stock["radar"] = _radar(judges)
    return stock


def _radar(judges: list[dict]) -> dict:
    """按流派聚合 rule/agent 平均分，供 ECharts 雷达图。"""
    acc: dict[str, dict] = {}
    for j in judges:
        g = acc.setdefault(j["school"], {"rule": [], "agent": []})
        g["rule"].append(j["rule_score"])
        g["agent"].append(j.get("agent_score", j["rule_score"]))
    import statistics
    return {
        "schools": list(acc.keys()),
        "rule": [round(statistics.mean(v["rule"]), 1) for v in acc.values()],
        "agent": [round(statistics.mean(v["agent"]), 1) for v in acc.values()],
    }


if __name__ == "__main__":
    # 自测：python rule_engine.py
    from data_provider import DataProvider
    dp = DataProvider()
    for code in ("600519", "000001", "300750"):
        r = analyze(code, dp)
        print(code, r["name"], "overall=", r["overall_score"], "verdict=", r["verdict"],
              "disputes=", sum(1 for j in r["judges"] if j["flagged"]))