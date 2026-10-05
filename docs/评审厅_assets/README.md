# 赛博评审厅 · Multi-Expert AI Review Hall

> 华为云码道 Agent 创新赛 · 珠海科技学院站参赛作品
> 本仓库代码核心由华为云码道（CodeArts）编程智能体生成（Spec-Driven + Agent Team 工作流）

## 一句话

51 位虚拟投资评委 + 多智能体辩论评估 —— 让普通投资者拥有交易公司级别的 AI 评审流程。

## 快速启动

### 方式一：纯前端演示（零依赖，推荐现场演示）

直接双击打开 `frontend/index.html` 即可 —— 数据内置于 `frontend/data/demo-data.js`（`window.DEMO_DATA`），SVG 雷达自绘，无任何外部请求 / CDN / 服务器。

### 方式二：完整项目（后端 + 前端）

```bash
pip install fastapi uvicorn
cd backend
python -m uvicorn main:app --reload --port 8000
# 浏览器打开 http://localhost:8000
```

## 架构

```
前端（评审厅 Dashboard）· 零依赖双击即开          后端（FastAPI 可选）
├─ 顶部栏：搜索 + 快速档/深度回放双模式             ├─ 规则引擎（秒级，零LLM）
├─ 个股切换带：20 只标的横向滚动一键换股（覆盖 10 大板块）├─ 汇总 overall=fund×0.6+consensus×0.4
├─ 评审流水线：5 工序动画（采集→规则→打分→辩论→判定）├─ 分歧标记 |rule-agent|>30 / verdict 映射
├─ 51评委投票墙（逐人点亮，真实分布：流派内梯度+个体离群）└─ 数据层（demo_deep.json 预设兜底）
├─ 流派分歧雷达（SVG 自绘，8 轴）
├─ 汇总判定：基本面/共识/综合分 + verdict 徽章
├─ 分歧检测列表（>30 高亮）
├─ 八大流派势力（聚合均分 + 偏多/偏空/中性徽章）
├─ 多空 3 轮辩论（预设模板 + 打字机）
├─ 评审报告（摘要/支持/风险/入场区间 + 一键导出 .md）
├─ 20 只对比矩阵（综合分 + 流派分布）
└─ 评审历史（自动留痕，点击回看）
```
## 目录

| 路径 | 说明 |
|---|---|
| `backend/engine/rule_engine.py` | 规则引擎参考实现（评分公式/分歧检测/verdict） |
| `backend/engine/data_provider.py` | 预设数据加载器（零外部依赖） |
| `frontend/data/demo_deep.json` | 51 评委 × 20 只股票预设演示数据（覆盖 10 大板块） |
| `frontend/` | 评审厅页面（HTML/JS/SVG 自绘，赛博朋克主题，零依赖） |
| `frontend/data/demo-data.js` | 演示数据全局脚本（`window.DEMO_DATA`，双击即开） |

## 开发工具链

- **华为云码道 CodeArts**：Spec-Driven 三阶段（spec.md → design.md → tasks.md）+ Agent Team 并行开发
- **GitCode**：公开仓库，全程提交记录
- **预设数据**：基于 UZI 官方 51 位虚拟评委（A-I 九类投资风格，演示用，非实时行情）

## 评分对齐摘要（初赛 100 分）

| 维度 | 分值 | 自评 | 一句话证据 |
|---|---|---|---|
| 功能完备度 | 30 | 28 | 51 评委投票墙/雷达/判定/分歧/辩论/报告/对比/历史全验证通过 |
| 码道深度使用 | 25 | 20 | Spec-Driven 三件套 + Agent Team 并行，截图待补（SOP §4） |
| 专业贴合与创新 | 25 | 22 | 机构级 AI 评审流程降维给普通投资者，8 大流派争议评审机制 |
| 技术架构与工程质量 | 15 | 14 | 纯前端零依赖 + 可选 FastAPI，SVG 自绘零 CDN |
| 交付规范性 | 5 | 4 | README 可复现 + 提交包结构完整 |

详细逐项证据见《评分标准对齐自查表.md》。

## 从零复现三步

1. **码道生成**：将 SOP v3 §2 的 Prompt A（Spec-Driven 初始需求）粘贴给码道，产出 spec.md → design.md → tasks.md 三件套
2. **后端**：Prompt B 生成 `backend/engine/rule_engine.py` + `data_provider.py` + `backend/main.py`（FastAPI 入口，对齐 README 方式二）；`pip install fastapi uvicorn` → `cd backend && python -m uvicorn main:app --reload --port 8000` → 浏览器开 http://localhost:8000 即可访问完整评审厅（前端口静态托管 + API 自动接线）
3. **前端**：Prompt C-E 生成评审厅（投票墙/雷达/辩论/双模式），数据来自 demo-data.js，**零依赖**双击 `frontend/index.html` 即开；或走方式二通过 FastAPI 托管访问

## 创新点 vs 开源标杆

| 维度 | 本项目 | TradingAgents-astock 等开源方案 |
|---|---|---|
| 评委规模 | 51 位（8 大流派，含游资/量化/宏观对冲） | 7 分析师辩论 |
| 评审深度 | 快速档（纯规则 30 秒级）+ 深度回放（3 轮辩论）双档 | 单一路径 |
| 争议机制 | 分歧检测（|规则−AI|>30 自动标记）+ 流派势力聚合 | 无显式分歧可视化 |
| 交付形态 | 纯前端双击即开（零部署门槛，适合现场答辩） | 依赖 LLM API + 部署 |

## 结合华为云服务

- **OBS 静态网站托管**：前端为纯静态页面，可直接发布 OBS 桶（index.html + css/ + js/ + data/），获得公网访问地址
- **华为云开发者作品展览馆**：按赛规 §4 步骤四发布至「珠海科技学院校赛」专区
- **可选 ModelArts**：规则引擎评分可迁移至 ModelArts 推理服务，展示 AI 工程化能力

## 免责声明

本项目为教学演示用途，不构成任何投资建议。