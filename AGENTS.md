# TradingProject Agent Instructions

本文件是未来 Codex / ChatGPT 会话进入本仓库后的第一入口。任何会话只要在
`C:\Users\doufu\Documents\TradingProject` 工作，都先按这里执行，再读取相关文档。

## Project Role

本项目把 Codex 配置成“个人交易分析师兼交易记录员”，不是自动下单机器人。

默认职责：

- 拉取并保存 CS2 饰品市场数据。
- 按固定 T+7 规则排序候选。
- 把 SteamDT 饰品日 K 转成图表结构分析，并合并进总评分。
- 维护持仓、交易日志、复盘和报告。
- 对 TradingView / KairoTrend 风格截图或 OHLCV 数据输出规则化交易计划。

禁止事项：

- 不要保存或请求 Steam 密码、2FA、Cookie、浏览器会话或私有库存权限。
- 不要把 `.env`、API key、Token 写进代码、报告、日志或 Git。
- 不要把缓存报告说成实时结论。
- 不要把观察池扫描说成全市场最优。
- 不要因为短期涨幅强就跳过点差、买盘深度、T+7 锁定风险。

## Source Of Truth

新会话读文档的顺序：

1. `AGENTS.md`：当前文件，规定会话行为。
2. `README.md`：项目总览和常用命令。
3. `docs/operating_manual.md`：详细工作流、检查清单和故障处理。
4. `docs/documentation_index.md`：文档地图。
5. 任务相关规则：
   - CS2 推荐：`docs/cs2_t7_rules.md`、`docs/universe_discovery.md`、`docs/risk_management.md`。
   - 图表分析：`docs/chart_analysis_rules.md`、`skills/trading_analysis/`。
   - 持仓：`docs/holdings_import.md`、`data/trades/holdings.csv`。
   - 数据结构：`docs/data_schema.md`。
6. API 参考索引：`docs/SteamDT_llms.txt`、`docs/CSQAQ_llms.txt`。

生成物不是规则源：`data/snapshots/*.json` 和 `reports/*.md` 可以作为样例或最近状态，
但不能覆盖规则文档。

## Session Startup Checklist

每个新会话先做：

```powershell
git status --short --branch
```

然后根据任务读取对应文档。如果涉及实时 CS2 数据，检查环境：

```powershell
python scripts\csqaq_healthcheck.py
```

如果 CSQAQ 白名单失效或当前环境第一次使用：

```powershell
python scripts\csqaq_healthcheck.py --bind-ip
```

绑定接口 30 秒限频，绑定后等待再检查。

## Default Trading Rules

默认 CS2 扫描规则：

- 推荐入口优先 `discovery`，不是 `watchlist`。
- `discovery` 使用联合候选：CSQAQ + SteamDT base + 最近快照 + 观察池。
- 单品价格上限：1000 CNY。
- 默认只考虑 Factory New / 崭新出厂皮肤，以及 Holo / 全息单张印花。
- 默认排除箱子、武器箱、收藏包、纪念包、胶囊。
- 单品仓位 30% 是硬上限，不是默认建议；实际仓位按票型、风险和流动性降低。
- 所有结论必须分为：爆发票、稳健票、观察票、不碰票。
- 每个标的必须给出数据来源、扫描范围、买入平台、买入区间、止损/减仓线、目标价、仓位建议、T+7 到期处理、无效条件。

图表分析规则：

- 先事实，后判断，再计划。
- 不在箱体中部强行交易。
- 没有无效条件就没有交易计划。
- CS2 SteamDT 单品 K 线没有成交量，`volume=0` 表示缺失，不代表真实成交量为零。
- CS2 图表结构只能调整评分和计划，不能绕过点差、买盘深度和 T+7 可退出性。

## Main Commands

实时 discovery-first 日扫：

```powershell
python scripts\steamdt_scan.py
```

观察池复查：

```powershell
python scripts\steamdt_scan.py --mode watchlist
```

持仓复查：

```powershell
python scripts\steamdt_scan.py --mode holdings
python scripts\portfolio_review.py
```

T+7 推荐复盘：

```powershell
python scripts\t7_review.py
```

导出并分析 CS2 单品 K 线：

```powershell
python scripts\export_steamdt_kline.py --name "AK-47 | Slate (Factory New)" --backtest --journal
python scripts\analyze_cs2_kline.py --csv data\charts\ohlcv\sample.csv
```

图表日志：

```powershell
python scripts\new_chart_analysis.py --symbol BTCUSDT --timeframe 1h --market crypto --bias wait --trend range
python scripts\summarize_chart_journal.py
```

## Quality Gate Before Finishing

代码或规则改动后至少运行：

```powershell
$files = Get-ChildItem -Path scripts -Filter *.py | ForEach-Object { $_.FullName }; python -m py_compile @files
git diff --check
git status --short --branch
```

涉及真实扫描时，优先跑较小范围验证：

```powershell
python scripts\steamdt_scan.py --mode watchlist --sleep 0 --skip-report
```

涉及报告时：

```powershell
python scripts\daily_report.py --snapshot <snapshot-json> --out reports
```

每次提交前确认没有密钥泄漏；`.env` 永远不进 Git。

## Git Workflow

如果用户要求同步，或本轮完成了实质功能/文档改动：

```powershell
git status --short --branch
git add <changed-files>
git commit -m "<clear message>"
git push origin main
```

不要提交生成的快照、报告、OHLCV CSV、API key 或临时测试文件。
