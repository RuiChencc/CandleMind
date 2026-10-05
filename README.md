# CandleMind

**CandleMind** — AI 辅助的 K 线价格行为分析工具（桌面端）。从 MT5 / TradingView / yfinance / AkShare 读取结构化 K 线数据，送入大模型做**两阶段分析**（市场诊断 → 交易决策）。不是截图识图，不连接券商、不执行下单。

**CandleMind** is an AI-powered **price-action (K-line) analysis assistant** for desktop traders. It ingests K-lines from **MT5 / TradingView / yfinance / AkShare** and runs a **two-stage LLM pipeline** (market diagnosis → trade decision) over structured data. No screenshot OCR, **no broker connection, no order placement**.

---

## 主要功能

- 📈 **多数据源**：MT5（Windows）、TradingView（全平台）、yfinance（期货/加密货币）、AkShare（A 股）
- 🧠 **两阶段 AI 分析**：市场诊断 → 策略路由 → 交易决策（限价/突破/市价或不下单）
- 🔄 **增量分析与持续跟踪**：新增 K 线时复用上次结论；开启 `keep_analysis` 后新 K 线收盘自动触发新一轮分析
- 🌳 **决策树可视化**：可交互决策树流程图，展示闸门与策略路径
- 🔮 **未来走势预期**：AI 预测下一根 K 线方向和下一个市场周期位置
- 💬 **分析后自由追问**：完整对话会话管理器，实时推理流 + Token 进度条，对话历史持久化
- 📚 **经验库**：按周期位置检索历史案例供分析参考
- 📝 **完整落盘**：Prompt、原始响应、诊断/决策 JSON、Token 用量、追问记录
- 🛡️ **可配置校验体系**：JSON 校验、一致性检查、语义校验、截断修复、失败自动重试
- 🔒 **API Key 本地加密存储**

---

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11（主支持）、macOS 12+（TradingView 数据源） |
| Python | 3.11+ |
| 数据源 | MT5 / TradingView / yfinance / AkShare **至少配置一种** |
| 网络 | 可访问所配置的 AI API（如 DeepSeek、PackyAPI 等） |

---

## 快速开始

```cmd
pip install -e .
python -m pa_agent.main
```

首次启动后在**设置**中填写 **Base URL**、**模型名** 与 **API Key**。

> 如需隔离环境也可创建虚拟环境：`python -m venv .venv` 后激活再 `pip install -e .`。

**安装内容**：PyQt6（GUI 框架）+ pyqtgraph（K 线图表）+ numpy/pandas（数据处理）+ openai（AI API 客户端）+ akshare/baostock（A 股数据源）+ json 校验、模型定义等全套依赖。

---

## 详细说明

完整操作界面说明见 [`CandleMind使用文档.md`](CandleMind使用文档.md)，配置字段说明见 [`config/README.md`](config/README.md)。

---

## 独立性声明

CandleMind 是**独立开发**的开源项目，作者基于自身需求与公开技术栈（PyQt6 / pyqtgraph / OpenAI API 客户端）从零构建，**不源自任何外部同类项目**。决策树可视化、两阶段 LLM pipeline、4 数据源集成、增量分析等模块均为本项目原创实现。

---

## 免责声明

本工具仅供学习与研究，不构成投资建议。交易有风险，决策后果自负。

## License

本项目采用 [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE) 发布。
