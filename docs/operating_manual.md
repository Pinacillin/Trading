# Trading Analyst Operating Manual

这份手册的目标是让任何新会话进入本仓库后，都能用同一套流程高效工作。

## 1. 项目当前能力

CS2 T+7 闭环：

- CSQAQ 参与候选发现，并提供大盘/板块指数。
- SteamDT base 参与候选补充；SteamDT price/kline 负责平台价格、求购价、卖单/买盘深度和单品日 K。
- `steamdt_scan.py` 默认 discovery-first，生成结构化快照和 Markdown 日报。
- `analyze_cs2_kline.py` 自动把 SteamDT 日 K 转成图表结构结论，并写入每个标的的 `chart_analysis`。
- `daily_report.py` 输出爆发票、稳健票、观察票、不碰票，并显示图表趋势、支撑阻力、确认条件和无效条件。
- `portfolio_review.py` 管理持仓复查。
- `t7_review.py` 复盘推荐后 7 日结果。

图表分析闭环：

- `skills/trading_analysis/` 保存固定分析流程和输出模板。
- `new_chart_analysis.py` 写入图表分析日志。
- `export_steamdt_kline.py` 可以导出 CS2 单品 K 线为 OHLCV CSV。
- `backtest_strategy.py` 提供基础突破回测。
- `summarize_chart_journal.py` 汇总图表分析样本。

## 2. 会话启动流程

任何新会话先运行：

```powershell
git status --short --branch
```

然后读：

```text
AGENTS.md
README.md
docs/operating_manual.md
docs/documentation_index.md
```

按任务继续读：

- 做 CS2 推荐：`docs/cs2_t7_rules.md`、`docs/universe_discovery.md`、`docs/risk_management.md`。
- 做图表分析：`docs/chart_analysis_rules.md`、`skills/trading_analysis/SKILL.md`。
- 做持仓：`docs/holdings_import.md`、`data/trades/holdings.csv`。
- 改字段或报告：`docs/data_schema.md`、对应脚本。

不要先凭记忆下结论。CS2 市场、API 状态、持仓和报告都是会变化的。

## 3. 环境和密钥

`.env` 只放本机，不进 Git。

需要的变量：

```text
STEAMDT_API_KEY=
CSQAQ_API_KEY=
# Optional alias also accepted:
CSQAQ_API_TOKEN=
```

检查 CSQAQ：

```powershell
python scripts\csqaq_healthcheck.py
```

绑定当前环境公网 IP：

```powershell
python scripts\csqaq_healthcheck.py --bind-ip
```

注意：

- 本地电脑和 Web Codex / Cloud Codex 公网 IP 不同，各自都要绑定。
- 绑定接口 30 秒限频。
- 如果看到 401 或白名单错误，先绑定再等 30 秒检查。

检查 SteamDT：

- `steamdt_scan.py` 会自动使用 `.env`。
- 如果触发 `4005`，报告必须标记缓存或配额风险。
- 不能把缓存扫描写成实时买入结论。

## 4. CS2 每日扫描工作流

默认命令：

```powershell
python scripts\steamdt_scan.py
```

默认流程：

```text
CSQAQ discovery + SteamDT base + 本地观察池 + 最近快照 -> 排除箱子/收藏包/胶囊 -> 只保留 Factory New 皮肤和 Holo 印花 -> SteamDT 深度验证 -> K 线结构分析 -> T+7 评分 -> Markdown 日报
```

候选发现是联合来源：

- CSQAQ 排行榜/全量接口：提供涨幅、价格、热度和板块视角。
- SteamDT `/open/cs2/v1/base`：提供 Steam 官方 `marketHashName` 宇宙，使用 24 小时本地缓存避免频繁打接口。
- `config/watchlist.csv`：保证关注标的不会因为 discovery 失败而漏掉。
- 最近 `data/snapshots/*-cs2-snapshot.json`：在 CSQAQ 异常时保留近期高分/持仓相关标的。

如果 CSQAQ 不可用，系统不会直接空结果，而是降级为 SteamDT/base cache + 本地观察池 + 最近快照。报告会在“候选来源”和“数据风险”里标明这不是完整实时 discovery。

输出：

- `data/snapshots/*-cs2-discovery.json`
- `data/snapshots/*-cs2-snapshot.json`
- `reports/*-cs2-report.md`

报告顶部必须看：

- `数据状态`：live 还是 cached。
- `扫描范围`：discovery、watchlist、holdings 或具体文件。
- `候选来源`：是否全量、是否降级。
- `数据风险`：SteamDT/CSQAQ/K 线错误。

结论解释必须包含：

- 为什么进入该 bucket。
- 数据来源。
- 买入平台和买入区间。
- 止损/减仓线。
- 目标价和强势目标。
- 仓位建议。
- T+7 到期处理。
- 无效条件。
- 图表结构：趋势、状态、支撑、阻力、确认条件。

## 5. 观察池和持仓

观察池不是推荐主入口：

```powershell
python scripts\steamdt_scan.py --mode watchlist
```

只能说“观察池内排序”，不能说“全市场最优”。

持仓扫描：

```powershell
python scripts\steamdt_scan.py --mode holdings
python scripts\portfolio_review.py
```

安全导入持仓：

```powershell
python scripts\import_holdings.py your_holdings.csv
```

不要让脚本登录 Steam、读取私有库存、保存 Cookie 或 2FA。持仓来自用户整理的 CSV。

## 6. 图表和 K 线工作流

CS2 单品日 K 导出：

```powershell
python scripts\export_steamdt_kline.py --name "AK-47 | Slate (Factory New)" --backtest --journal
```

单独分析导出的 CSV：

```powershell
python scripts\analyze_cs2_kline.py --csv data\charts\ohlcv\sample.csv
```

图表结论含义：

- `trend`：bullish、bearish、range、mixed、insufficient。
- `structure_state`：breakout_candidate、pullback_candidate、overextended_no_chase、range_wait_breakout、mixed_wait_confirmation、weak_breakdown。
- `trade_bias`：long_setup、wait、no_trade。
- `score_adjustment`：并入 T+7 总分的小幅调整，不覆盖流动性硬约束。

SteamDT 单品 K 线没有成交量。CSV 中 `volume=0` 是缺失值，不是成交量为零。

TradingView / KairoTrend 风格分析：

```powershell
python scripts\new_chart_analysis.py --symbol BTCUSDT --timeframe 1h --market crypto --bias wait --trend range --notes "range middle, wait for breakout"
python scripts\summarize_chart_journal.py
```

截图放在：

```text
data/charts/screenshots/
```

## 7. 复盘工作流

T+7 推荐复盘：

```powershell
python scripts\t7_review.py
```

图表日志复盘：

```powershell
python scripts\summarize_chart_journal.py
```

复盘必须回答：

- 推荐时 bucket 是什么。
- 推荐后 7 日表现如何。
- 错误来自趋势误判、追高、流动性、板块、数据缺失还是规则过宽。
- 是否需要调整权重。
- 观察池是否需要新增、降级或删除标的。

## 8. 仓位和风控规范

`config/trading_profile.json` 中 `max_single_item_position_pct=30` 是硬上限，不是默认仓位。

默认建议：

- 爆发票：机会仓，除非板块和流动性都极强，否则不接近硬上限。
- 稳健票：标准仓，分批买入。
- 观察票：通常不建仓，最多试错仓。
- 不碰票：不建仓。

如果结论没有止损/减仓线、无效条件和 T+7 到期处理，不允许输出为可执行交易计划。

## 9. 故障处理

CSQAQ：

- 401 / 白名单错误：运行 `python scripts\csqaq_healthcheck.py --bind-ip`。
- 429：等 30 秒以上再试。
- discovery 降级：报告必须写明不是全市场扫描。

SteamDT：

- `4005`：配额或权限相关，扫描器会尝试缓存降级。
- 缓存降级报告只能作为观察。
- K 线缺失时，图表分应降低或标记样本不足。

报告生成失败：

- 先跑 `python scripts\daily_report.py --snapshot <snapshot> --out reports` 定位。
- 检查快照中每个 `items[]` 是否含 `chart_analysis`。

文件名错误：

- CS2 饰品名可能含 `|`、`/`、括号等，写文件必须走脚本内安全文件名逻辑。

## 10. 质量检查

代码改动后：

```powershell
$files = Get-ChildItem -Path scripts -Filter *.py | ForEach-Object { $_.FullName }; python -m py_compile @files
git diff --check
```

工作流改动后：

```powershell
python scripts\steamdt_scan.py --mode watchlist --sleep 0 --skip-report
python scripts\daily_report.py --snapshot <latest-snapshot> --out reports
```

密钥检查思路：

- `.env` 不在 `git status` 里。
- 不在文档、报告、快照中粘贴真实 key。
- 提交前检查 staged diff。

最后：

```powershell
git status --short --branch
```

## 11. Git 和生成物

应该提交：

- `scripts/*.py`
- `docs/*.md`
- `skills/**`
- `config/*.example.*`
- 空目录占位 `.gitkeep`

通常不提交：

- `.env`
- `reports/*.md`
- `data/snapshots/*.json`
- `data/charts/ohlcv/*.csv`
- `data/charts/ohlcv/*.json`
- `data/backtests/results/*`

完成实质改动后：

```powershell
git add <files>
git commit -m "<clear message>"
git push origin main
```
