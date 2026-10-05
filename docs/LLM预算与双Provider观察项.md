# LLM 预算与双 Provider 观察项

> 建立：2026-09-30（P0 预算/降级检修轮）。本文件承载**未验证项的触发条件与检查步骤**——未验证不带检查路径 = 永恒未验证。
> 归属：`pa_agent/ai/deepseek_client.py`（`_maybe_fallback` 触发 1-4）+ `pa_agent/ai/llm_usage.py`（计数/冷却/审计）。

## O1. dhap 月超行为（硬拒 / 软超）——触发：次月 1 号

现状：`dhap_monthly_limit=12000` × `cut_ratio=1.1` → 预切线 13200。dhap 平台侧 12000 后行为**未验证**（硬拒 429/403 vs 软超继续扣费）。

- 触发条件：2026-10-01 起，dhap 月计数首次越过 12000
- 检查步骤（按序）：
  1. dhap 控制台（djuhe 平台）核对当月总调用数：12000 内 / 超
  2. 超 12000 后首次调用后，grep bot 日志与 `records/execution_log/llm_usage_dhap_202610.json`：
     - `count` 是否继续增长（→ 软超，预切 = 成本保护）
     - 日志是否有 429/403/APIConnectionError（→ 硬拒，预切 = 防御提前量）
  3. 无控制台时：从 bot 日志首次 429/拒绝时间反推越过 12000 的时刻
- 结论写入方式：本文件「O1 结论」段追加一行（日期 + 硬拒/软超 + 证据文件）

## O2. 商汤额度激活与切换端到端 — 触发：key 到手

现状：`backup_provider` 未配置 → 触发 1/2/4 全部走 WARN 分支，端到端未跑（结构 + 判定单测已覆盖 L1）。

- 触发条件：商汤（sensenova）API key 到手
- 检查步骤：
  1. `config/settings.json` 填 `backup_provider`（`base_url: https://token.sensenova.cn/v1` 等）+ `backup_provider_enabled: true`
  2. 发 `你好` 数次确认主通道正常；再构造触发 1（临时把 `dhap_monthly_limit` 调小如 5）→ 断言回复附「已切至商汤额度」且 `records/execution_log/llm_usage_sensenova_YYYY-MM-DD.json` 有时间戳
  3. 构造触发 4（改回 limit + 清冷却）→ 断言切回 dhap
  4. 商汤 5h 上限 1400 防超：连续调用至窗口占满 → 断言出现「AI 服务暂不可用：主通道（dhap）配额未恢复…」

## 终态评估（~2026-12）

O1 结论 + O2 实测 → 决定：预切线/cut_ratio 是否调整、双满提示文案是否保留、触发 4 是否改为「先耗尽商汤」（**否决先例**：dhap 包月不结转、商汤免费无金钱价值 → 维持恢复即切回）
