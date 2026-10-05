# 答辩 FAQ · 赛博评审厅

> 来源：SOP v3 §6 答辩 FAQ（含修正）｜适用：初赛线上评审 + 决赛线下答辩
> 口径铁律：51 位虚拟评委 / 8 大流派 / 评分公式 overall=fund×0.6+consensus×0.4 / verdict 阈值 80/65/50 / 分歧 |agent-rule|>30
> 当前演示数据：20 只 A 股覆盖 10 大板块（茅台 600519=70.98 hold_like 领跑 / 万科 000002=40.24 avoid 垫底）

---

## Q1 创新点是什么？

**A**：把机构级 AI 投资评审流程降维给普通投资者——51 位虚拟投资评委按 8 大流派（经典价值/成长/宏观对冲/技术趋势/中国价投/游资/量化/Serenity 卡位）逐一点亮，分歧自动检测并触发 3 轮辩论。竞品（TradingAgents-astock 等开源方案）仅 7 分析师辩论 + 单一路径，无显式分歧可视化。

## Q2 为什么是 51 位不是 66 位？

**A**：UZI 官方虚拟评委名单（A-I 九类投资风格）合计 51 位：经典价值 6 + 成长 4 + 宏观对冲 5 + 技术趋势 4 + 中国价投 6 + 游资 22 + 量化 3 + Serenity 卡位 1 = 51。66 位是早期草稿未对齐官方口径，已修正。

## Q3 评分公式为什么是 0.6/0.4？

**A**：overall = fund_score×0.6 + consensus_score×0.4。基本盘（财务/估值/盈利）权重 60%，市场盘（51 位评委共识）权重 40%——基本面派重事实、共识派重博弈，两者平衡体现『既要行业逻辑，也要资金共识』。所有数字与 UZI v2.11 一致，后端 `engine/rule_engine.py` 自动化测试 14 项断言 OK。

## Q4 快速档与深度回放的区别？

**A**：快速档走规则引擎 API，秒级出结果（演示用 `python -m uvicorn main:app` 启动）；深度回放加载预生成 demo_deep.json 模拟深度分析全过程（含辩论打字机动画）。前者零 LLM 延迟适合现场答辩不翻车，后者展示完整分析叙事。

## Q5 演示数据是怎么生成的？

**A**：基于 UZI 官方 51 位虚拟评委（A-I 九类）+ 20 只 A 股（覆盖 10 大板块）预设。每位评委按个人风格偏移（稳健 ±2 / 激进 ±7-9）跨股票保持一贯风格；每流派对每股票有自己的基准（茅台经典价值高、宁德成长高、平安中庸）。固定种子（20261003）确定性，演示回放不漂移。

## Q6 前端为什么零依赖能跑？

**A**：HTML + JS + SVG 自绘（弃 ECharts CDN 防断网），数据用 `window.DEMO_DATA` 全局脚本加载（避 file:// CORS），双击 index.html 即开。FastAPI 后端是可选增强——`pip install fastapi uvicorn` 后 `python -m uvicorn main:app` 一行起，自动静态托管前端。

## Q7 你用了码道什么能力？

**A**：(1) Spec-Driven 三件套（spec.md → design.md → tasks.md）打地基；(2) Agent Team 并行开发前端 + 后端；(3) 5 组精修 Prompt（Prompt A-E 见 `码道Prompt包.md`）覆盖需求/引擎/前端/辩论/双模式；(4) 码道 IDE 截图 + GitCode commit 记录（提交时随附 8 项证据清单）。

## Q8 评委按规则重算 consensus 和你前端展示的不一致怎么办？

**A**：完全一致。前端 demo-data.js 的 consensus_score / overall_score / verdict 三个字段已经按后端 `consensus_of(judges)` 公式同步重算（茅台 60.44/70.98 hold_like、平安 56.29/57.32 watch、宁德 64.85/65.54 hold_like）。后端单测 `python -m unittest test_rule_engine` 14 项断言全过。

## Q9 接入真实行情数据怎么改？

**A**：`backend/engine/data_provider.py` 是数据层接口，`load(code) -> stock dict`，接口已与真实源一致。替换为 akshare/xueqiu API 拉取行情 → 规则引擎动态评分即可，前端无需改。详见 SOP v3 §4 demo_deep.json schema。

## Q10 与华为云服务怎么结合？

**A**：(1) **OBS 静态网站托管** —— 前端是纯静态页（index.html + css/ + js/ + data/），直接发布 OBS 桶获公网地址；(2) **华为云开发者作品展览馆** —— 按赛规 §4 步骤四发布至「珠海科技学院校赛」专区；(3) **可选 ModelArts** —— 规则引擎评分可迁移至 ModelArts 推理服务展示 AI 工程化能力。

---

## 答辩兜底

- 现场不翻车：纯前端双击即开（断网也能演示）
- 数字一致性：前端展示数字 = 后端公式重算数字（单测 14 项 OK）
- 51 评委口径：README/自查表/Prompt 包/SOP 全文档统一
- 截图证据：8 项截图留证清单见 `码道Prompt包.md` 末尾
- 创新对比：与 TradingAgents-astock 等开源方案有明确差异（51 vs 7、双档、争议机制）