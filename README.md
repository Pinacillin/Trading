# Personal Trading Analyst System

这个项目把两个方向合并成一个个人交易分析助手：

1. CS2 饰品 T+7 分析：用 SteamDT、CSQAQ 等数据源做每日扫描、排序、持仓跟踪和复盘。
2. TradingView / KairoTrend 风格图表分析：用固定流程分析截图或行情数据，输出趋势、支撑阻力、入场、止损、止盈和风险回报比。

目标不是让 AI 随口预测，而是让 Codex 按规则做同一件事：读取数据，套用规则，给出计划，记录结果，复盘改进。

## New Session Entry

未来任何 Codex / ChatGPT 会话进入本仓库，先读：

```text
AGENTS.md
docs/operating_manual.md
```

`AGENTS.md` 是跨会话工作规范，规定默认流程、风控边界、检查清单和 Git 同步规则；`docs/operating_manual.md` 是完整使用手册。
如果不知道某个文档负责什么，读 `docs/documentation_index.md`。

## Directory

```text
trading-analyst-system/
  config/                 本地配置样例和观察池
  docs/                   策略、风控、数据结构和分析规则
  data/
    snapshots/            每日扫描原始快照
    trades/               交易记录、持仓记录
    charts/               图表截图和人工标注
    backtests/            回测输入和结果
  reports/                每日扫描报告、复盘报告
  scripts/                数据扫描和报告脚本
  skills/
    cs2_t7_screening/     Codex 的 CS2 T+7 分析 skill
    chart_pattern_analysis/ Codex 的图表分析 skill
```

## First Milestone

- 先把规则写清楚：什么数据可以用，怎么打分，什么时候不交易。
- 第一版扫描器只追求稳定：能读观察池，调用 API，输出候选分组和风险说明。
- 每次推荐都必须分成：爆发票、稳健票、观察票、不碰票。
- 所有交易建议都要写明数据来源、理由、风险、无效条件。
- 默认不分析箱子、收藏包和胶囊；除非单独点名，观察池以皮肤和单张贴纸为主。

## Secrets

不要把 API key 写进代码。复制 `.env.example` 为 `.env` 后只在本机填写：

```powershell
Copy-Item .env.example .env
```

`.env` 已经在 `.gitignore` 中排除。

## Daily CS2 Scan

默认运行 discovery-first 扫描：

```powershell
python scripts\steamdt_scan.py
```

脚本会先拉 CSQAQ 最新候选，再用 SteamDT 做深度验证。默认单品价格上限是 1000 CNY，不碰箱子、收藏包和胶囊；皮肤只看崭新出厂 / Factory New，印花只看全息 / Holo。
每个深度扫描标的还会把 SteamDT 日 K 转成图表结构结论，自动写入总分和日报；但 CS2 单品 K 线没有成交量，所以图表只用于价格结构，T+7 可退出性仍由点差、同平台求购价和买卖深度决定。

检查 CSQAQ 接口状态：

```powershell
python scripts\csqaq_healthcheck.py
```

### CSQAQ IP Whitelist

CSQAQ 的 API Token 绑定的是“当前运行环境的公网 IP”。本地电脑和 Web Codex / Cloud Codex 的公网 IP 不一样，所以每个环境第一次使用时都要各自绑定一次。

本地第一次运行，或本地公网 IP 变化后：

```powershell
python scripts\csqaq_healthcheck.py --bind-ip
```

Web Codex / Cloud Codex 第一次运行，或云端环境重建后，也要在云端终端里重新运行同一条命令：

```bash
python scripts/csqaq_healthcheck.py --bind-ip
```

CSQAQ 的绑定接口限制为 30 秒/次，不要连续点击或连续运行。绑定后等 30 秒，再检查：

```bash
python scripts/csqaq_healthcheck.py
```

看到 `current_data: http=200` 和 `rank_list: http=200` 后，再运行扫描。

只复查观察池：

```text
python scripts\steamdt_scan.py --mode watchlist
```

只复查持仓：

```powershell
python scripts\steamdt_scan.py --mode holdings
```

脚本会输出：

- `data/snapshots/*-cs2-snapshot.json`：结构化快照，保留评分和原始平台价。
- `data/snapshots/*-cs2-discovery.json`：动态候选发现快照。
- `reports/*-cs2-report.md`：可直接阅读的 T+7 日报。

如果 SteamDT 配额触发 `4005`，脚本会自动尝试读取最近一次成功快照，并在报告的数据风险里标记缓存来源；这种报告只能作为观察，不应当当作实时买入依据。

注意：`config/watchlist.csv` 是手工种子池，不代表全市场。由于市场变化快，默认推荐应该走 discovery-first：每次先拉取最新 CSQAQ 候选，再用 SteamDT 深度验证。观察池报告只能说明“池内排序”。更完整的候选发现规则见 `docs/universe_discovery.md`。

## Trading Loop

持仓表：

```text
data/trades/holdings.csv
```

安全导入持仓：

```powershell
python scripts\import_holdings.py your_holdings.csv
```

不要把 Steam 密码、2FA、网页登录 Cookie 或会话权限交给脚本。更多说明见 `docs/holdings_import.md`。

交易记录：

```text
data/trades/trade_journal.csv
```

复查持仓：

```powershell
python scripts\portfolio_review.py
```

复盘 T+7 推荐：

```powershell
python scripts\t7_review.py
```

## Chart Analysis Loop

TradingView / KairoTrend 风格图表分析规则在：

```text
skills/trading_analysis/
docs/chart_analysis_rules.md
```

创建一条图表分析记录：

```powershell
python scripts\new_chart_analysis.py --symbol BTCUSDT --timeframe 1h --market crypto --bias wait --trend range --notes "range middle, wait for breakout"
```

截图放在：

```text
data/charts/screenshots/
```

OHLCV CSV 放在：

```text
data/charts/ohlcv/
```

汇总图表分析复盘：

```powershell
python scripts\summarize_chart_journal.py
```

对 OHLCV CSV 做简单突破策略回测：

```powershell
python scripts\backtest_strategy.py data\charts\ohlcv\sample.csv
```

导出 CS2 饰品日 K 到同一套 OHLCV 工作流：

```powershell
python scripts\export_steamdt_kline.py --name "AK-47 | Slate (Factory New)" --backtest --journal
```

这会生成 `data/charts/ohlcv/*.csv`，字段为 `timestamp,open,high,low,close,volume`。SteamDT 单品 K 线在这里没有成交量，导出的 `volume` 固定为 `0`；分析 CS2 饰品图表时只能把它当作价格结构，是否可交易还必须回到 CS2 扫描器检查点差、同平台求购价、买盘深度、卖单深度和 T+7 退出条件。

单独分析一个已导出的 CS2 K 线 CSV：

```powershell
python scripts\analyze_cs2_kline.py --csv data\charts\ohlcv\sample.csv
```

图表分析 MVP 的目标是先稳定记录 30-50 个样本，再根据实际结果调整规则；不要把单次截图分析当作确定预测。
