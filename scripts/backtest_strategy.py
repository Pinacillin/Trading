"""Simple OHLCV backtest for breakout/retest-style rules.

Input CSV columns: timestamp,open,high,low,close,volume
The strategy is intentionally simple and auditable:
- long breakout: close breaks above prior N-bar high
- short breakout: close breaks below prior N-bar low
- stop: ATR multiple
- target: fixed R multiple
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest a simple OHLCV breakout strategy.")
    parser.add_argument("csv_path")
    parser.add_argument("--direction", choices=["long", "short", "both"], default="both")
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--atr-multiple", type=float, default=1.5)
    parser.add_argument("--target-r", type=float, default=2.0)
    parser.add_argument("--out", default="data/backtests/results")
    return parser.parse_args()


def to_float(value: Any) -> float:
    return float(value)


def load_candles(path: Path) -> list[Candle]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            rows.append(
                Candle(
                    timestamp=row.get("timestamp") or row.get("time") or row.get("date") or "",
                    open=to_float(row["open"]),
                    high=to_float(row["high"]),
                    low=to_float(row["low"]),
                    close=to_float(row["close"]),
                    volume=to_float(row.get("volume") or 0),
                )
            )
    return rows


def true_range(current: Candle, previous: Candle | None) -> float:
    if previous is None:
        return current.high - current.low
    return max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close))


def atr(candles: list[Candle], idx: int, period: int) -> float | None:
    if idx < period:
        return None
    ranges = [true_range(candles[i], candles[i - 1] if i else None) for i in range(idx - period + 1, idx + 1)]
    return sum(ranges) / len(ranges)


def run_backtest(candles: list[Candle], direction: str, lookback: int, atr_period: int, atr_multiple: float, target_r: float) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    min_idx = max(lookback, atr_period)
    for idx in range(min_idx, len(candles) - 1):
        prior = candles[idx - lookback : idx]
        candle = candles[idx]
        current_atr = atr(candles, idx, atr_period)
        if current_atr is None or current_atr <= 0:
            continue
        signals: list[str] = []
        if direction in {"long", "both"} and candle.close > max(row.high for row in prior):
            signals.append("long")
        if direction in {"short", "both"} and candle.close < min(row.low for row in prior):
            signals.append("short")
        for signal in signals:
            entry = candle.close
            risk = current_atr * atr_multiple
            stop = entry - risk if signal == "long" else entry + risk
            target = entry + risk * target_r if signal == "long" else entry - risk * target_r
            result = simulate_exit(candles, idx + 1, signal, stop, target, risk)
            trades.append(
                {
                    "entry_time": candle.timestamp,
                    "direction": signal,
                    "entry": round(entry, 6),
                    "stop": round(stop, 6),
                    "target": round(target, 6),
                    "exit_time": result["exit_time"],
                    "exit": round(result["exit"], 6),
                    "result_r": round(result["result_r"], 3),
                }
            )
    return trades


def simulate_exit(candles: list[Candle], start_idx: int, direction: str, stop: float, target: float, risk: float) -> dict[str, Any]:
    for idx in range(start_idx, len(candles)):
        candle = candles[idx]
        if direction == "long":
            if candle.low <= stop:
                return {"exit_time": candle.timestamp, "exit": stop, "result_r": -1.0}
            if candle.high >= target:
                return {"exit_time": candle.timestamp, "exit": target, "result_r": (target - (stop + risk)) / risk}
        else:
            if candle.high >= stop:
                return {"exit_time": candle.timestamp, "exit": stop, "result_r": -1.0}
            if candle.low <= target:
                return {"exit_time": candle.timestamp, "exit": target, "result_r": ((stop - risk) - target) / risk}
    last = candles[-1]
    entry_proxy = stop + risk if direction == "long" else stop - risk
    result_r = (last.close - entry_proxy) / risk if direction == "long" else (entry_proxy - last.close) / risk
    return {"exit_time": last.timestamp, "exit": last.close, "result_r": result_r}


def summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = [trade["result_r"] for trade in trades]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    max_losing_streak = 0
    losing_streak = 0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
        if value <= 0:
            losing_streak += 1
            max_losing_streak = max(max_losing_streak, losing_streak)
        else:
            losing_streak = 0
    return {
        "trades": len(values),
        "win_rate_pct": round(len(wins) / len(values) * 100, 2) if values else None,
        "avg_r": round(sum(values) / len(values), 3) if values else None,
        "max_drawdown_r": round(max_drawdown, 3),
        "max_losing_streak": max_losing_streak,
        "gross_win_r": round(sum(wins), 3),
        "gross_loss_r": round(sum(losses), 3),
    }


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv_path)
    candles = load_candles(csv_path)
    trades = run_backtest(candles, args.direction, args.lookback, args.atr_period, args.atr_multiple, args.target_r)
    result = {
        "created_at": datetime.now().isoformat(),
        "input": str(csv_path),
        "params": {
            "direction": args.direction,
            "lookback": args.lookback,
            "atr_period": args.atr_period,
            "atr_multiple": args.atr_multiple,
            "target_r": args.target_r,
        },
        "summary": summary(trades),
        "trades": trades,
    }
    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{csv_path.stem}-backtest.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote backtest result: {out_path}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

