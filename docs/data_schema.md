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
data/charts/YYYY-MM-DD-symbol-timeframe.md
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
