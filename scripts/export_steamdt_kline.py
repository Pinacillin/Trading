"""Export a SteamDT CS2 item kline into the chart-analysis OHLCV format.

SteamDT item klines currently provide daily OHLC price candles, but not
exchange-style volume. The exported CSV writes volume as 0 and downstream
analysis must treat volume confirmation as missing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from steamdt_scan import DEFAULT_STEAMDT_BASE_URL, ROOT, fetch_steamdt_kline, load_dotenv


CSV_FIELDS = ["timestamp", "open", "high", "low", "close", "volume"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export SteamDT item kline to OHLCV CSV.")
    parser.add_argument("--name", "--market-hash-name", dest="market_hash_name", required=True)
    parser.add_argument("--platform", default="", help="Optional SteamDT platform filter.")
    parser.add_argument("--out-dir", default="data/charts/ohlcv")
    parser.add_argument("--filename", help="Optional CSV filename. Defaults to a safe item-name slug.")
    parser.add_argument("--source", default="SteamDT")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--backtest", action="store_true", help="Run the breakout backtest after export.")
    parser.add_argument("--journal", action="store_true", help="Create a wait/no-trade chart journal stub.")
    parser.add_argument("--base-url", default=os.environ.get("STEAMDT_BASE_URL", DEFAULT_STEAMDT_BASE_URL))
    return parser.parse_args()


def safe_filename(name: str) -> str:
    normalized = name.strip().lower()
    normalized = normalized.replace("|", " ")
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"[^a-z0-9._-]+", "-", normalized)
    normalized = normalized.strip(".-_") or "steamdt-item"
    if normalized.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
        normalized = f"{normalized}-item"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"{normalized[:90]}-{digest}.csv"


def normalize_output_filename(filename: str) -> str:
    candidate = Path(filename).name
    if candidate.lower().endswith(".csv"):
        candidate = candidate[:-4]
    candidate = re.sub(r"\s+", "-", candidate.strip())
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate)
    candidate = candidate.strip(".-_") or "steamdt-kline"
    if candidate.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
        candidate = f"{candidate}-item"
    return f"{candidate[:100]}.csv"


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path


def validate_candles(candles: list[dict[str, float]]) -> None:
    if not candles:
        raise SystemExit("SteamDT returned no usable kline candles for this item.")
    previous_ts: float | None = None
    for index, candle in enumerate(candles, start=1):
        required = ("timestamp", "open", "high", "low", "close")
        missing = [field for field in required if field not in candle]
        if missing:
            raise SystemExit(f"Candle {index} is missing fields: {', '.join(missing)}")
        open_ = float(candle["open"])
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        timestamp = float(candle["timestamp"])
        if timestamp <= 0:
            raise SystemExit(f"Candle {index} is missing a valid timestamp.")
        if min(open_, high, low, close) <= 0:
            raise SystemExit(f"Candle {index} contains non-positive prices.")
        if high < max(open_, close) or low > min(open_, close) or high < low:
            raise SystemExit(f"Candle {index} has inconsistent OHLC values.")
        if previous_ts is not None and timestamp < previous_ts:
            raise SystemExit("Kline candles are not sorted by timestamp.")
        previous_ts = timestamp


def write_csv(path: Path, candles: list[dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for candle in candles:
            writer.writerow(
                {
                    "timestamp": format_timestamp(candle["timestamp"]),
                    "open": f"{float(candle['open']):.6f}".rstrip("0").rstrip("."),
                    "high": f"{float(candle['high']):.6f}".rstrip("0").rstrip("."),
                    "low": f"{float(candle['low']):.6f}".rstrip("0").rstrip("."),
                    "close": f"{float(candle['close']):.6f}".rstrip("0").rstrip("."),
                    "volume": "0",
                }
            )


def format_timestamp(value: float) -> str:
    if value <= 0:
        return ""
    seconds = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
    except (OSError, OverflowError, ValueError):
        return str(int(value))


def write_metadata(path: Path, args: argparse.Namespace, candles: list[dict[str, float]]) -> None:
    meta_path = path.with_suffix(".json")
    payload = {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": args.source,
        "market": "CS2",
        "symbol": args.market_hash_name,
        "platform": args.platform,
        "timeframe": args.timeframe,
        "csv_path": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
        "candles": len(candles),
        "first_timestamp": format_timestamp(candles[0]["timestamp"]),
        "last_timestamp": format_timestamp(candles[-1]["timestamp"]),
        "volume_note": "SteamDT item/v1/kline does not provide volume here; exported volume is 0.",
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_backtest(csv_path: Path) -> None:
    script = ROOT / "scripts" / "backtest_strategy.py"
    subprocess.run([sys.executable, str(script), str(csv_path)], check=True)


def create_journal(args: argparse.Namespace, csv_path: Path) -> None:
    script = ROOT / "scripts" / "new_chart_analysis.py"
    notes = (
        "SteamDT CS2 daily item kline export. Volume is missing and stored as 0; "
        "use CS2 scan liquidity fields for exitability before any trade plan."
    )
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            args.market_hash_name,
            "--timeframe",
            args.timeframe,
            "--market",
            "CS2",
            "--source",
            args.source,
            "--data",
            str(csv_path.relative_to(ROOT) if csv_path.is_relative_to(ROOT) else csv_path),
            "--bias",
            "wait",
            "--trend",
            "unclear",
            "--setup-type",
            "kline_export_review",
            "--confidence",
            "low",
            "--notes",
            notes,
        ],
        check=True,
    )


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("STEAMDT_API_KEY")
    if not api_key:
        raise SystemExit("Missing STEAMDT_API_KEY. Put it in .env or your shell environment.")

    candles = fetch_steamdt_kline(args.market_hash_name, api_key, args.base_url, args.platform)
    validate_candles(candles)

    out_dir = resolve_path(args.out_dir)
    filename = normalize_output_filename(args.filename) if args.filename else safe_filename(args.market_hash_name)
    out_path = out_dir / filename
    write_csv(out_path, candles)
    write_metadata(out_path, args, candles)

    print(f"Wrote OHLCV CSV: {out_path}", flush=True)
    print(f"Wrote metadata: {out_path.with_suffix('.json')}", flush=True)
    print("Volume note: SteamDT kline volume is unavailable; exported volume is 0.", flush=True)

    if args.backtest:
        run_backtest(out_path)
    if args.journal:
        create_journal(args, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
