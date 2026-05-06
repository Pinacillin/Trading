# Personal Trading Analyst System

这个项目把两个方向合并成一个个人交易分析助手：

1. CS2 饰品 T+7 分析：用 SteamDT、CSQAQ 等数据源做每日扫描、排序、持仓跟踪和复盘。
2. TradingView / KairoTrend 风格图表分析：用固定流程分析截图或行情数据，输出趋势、支撑阻力、入场、止损、止盈和风险回报比。

目标不是让 AI 随口预测，而是让 Codex 按规则做同一件事：读取数据，套用规则，给出计划，记录结果，复盘改进。

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

脚本会先拉 CSQAQ 最新候选，再用 SteamDT 做深度验证。默认单品价格上限是 1000 CNY，不碰箱子、收藏包和胶囊。

检查 CSQAQ 接口状态：

```powershell
python scripts\csqaq_healthcheck.py
```

只有白名单 IP 变化时才绑定：

```powershell
python scripts\csqaq_healthcheck.py --bind-ip
```

CSQAQ 的绑定接口限制为 30 秒/次，不要连续点击或连续运行。

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
