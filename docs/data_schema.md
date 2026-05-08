# 数据结构

## CS2 snapshot

保存路径：

```text
data/snapshots/YYYY-MM-DD-cs2-snapshot.json
```

建议字段：

```json
{
  "snapshot_time": "2026-05-06T12:00:00+08:00",
  "source": ["SteamDT", "CSQAQ"],
  "scan_scope": "watchlist",
  "items": [
    {
      "market_hash_name": "AK-47 | Redline (Field-Tested)",
      "category": "main_weapon",
      "lowest_sell_price": 0,
      "highest_buy_order": 0,
      "sell_order_count": 0,
      "buy_order_count": 0,
      "change_7d_pct": 0,
      "change_30d_pct": 0,
      "drawdown_from_30d_high_pct": 0,
      "bounce_from_30d_low_pct": 0,
      "spread_pct": 0,
      "sector_score": 0,
      "t7_score": 0,
      "chart_analysis": {
        "trend": "bullish",
        "structure_state": "breakout_candidate",
        "trade_bias": "long_setup",
        "chart_score": 8.5,
        "score_adjustment": 2.8,
        "support_zone": [0, 0],
        "resistance_zone": [0, 0],
        "entry_zone": [0, 0],
        "stop_loss": 0,
        "take_profit": 0,
        "confirmation": "",
        "invalidation": ""
      },
      "bucket": "watch"
    }
  ]
}
```

## CS2 discovery snapshot

保存路径：

```text
data/snapshots/YYYY-MM-DD-HHMMSS-cs2-discovery.json
```

核心字段：

- `source.csqaq.source_status`：本次候选来源，例如全量接口、排行榜分页或观察池降级。
- `source.csqaq.is_full_market`：是否可视为全量。
- `filters.price_cap_cny`：单品价格上限，默认 1000。
- `candidates`：动态候选列表。
- `excluded_sample`：被箱子、收藏包、胶囊或价格上限排除的样本。

## Trade journal

保存路径：

```text
data/trades/trade_journal.csv
```

字段：

```text
trade_id,opened_at,closed_at,market,type,symbol,bucket,entry_price,stop_price,target_price,exit_price,size,reason,invalidation,result,review
```

## Chart analysis record

保存路径：

```text
data/charts/journal/YYYYMMDD-HHMMSS-symbol-timeframe.md
```

字段：

- 截图路径。
- 标的和周期。
- 趋势判断。
- 支撑阻力。
- 交易计划。
- 风险回报比。
- 无效条件。
- 复盘结论。

结构化索引：

```text
data/charts/journal/chart_analyses.csv
```

字段：

```text
analysis_id,created_at,source,symbol,timeframe,market,bias,trend,setup_type,entry,stop_loss,take_profit,risk_reward,confidence,status,screenshot_path,data_path,notes,result_at,result_price,result_r,result_notes
```

## OHLCV backtest input

保存路径：

```text
data/charts/ohlcv/*.csv
```

必需字段：

```text
timestamp,open,high,low,close,volume
```

回测输出：

```text
data/backtests/results/*-backtest.json
```

### SteamDT CS2 item kline export

`scripts/export_steamdt_kline.py` 会把 SteamDT `item/v1/kline` 的饰品日 K 转成上面的 OHLCV CSV：

```powershell
python scripts\export_steamdt_kline.py --name "AK-47 | Slate (Factory New)"
```

导出字段仍是：

```text
timestamp,open,high,low,close,volume
```

SteamDT 单品 K 线在这个流程里只有价格 OHLC，没有成交量，所以 `volume` 固定写成 `0`。这代表成交量缺失，不代表成交量为零。CS2 饰品是否可交易仍必须结合扫描器里的点差、同平台求购价、买盘深度、卖单深度、价格上限、品类过滤和 T+7 解锁时间判断。

也可以单独对导出的 CSV 生成图表结构 JSON：

```powershell
python scripts\analyze_cs2_kline.py --csv data\charts\ohlcv\sample.csv
```
