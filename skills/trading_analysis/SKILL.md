# Trading Analysis Skill

## Use When

用户提供 TradingView、Thinkorswim、MT4/MT5 截图，或提供 OHLCV 数据并要求输出趋势、支撑阻力、入场、止损、止盈、风险回报比、复盘记录时使用。CS2 饰品 K 线也可以走本流程，但 SteamDT 单品 K 线通常只有价格 OHLC、没有成交量。

## Priority

1. Protect capital.
2. Do not force trades.
3. Separate observation, setup, trigger, and execution.
4. Always explain invalidation.
5. Record missing data instead of guessing.

## Required Context

- `skills/trading_analysis/rules.md`
- `skills/trading_analysis/output-template.md`
- `docs/chart_analysis_rules.md`
- `docs/risk_management.md`

## Workflow

1. Identify market, symbol, timeframe, source, and whether the chart is intraday or closed-candle.
2. Separate visible facts from interpretation.
3. Determine trend:
   - Bullish: higher highs/higher lows and price above important structure or moving averages.
   - Bearish: lower highs/lower lows and price below important structure or moving averages.
   - Range/chop: unclear structure, repeated fakeouts, or price in the middle of a box.
4. Mark support, resistance, liquidity zones, swing highs/lows, and invalidation.
5. Check setup quality:
   - Trend alignment.
   - Volume or momentum confirmation if visible.
   - For CS2 item klines exported from SteamDT, treat `volume=0` as missing volume, not as bearish volume.
   - For CS2 trades, confirm exitability with spread, same-platform bid, buy depth, sell depth, and T+7 unlock status from the CS2 scanner before producing an entry plan.
   - Risk/reward at least 1:2 unless the user explicitly sets another rule.
   - No nearby invalidation conflict.
6. Produce exactly one primary plan:
   - Long plan.
   - Short plan.
   - Wait/no-trade plan.
7. Include confidence, missing data, and journal note.
8. Save or update the analysis record when operating in the repo.

## Output Rules

Always include:

- Market Context
- Trend
- Key Levels
- Setup
- Entry
- Stop Loss
- Take Profit
- Risk/Reward
- Confirmation Needed
- Invalidation
- Confidence
- Missing Data
- Journal Note

Never present a chart idea as a guaranteed prediction. If the chart is unclear, output a wait/no-trade plan.
