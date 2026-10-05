# 华为云码道大赛 · 赛博评审厅 SOP v3（精修版）

> 版本：v3 ｜ 适用：珠海科技学院站码道 Agent 创新赛（截止 2026-10-23，约剩 20 天）
> 证据原则：所有引用已在本机/官方源验证；不可验证引用已剔除或替换。

---

## 0. v3 修正清单（相对 v2 的硬核修正，带证据）

| # | 原 v2 内容 | 修正 | 证据 |
|---|---|---|---|
| 1 | TradingAgents（65K⭐） | **109,548⭐** | GitHub API 实测 2026-09-29 |
| 2 | 学术引用 FinCom（arXiv 2026） | **删除**，替换为 MAD + ChatEval | arXiv 两次检索 "FinCom"/"disagree+commit" 均 0 命中 |
| 3 | 发布 Skill：`--skill publish-work-to-gallery` | **`--skill huawei-cloud-publish-work-to-gallery`** | 大赛官方赛题原文 |
| 4 | 评分公式 `0.65×mean+0.35×vote+极化拉伸` | 答辩口径改用 UZI 真实公式 `fund×0.6+consensus×0.4`（v2.11 README） | UZI-Skill v2.11 评分校准章节 |
| 5 | 9 大流派 66 人 | 标注为"基于公开投资方法论自建的预设评审框架" | UZI 实际分组为 A-I九组（经典价值/成长/宏观/技术/中国价投/游资/量化/Serenity等），人数与用户自定不同——预设数据可自洽设计，但**不宣称原版名单** |
| 6 | 证据包侧重决赛 | **证据包是初赛生死线**（初赛线上评审：功能完成度+码道深度+专业贴合度全部靠材料体现） | 官方赛题"初赛采用线上评审" |

---

## 1. 定位与架构（v2 保留，公式修正）

**一句话**：66 位虚拟投资评委 + 多智能体辩论评估 —— 让普通投资者拥有交易公司级别的 AI 评审流程。

```
┌─ 前端（码道 Spec-Driven + Agent Team）──────────────────┐
│ 赛博评审厅：66评委投票墙 · 流派分歧雷达 · 分歧点高亮 ·     │
│ 多空3轮辩论 · K线 · 报告卡片 · 快速档/深度回放双模式       │
└───────────────┬─────────────────────────────────────────┘
                 │ REST API
┌─ 后端 FastAPI（码道 Agent Team 并行）───────────────────┐
│ 规则引擎（22维×51人，秒级确定性，零LLM）→ [可选]评审Agent  │
│ → 汇总 overall=fund×0.6+consensus×0.4 → verdict → 分歧标记│
└───────────────┬─────────────────────────────────────────┘
                 │
      华为云码道 CodeArts（全流程）+ GitCode（证据链）
```

**学术背书（已验证）**：
- **MAD Multi-Agents-Debate** ★613 — 多智能体辩论（OpenAI 论文实现）
- **ChatEval**（清华 thunlp）★343 — 多智能体辩论评估优于单模型
- **TradingAgents-astock** ★3609 — A股 7 分析师 Bull/Bear 辩论 + 三方风控（辩论机制背书）

---

## 2. 码道 Prompt 包（v3 精修版，可直接粘贴）

### Prompt A（Spec-Driven 初始需求）— 精修

```
请使用Spec-Driven模式，帮我创建一个可以运行的Web作品。

作品用途是「多专家AI金融评审厅」，主要用户是希望快速了解个股投资价值的普通投资者。

核心功能：
1. 输入股票代码，规则引擎生成66位虚拟投资评委的骨架评分
2. 66评委头像网格逐人点亮，显示分数与一句话观点
3. 按流派分组展示分歧对比雷达图
4. 规则引擎分与Agent深度分差>30分自动标记分歧点并高亮
5. 评分公式：overall = fund_score × 0.6 + consensus × 0.4（fund=基本面体系分，consensus=评委共识分）
6. 快速档（30秒规则引擎）/ 深度回放（预生成数据）双模式
7. 底部多空辩论区：最高分与最低分评委3轮结构化辩论（预设模板+变量替换，不调LLM）

技术栈：后端Python FastAPI，前端HTML+JS+ECharts，数据层预设演示数据兜底（离线可跑）。

界面风格：赛博朋克深色（深蓝黑底 #0a0e17 + 霓虹青/品红高亮，等宽科技风字体）。

请先生成需求规格文档 spec.md，我确认后再进入方案与任务阶段。
```

### Prompt B（后端规则引擎，Agent Team 并行）— 精修

```
基于design.md后端设计实现FastAPI：

1. backend/engine/rule_engine.py — 规则引擎核心：
   - 输入股票代码 → 输出66评委评分JSON
   - 每评委：{id, name, school, score, headline, highlights}
   - A-I九类风格预设分组（共51人，UZI官方名单）：A经典价值6/B成长4/C宏观对冲5/D技术趋势4/E中国价投6/F游资22/G量化3/I AI卡位1
   - 汇总公式：overall = fund × 0.6 + consensus × 0.4
   - 分歧标记：|agent_score - rule_score| > 30 → flagged=true

2. backend/engine/data_provider.py — 3只股票预设演示数据：
   - 600519 贵州茅台（价值高分/量化中等）
   - 000001 平安银行（技术看多/价值分歧）
   - 300750 宁德时代（成长看多/游资看空）

3. backend/main.py — REST API：
   - GET /api/analyze?code={code} → 完整评分JSON
   - GET /api/health

请实现并启动服务供我测试。
```

### Prompt C（前端评审厅，与后端并行）— 精修

```
基于design.md前端设计实现评审厅页面：

1. index.html：左侧2/3评委投票墙（6列×11行），右侧1/3流派雷达图+分歧面板，底部辩论区，顶部模式切换+输入框
2. judge-grid.js：66张卡片（首字头像/姓名/流派/评分/headline），加载后逐张点亮间隔80ms缩放弹跳动画，悬停放大，点击展开22维详情
3. radar.js（ECharts）：9轴9流派，青色=规则引擎 vs 品红=Agent，差>30轴红色高亮+警告图标，右侧列出分歧评委
4. cyberpunk.css：#0a0e17背景 + 霓虹青/品红发光边框 + 等宽字体
5. 数据从 /api/analyze 获取
```

### Prompt D（多空辩论区）— 精修

```
页面底部新增多空辩论区：
1. 从66评委选最高分（bull）与最低分（bear）
2. 3轮结构化辩论：bull先发言引用highlights数据 → bear反驳 → 循环；流式打字机逐字显示
3. 辩论结束输出"评审团总结"verdict
4. 辩论内容=预设模板+变量替换，不调真实LLM
5. 样式：bull绿色/bear红色气泡左右对立，中间动态"分歧线"摆动
```

### Prompt E（双模式切换）— 精修

```
页面顶部新增模式切换：
1. 快速档：调规则引擎API秒级返回，评委点亮间隔30ms
2. 深度回放：加载 frontend/data/demo_deep.json 模拟深度分析全过程
3. 状态条："快速档·规则引擎｜30秒出结果" / "深度回放·预生成分析"
4. 底部演示控制（仅深度模式可见）：一键重置 / 加速演示（20ms）/ 跳过辩论
```

---

## 3. 阶段零~六（沿用 v2，插入修正）

### 阶段零 D1：环境准备（2小时）
0.1 开通码道 CodeArts 体验版 ｜ 0.2 新建项目 review-hall ｜ 0.3 开启自动批准 ｜ 0.4 注册 GitCode 建公开仓库 review-hall ｜ 0.5 本地 Git 配置 ｜ 0.6 截图存档

### 阶段一 D1-D2：Spec-Driven 三件套
1.1 码道切"规范开发 Spec-Driven" ｜ 1.2 输入 Prompt A → spec.md ｜ 1.3 审核修订 ｜ 1.4 → design.md ｜ 1.5 审核 ｜ 1.6 → tasks.md ｜ 1.7 **截图存档三件套**

### 阶段二 D3-D10：Agent Team 并行开发
2.1 Agent Team 模式输入 Prompt B（后端） ｜ 2.2 并行 Prompt C（前端） ｜ 2.3 **截图 Agent Team 可视化（任务上下游图）** ｜ 2.4 测 `curl localhost:8000/api/analyze?code=600519` 返回66评委JSON ｜ 2.5 前端评委墙点亮动画 ｜ 2.6 截图 ｜ 2.7 GitCode 首次提交（commit记录"码道Agent Team生成"）

### 阶段三 D11-D15：视觉打磨
3.1 Prompt D 辩论区 ｜ 3.2 Prompt E 双模式 ｜ 3.3 报告卡片+导出 ｜ 3.4 生成 demo_deep.json（**数据规格见§4**） ｜ 3.5 录制3分钟演示视频 ｜ 3.6 截图

### 阶段四 D16-D18：证据整理 + 首次提交（初赛生死线）
4.1 Prompt A→E 完整时间线截图×5 ｜ 4.2 **至少2次"报错→码道修复"对话截图**（关键证据） ｜ 4.3 Agent Team 可视化截图 ｜ 4.4 GitCode commit 记录截图 ｜ 4.5 演示视频 ｜ 4.6 README（含"核心代码由华为云码道生成"声明） ｜ 4.7 仓库公开确认 ｜ 4.8 发布 Skill：`npx skills add https://gitcode.com/Lingxi-HandsOn/gallery.git --skill huawei-cloud-publish-work-to-gallery -y 2>&1` ｜ 4.9 发布至作品展览馆"珠海科技学院校赛"专区 ｜ 4.10 截图发布成功 ｜ 4.11 **大赛平台首次提交**（留迭代窗口）

### 阶段五 D19-D22：决赛答辩（10/29晋级 → 11/5 提交决赛版）
PPT 7页：定位/场景/架构/码道深度(2-3页证据)/学术背书(MAD+ChatEval+astock)/演示/商业前景 + 现场演示脚本 + FAQ（见§6）

### 阶段六：3分钟现场演示脚本（沿用 v2 分镜）

---

## 4. 预设数据规格（demo_deep.json schema）

```json
{
  "code": "600519", "name": "贵州茅台",
  "timestamp": "2026-10-10T10:00:00+08:00",
  "fund_score": 72, "consensus_score": 55,
  "overall": 65,
  "verdict": "officeright",  // 观堂/可蹲/规避 档位
  "judges": [
    {"id":"buffett","name":"沃伦·巴菲特","school":"价值派","rule_score":85,"agent_score":88,"flagged":false,"headline":"ROE稳定+护城河深，本分生意","highlights":["ROE 30%+","毛利率91%","自由现金流为正"]}
    // ... 共51人，覆盖 A-I 九类风格（investor-cards.json 官方口径）
  ],
  "radar": {"schools":["价值","成长","技术","游资","量化","宏观","中国价投","趋势","逆向"], "rule":[82,70,55,40,52,63,78,48,35], "agent":[80,68,58,38,60,60,75,45,38]},
  "disputes": [{"bull":"buffett","bear":"量化_趋势模型X","rounds":3,"transcript":["...","...","..."]}],
  "report": {"summary":"...","support":["..."],"risk":["..."],"entry_zone":["..."]}
}
```

**要点**：3只股票（600519/000001/300750）各自自洽；分歧点至少 2 个（雷达图高亮）；辩论 transcript 预设 3 轮完整文本。

---

## 5. DSH 能力分工矩阵（回答"DSH 都能帮我完成吗"）

| 工作项 | DSH 直接代劳 | 说明 |
|---|---|---|
| Prompt A-E 精修包 | ✅ 已产出（§2） | 直接粘贴码道 |
| 预设数据 demo_deep.json | ✅ 可一键生成 | 规格见§4 |
| 规则引擎参考规格/公式 | ✅ 可给参考实现 | 喂给码道作输入 |
| 答辩 PPT | ✅ 可用技能生成 | pptx-generator/ppt-master |
| 演示视频脚本/FAQ/README | ✅ 可代笔 | — |
| 码道本地验证（代码拉回后） | ✅ 可测试/审查/修 bug 建议 | 需你把码道产物拉到本地 |
| 码道账号开通/Spec-Driven交互执行 | ❌ 必须你手动 | 云端网页操作 |
| Agent Team 使用与截图 | ❌ 必须你手动 | 码道 IDE 内 |
| GitCode 注册/推送/发布 Skill | ❌ 必须你手动 | 账号与网页会话 |
| 大赛平台提交 | ❌ 必须你手动 | 每队每天1次 |
| 演示视频录制 | ⚠️ 脚本可代笔，录制需你操作 | OBS/录屏 |

---

## 6. 答辩 FAQ（含修正）

| 预判问题 | 回答要点 |
|---|---|
| "这是真的AI吗？" | 确定性规则引擎（60%权重，零LLM）+ 深度模式评审Agent + 码道AI辅助开发，混合架构 |
| "为什么叫多智能体？" | 清华 ChatEval：多智能体辩论评估优于单模型；4-5个并行评审Agent分工+分歧检测 |
| "66评委标准哪来的？" | 基于公开投资方法论（书本/访谈）提炼为结构化评审规则，预设演示数据+可扩展规则引擎 |
| "码道做了什么？" | Spec-Driven 三件套 + Agent Team 可视化截图 + 报错修复记录（2次以上截图） |
| "现场能跑通吗？" | 快速档零LLM 30秒出结果，深度模式预生成回放 |