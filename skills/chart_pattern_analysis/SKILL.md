# Chart Pattern Analysis Skill

> Legacy note: 新的通用图表流程以 `skills/trading_analysis/` 为准。本 skill 保留给旧会话和简单截图任务；如果涉及 CS2 饰品 K 线、交易日志或复盘，优先读 `AGENTS.md`、`docs/operating_manual.md` 和 `skills/trading_analysis/SKILL.md`。

## Use When

用户提供 TradingView、Thinkorswim、MT4/MT5 图表截图，或要求做图表趋势、支撑阻力、入场止损止盈分析时使用。

## Required Inputs

- 图表截图或 OHLCV 数据。
- 标的、周期、市场，如果截图中无法识别则明确标记缺失。
- 规则文档：`docs/chart_analysis_rules.md` 和 `docs/risk_management.md`。

## Workflow

1. 识别标的、周期、当前价格和图表来源。
2. 判断趋势：上涨、下跌或震荡。
3. 标出支撑、阻力、前高、前低和失效位。
4. 判断形态：突破、回踩、箱体、假突破、反转或趋势延续。
5. 输出做多、做空、等待或不交易计划。
6. 计算风险回报比。
7. 记录复盘字段。

## Output Rules

必须区分：

- 已观察到的事实。
- 基于规则的判断。
- 可以执行的计划。
- 还需要等待的确认。
- 交易失效条件。

缺少数据时必须写明，不允许补编图表上看不到的信息。
