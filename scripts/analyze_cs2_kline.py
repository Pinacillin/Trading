"""Rule-based CS2 item K-line structure analysis.

This module turns SteamDT daily item candles into a compact chart-analysis
summary that can be embedded in CS2 T+7 scan snapshots and reports. It is price
structure only: SteamDT item klines do not provide reliable volume here.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a CS2 item OHLCV/K-line CSV.")
    parser.add_argument("--csv", required=True, help="CSV with timestamp,open,high,low,close,volume fields.")
    parser.add_argument("--current-price", type=float, help="Optional live price override.")
    parser.add_argument("--out", help="Optional JSON output path.")
    return parser.parse_args()


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return (current - base) / base * 100


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round_price(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def round_pct(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        candles: list[dict[str, Any]] = []
        for row in reader:
            open_ = to_float(row.get("open"))
            high = to_float(row.get("high"))
            low = to_float(row.get("low"))
            close = to_float(row.get("close"))
            if None in (open_, high, low, close):
                continue
            candles.append(
                {
                    "timestamp": row.get("timestamp") or "",
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": to_float(row.get("volume")),
                }
            )
    return candles


def candle_errors(candle: dict[str, Any], index: int) -> list[str]:
    open_ = to_float(candle.get("open"))
    high = to_float(candle.get("high"))
    low = to_float(candle.get("low"))
    close = to_float(candle.get("close"))
    if None in (open_, high, low, close):
        return [f"invalid_candle_{index}"]
    open_f, high_f, low_f, close_f = float(open_), float(high), float(low), float(close)
    errors: list[str] = []
    if min(open_f, high_f, low_f, close_f) <= 0:
        errors.append(f"non_positive_price_{index}")
    if high_f < max(open_f, close_f) or low_f > min(open_f, close_f) or high_f < low_f:
        errors.append(f"inconsistent_ohlc_{index}")
    return errors


def split_valid_candles(candles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    valid: list[dict[str, Any]] = []
    notes: list[str] = []
    for index, candle in enumerate(candles, start=1):
        errors = candle_errors(candle, index)
        if errors:
            notes.extend(errors)
            continue
        valid.append(candle)
    return valid, notes


def timestamp_sort_key(candle: dict[str, Any]) -> tuple[int, str]:
    timestamp = candle.get("timestamp")
    numeric = to_float(timestamp)
    if numeric is not None:
        return (0, f"{numeric:020.6f}")
    if timestamp:
        return (1, str(timestamp))
    return (2, "")


def zone(low: float | None, high: float | None) -> list[float | None]:
    if low is None or high is None:
        return [None, None]
    low_f, high_f = sorted([low, high])
    return [round_price(low_f), round_price(high_f)]


def analyze_candles(candles: list[dict[str, Any]], current_price: float | None = None) -> dict[str, Any]:
    valid, notes = split_valid_candles(candles)
    if all(candle.get("timestamp") not in (None, "") for candle in valid):
        valid = sorted(valid, key=timestamp_sort_key)
    closes = [float(c["close"]) for c in valid]
    highs = [float(c["high"]) for c in valid]
    lows = [float(c["low"]) for c in valid]
    if not valid or not closes:
        return {
            "available": False,
            "candles": 0,
            "trend": "insufficient",
            "structure_state": "insufficient_data",
            "trade_bias": "wait",
            "chart_score": 0,
            "score_adjustment": -4,
            "notes": notes + ["missing_usable_kline"],
        }

    current = float(current_price or closes[-1])
    candle_count = len(valid)
    recent_7 = closes[-8:] if candle_count >= 8 else closes
    recent_30 = closes[-31:] if candle_count >= 31 else closes
    change_7d = pct_change(current, recent_7[0] if recent_7 else None)
    change_30d = pct_change(current, recent_30[0] if recent_30 else None)
    ma7 = mean(closes[-7:])
    ma14 = mean(closes[-14:])
    ma30 = mean(closes[-30:])
    high_14 = max(highs[-14:]) if highs else None
    low_14 = min(lows[-14:]) if lows else None
    high_30 = max(highs[-30:]) if highs else None
    low_30 = min(lows[-30:]) if lows else None
    prior_high_window = highs[-31:-1] if candle_count >= 2 else []
    prior_high_30 = max(prior_high_window) if prior_high_window else high_30
    drawdown_30 = pct_change(current, high_30)
    bounce_30 = pct_change(current, low_30)
    dev_ma7 = pct_change(current, ma7)
    dev_ma30 = pct_change(current, ma30)

    recent_high = max(highs[-15:]) if candle_count >= 15 else max(highs)
    recent_low = min(lows[-15:]) if candle_count >= 15 else min(lows)
    previous_highs = highs[-30:-15] if candle_count >= 30 else highs[:-15]
    previous_lows = lows[-30:-15] if candle_count >= 30 else lows[:-15]
    previous_high = max(previous_highs) if previous_highs else recent_high
    previous_low = min(previous_lows) if previous_lows else recent_low
    higher_high = recent_high > previous_high * 1.005
    higher_low = recent_low > previous_low * 0.995
    lower_high = recent_high < previous_high * 0.995
    lower_low = recent_low < previous_low * 0.995

    if candle_count < 30:
        trend = "insufficient"
    elif ma7 and ma14 and ma30 and current >= ma7 >= ma14 >= ma30 and (higher_high or higher_low):
        trend = "bullish"
    elif ma7 and ma14 and ma30 and current <= ma7 <= ma14 <= ma30 and (lower_high or lower_low):
        trend = "bearish"
    elif high_30 and low_30 and current and ((high_30 - low_30) / current * 100) <= 12:
        trend = "range"
    else:
        trend = "mixed"

    stretched = (dev_ma7 or 0) > 10 or (bounce_30 or 0) > 35
    broke_prior_high = bool(prior_high_30 and current > prior_high_30 * 1.005)
    lost_recent_support = bool(low_14 and current < low_14 * 0.985)
    pullback_depth = abs(drawdown_30 or 0)

    if candle_count < 30:
        state = "insufficient_data"
        trade_bias = "wait"
    elif lost_recent_support or trend == "bearish":
        state = "weak_breakdown"
        trade_bias = "no_trade"
    elif broke_prior_high and not stretched:
        state = "breakout_candidate"
        trade_bias = "long_setup"
    elif trend == "bullish" and 2 <= pullback_depth <= 10 and current >= (ma30 or current):
        state = "pullback_candidate"
        trade_bias = "long_setup"
    elif trend == "bullish" and stretched:
        state = "overextended_no_chase"
        trade_bias = "wait"
    elif trend == "range":
        state = "range_wait_breakout"
        trade_bias = "wait"
    else:
        state = "mixed_wait_confirmation"
        trade_bias = "wait"

    score = 5.0
    if trend == "bullish":
        score += 2.0
    elif trend == "bearish":
        score -= 2.5
    elif trend == "range":
        score -= 0.5
    if higher_high:
        score += 0.8
    if higher_low:
        score += 0.8
    if lower_high:
        score -= 0.8
    if lower_low:
        score -= 0.8
    if state in {"breakout_candidate", "pullback_candidate"}:
        score += 1.4
    if state == "overextended_no_chase":
        score -= 1.2
    if state == "weak_breakdown":
        score -= 2.5
    if state == "insufficient_data":
        score -= 2.0
    score = clamp(score, 0, 10)
    score_adjustment = round((score - 5) * 0.8, 2)

    support_low = low_14
    support_high = max([value for value in (ma14, low_14) if value is not None], default=None)
    resistance_mid = prior_high_30 or high_30
    resistance_zone = zone(resistance_mid * 0.995 if resistance_mid else None, resistance_mid * 1.005 if resistance_mid else None)
    support_zone = zone(support_low, support_high)

    if trade_bias == "long_setup" and state == "breakout_candidate" and resistance_mid:
        entry_zone = zone(resistance_mid * 0.99, current * 1.01)
    elif trade_bias == "long_setup" and support_high:
        entry_zone = zone(support_high * 0.99, current * 1.01)
    else:
        entry_zone = [None, None]

    stop_loss = support_low * 0.98 if trade_bias == "long_setup" and support_low else None
    take_profit = None
    risk_reward = None
    if stop_loss and current > stop_loss:
        take_profit = current + (current - stop_loss) * 2
        risk_reward = 2.0

    if state == "breakout_candidate":
        confirmation = "收盘继续站稳30日前高上方，且T+7扫描器确认同平台买盘和点差没有恶化"
    elif state == "pullback_candidate":
        confirmation = "回踩支撑区后重新收回短均线，且买盘深度未明显下降"
    elif state == "overextended_no_chase":
        confirmation = "等待回踩不破支撑区，或横盘消化后再突破"
    elif state == "weak_breakdown":
        confirmation = "重新收回30日均线和近期支撑前不做T+7计划"
    else:
        confirmation = "等待突破阻力或回踩支撑后的确认K线"

    if support_low:
        invalidation = f"日线收盘跌破近期支撑 {round_price(support_low)}"
    elif ma30:
        invalidation = f"日线收盘跌破30日均线 {round_price(ma30)}"
    else:
        invalidation = "K线样本不足，图表条件无法确认"

    notes.extend(["volume_missing_from_steamdt_kline"])
    if candle_count < 30:
        notes.append("kline_less_than_30_days")

    return {
        "available": True,
        "candles": candle_count,
        "trend": trend,
        "structure_state": state,
        "trade_bias": trade_bias,
        "chart_score": round(score, 2),
        "score_adjustment": score_adjustment,
        "change_7d_pct": round_pct(change_7d),
        "change_30d_pct": round_pct(change_30d),
        "drawdown_from_30d_high_pct": round_pct(drawdown_30),
        "bounce_from_30d_low_pct": round_pct(bounce_30),
        "ma7": round_price(ma7),
        "ma14": round_price(ma14),
        "ma30": round_price(ma30),
        "support_zone": support_zone,
        "resistance_zone": resistance_zone,
        "entry_zone": entry_zone,
        "stop_loss": round_price(stop_loss),
        "take_profit": round_price(take_profit),
        "risk_reward": risk_reward,
        "confirmation": confirmation,
        "invalidation": invalidation,
        "notes": notes,
    }


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")
    result = analyze_candles(load_csv(csv_path), current_price=args.current_price)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Wrote analysis: {out_path}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
