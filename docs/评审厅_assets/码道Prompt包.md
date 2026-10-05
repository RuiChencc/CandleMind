# 码道 Prompt 包（参赛交付 · 可直接粘贴）

> 来源：SOP v3 §2 精修版 ｜ 统一口径：51 位虚拟评委（UZI 官方名单 A-I 九类风格）
> 使用方式：按 A→E 顺序粘贴给华为云码道 CodeArts，每个 Prompt 一次对话，完成后截图留证

---

## Prompt A（Spec-Driven 初始需求）

```
请使用Spec-Driven模式，帮我创建一个可以运行的Web作品。

作品用途是「多专家AI金融评审厅」，主要用户是希望快速了解个股投资价值的普通投资者。

核心功能：
1. 输入股票代码，规则引擎生成51位虚拟投资评委的骨架评分
2. 51评委头像网格逐人点亮，显示分数与一句话观点
3. 按流派分组展示分歧对比雷达图（8大流派）
4. 规则引擎分与Agent深度分差>30分自动标记分歧点并高亮
5. 评分公式：overall = fund_score × 0.6 + consensus_score × 0.4
6. 快速档（30秒规则引擎）/ 深度回放（预生成数据）双模式
7. 底部多空辩论区：最高分与最低分评委3轮结构化辩论（预设模板+变量替换，不调LLM）

技术栈：后端Python FastAPI，前端HTML+JS（零外部依赖，双击即开），数据层预设演示数据兜底。

界面风格：投行晨金深色（深底 #0a0d14 + 暖金 #ffc857 高亮 + 冷青/玫红辅色，中文优先字体）。

请先生成需求规格文档 spec.md，我确认后再进入方案与任务阶段。
```

---

## Prompt B（后端规则引擎，Agent Team 并行）

```
基于design.md后端设计实现FastAPI：

1. backend/engine/rule_engine.py — 规则引擎核心：
   - 输入股票代码 → 输出51评委评分JSON
   - 每评委：{id, name, school, rule_score, agent_score, headline, highlights}
   - 8大流派预设分组（共51人，UZI官方名单）：经典价值6/成长4/宏观对冲5/技术趋势4/中国价投6/游资22/量化3/AI卡位1
   - 汇总公式：overall = fund_score × 0.6 + consensus_score × 0.4
   - 分歧标记：|agent_score - rule_score| > 30 → flagged=true

2. backend/engine/data_provider.py — 20只股票预设演示数据（覆盖10板块）：
   - 600519 贵州茅台（价值高分/量化中等）
   - 000001 平安银行（技术看多/价值分歧）
   - 300750 宁德时代（成长看多/游资看空）

3. backend/main.py — REST API：
   - GET /api/analyze?code={code} → 完整评分JSON
   - GET /api/health

请实现并启动服务供我测试。
```

---

## Prompt C（前端评审厅，与后端并行）

```
基于design.md前端设计实现评审厅页面：

1. index.html：左侧2/3评委投票墙（51张卡片），右侧1/3流派雷达图+分歧面板，底部辩论区，顶部模式切换+输入框
2. judge-grid.js：51张卡片（首字头像/姓名/流派/评分/headline），加载后逐张点亮，悬停放大
3. radar.js（SVG自绘，零依赖）：8轴8流派，金色=规则引擎 vs 玫红=Agent，差>30轴红色高亮+警告图标
4. cyberpunk.css：#0a0d14背景 + 暖金#ffc857高亮 + 冷青#5cd9ff/玫红#ff5577辅色 + 中文优先字体
5. 数据从 /api/analyze 获取，离线回退 window.DEMO_DATA
```

---

## Prompt D（多空辩论区）

```
页面底部新增多空辩论区：
1. 从51评委选最高分（bull）与最低分（bear）
2. 3轮结构化辩论：bull先发言引用highlights数据 → bear反驳 → 循环；流式打字机逐字显示
3. 辩论结束输出"评审团总结"verdict
4. 辩论内容=预设模板+变量替换，不调真实LLM
5. 样式：bull暖金/bear玫红气泡左右对立，中间动态"分歧线"摆动
```

---

## Prompt E（双模式切换）

```
页面顶部新增模式切换：
1. 快速档：调规则引擎API秒级返回，评委点亮间隔30ms
2. 深度回放：加载 demo_deep.json 模拟深度分析全过程
3. 状态条："快速档·规则引擎｜30秒出结果" / "深度回放·预生成分析"
4. 底部演示控制（仅深度模式可见）：一键重置 / 加速演示 / 跳过辩论
```

---

## 截图留证清单（配合提交证据）

1. Prompt A 对话截图（spec.md 产出时）
2. Prompt B 对话截图（后端完成时）
3. Prompt C 对话截图（前端完成时）
4. Prompt D 对话截图（辩论区完成时）
5. Prompt E 对话截图（双模式完成时）
6. 至少 2 次"报错→码道修复"对话截图（关键证据）
7. Agent Team 可视化截图（并行开发时）
8. GitCode commit 记录截图

> 每个 Prompt 执行后立即截图，日期/时间戳可见，确保"使用证明材料的完整性与真实性"（评分维度 2）。