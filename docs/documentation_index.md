# Documentation Index

本索引用来说明每个文档的职责。新会话不要把所有文件混成同一优先级。

## Entry Documents

| 文件 | 用途 | 什么时候读 |
| --- | --- | --- |
| `AGENTS.md` | 跨会话强制工作规范 | 每个新会话第一步 |
| `README.md` | 项目总览和常用命令 | 每个新会话或用户问“怎么用” |
| `docs/operating_manual.md` | 详细使用手册、流程、故障处理和质检 | 任何实操任务前 |
| `docs/documentation_index.md` | 文档地图 | 不确定该读哪个文档时 |

## Strategy Documents

| 文件 | 用途 | 注意 |
| --- | --- | --- |
| `docs/strategy_rules.md` | 总策略原则 | 不替代具体 CS2 或图表规则 |
| `docs/risk_management.md` | 仓位、R、止损、复盘要求 | 单品 30% 是硬上限，不是默认仓位 |
| `docs/cs2_t7_rules.md` | CS2 T+7 扫描、评分、分组和输出规则 | 推荐类任务的核心规则 |
| `docs/universe_discovery.md` | discovery、watchlist、holdings 的关系 | 防止把观察池当全市场 |
| `docs/chart_analysis_rules.md` | 图表截图/OHLCV/CS2 K 线分析规则 | CS2 K 线缺成交量，必须结合扫描器 |

## Data And Operations

| 文件 | 用途 | 注意 |
| --- | --- | --- |
| `docs/data_schema.md` | 快照、日志、OHLCV、chart_analysis 字段 | 改脚本输出时同步更新 |
| `docs/holdings_import.md` | 持仓安全导入规则 | 禁止账号权限、Cookie、2FA |
| `data/charts/journal/README.md` | 图表日志目录说明 | 只管 journal 目录 |

## API Reference Indexes

| 文件 | 用途 | 注意 |
| --- | --- | --- |
| `docs/SteamDT_llms.txt` | SteamDT API 文档链接索引 | API 可能变化，必要时查官方文档 |
| `docs/CSQAQ_llms.txt` | CSQAQ API 文档链接索引 | CSQAQ 白名单绑定当前公网 IP |

这两个 `llms.txt` 是 API 入口索引，不是交易规则源。交易规则以 `docs/*.md` 和 `AGENTS.md` 为准。

## Skills

| 文件 | 用途 | 注意 |
| --- | --- | --- |
| `skills/cs2_t7_screening/SKILL.md` | CS2 T+7 分析 skill | 读取 `AGENTS.md` 和操作手册后使用 |
| `skills/trading_analysis/SKILL.md` | 通用图表分析 skill | 新图表任务优先使用 |
| `skills/trading_analysis/rules.md` | 图表分析细则 | 和 `docs/chart_analysis_rules.md` 搭配 |
| `skills/trading_analysis/output-template.md` | 图表输出模板 | 生成分析记录时使用 |
| `skills/chart_pattern_analysis/SKILL.md` | 旧版图表 skill | 仅保留兼容，复杂任务用 `trading_analysis` |

## Generated Artifacts

这些文件可以读作样例或最近状态，但不是规范源：

- `data/snapshots/*.json`
- `reports/*.md`
- `data/backtests/results/*`
- `data/charts/ohlcv/*.csv`
- `data/charts/ohlcv/*.json`
- `data/charts/journal/chart-*.md`

生成物默认不提交到 Git，除非用户明确要求保存某个样例。

