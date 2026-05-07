"""Create a structured chart analysis journal record."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "analysis_id",
    "created_at",
    "source",
    "symbol",
    "timeframe",
    "market",
    "bias",
    "trend",
    "setup_type",
    "entry",
    "stop_loss",
    "take_profit",
    "risk_reward",
    "confidence",
    "status",
    "screenshot_path",
    "data_path",
    "notes",
    "result_at",
    "result_price",
    "result_r",
    "result_notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a chart analysis journal record.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--market", default="")
    parser.add_argument("--source", default="TradingView")
    parser.add_argument("--screenshot", default="")
    parser.add_argument("--data", default="")
    parser.add_argument("--bias", choices=["long", "short", "wait", "no_trade"], default="wait")
    parser.add_argument("--trend", choices=["bullish", "bearish", "range", "unclear"], default="unclear")
    parser.add_argument("--setup-type", default="manual_review")
    parser.add_argument("--entry", default="")
    parser.add_argument("--stop-loss", default="")
    parser.add_argument("--take-profit", default="")
    parser.add_argument("--confidence", choices=["high", "medium", "low"], default="low")
    parser.add_argument("--notes", default="")
    parser.add_argument("--journal", default="data/charts/journal/chart_analyses.csv")
    parser.add_argument("--records-dir", default="data/charts/journal")
    return parser.parse_args()


def to_float(value: str) -> float | None:
    try:
        if value == "":
            return None
        return float(value)
    except ValueError:
        return None


def risk_reward(entry: str, stop: str, target: str, bias: str) -> str:
    entry_f = to_float(entry)
    stop_f = to_float(stop)
    target_f = to_float(target)
    if entry_f is None or stop_f is None or target_f is None:
        return ""
    risk = entry_f - stop_f if bias == "long" else stop_f - entry_f
    reward = target_f - entry_f if bias == "long" else entry_f - target_f
    if risk <= 0 or reward <= 0:
        return ""
    return f"{reward / risk:.2f}"


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in FIELDS} for row in rows])


def markdown_record(row: dict[str, str]) -> str:
    return "\n".join(
        [
            f"# Chart Analysis {row['analysis_id']}",
            "",
            "## Market Context",
            "",
            f"- Source: {row['source']}",
            f"- Symbol: {row['symbol']}",
            f"- Timeframe: {row['timeframe']}",
            f"- Market: {row['market']}",
            f"- Screenshot: {row['screenshot_path'] or 'N/A'}",
            f"- Data: {row['data_path'] or 'N/A'}",
            "",
            "## Plan",
            "",
            f"- Bias: {row['bias']}",
            f"- Trend: {row['trend']}",
            f"- Setup: {row['setup_type']}",
            f"- Entry: {row['entry'] or 'N/A'}",
            f"- Stop Loss: {row['stop_loss'] or 'N/A'}",
            f"- Take Profit: {row['take_profit'] or 'N/A'}",
            f"- Risk/Reward: {row['risk_reward'] or 'N/A'}",
            f"- Confidence: {row['confidence']}",
            f"- Status: {row['status']}",
            "",
            "## Notes",
            "",
            row["notes"] or "N/A",
            "",
            "## Result",
            "",
            "- Result At:",
            "- Result Price:",
            "- Result R:",
            "- Result Notes:",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc).astimezone()
    analysis_id = f"chart-{now.strftime('%Y%m%d-%H%M%S')}-{args.symbol.replace(' ', '_').replace('/', '_')}-{args.timeframe}"
    rr = risk_reward(args.entry, args.stop_loss, args.take_profit, args.bias)
    row = {
        "analysis_id": analysis_id,
        "created_at": now.isoformat(),
        "source": args.source,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "market": args.market,
        "bias": args.bias,
        "trend": args.trend,
        "setup_type": args.setup_type,
        "entry": args.entry,
        "stop_loss": args.stop_loss,
        "take_profit": args.take_profit,
        "risk_reward": rr,
        "confidence": args.confidence,
        "status": "open",
        "screenshot_path": args.screenshot,
        "data_path": args.data,
        "notes": args.notes,
        "result_at": "",
        "result_price": "",
        "result_r": "",
        "result_notes": "",
    }
    journal_path = (ROOT / args.journal).resolve() if not Path(args.journal).is_absolute() else Path(args.journal)
    rows = load_rows(journal_path)
    rows.append(row)
    write_rows(journal_path, rows)

    records_dir = (ROOT / args.records_dir).resolve() if not Path(args.records_dir).is_absolute() else Path(args.records_dir)
    records_dir.mkdir(parents=True, exist_ok=True)
    record_path = records_dir / f"{analysis_id}.md"
    record_path.write_text(markdown_record(row), encoding="utf-8")
    print(f"Wrote chart journal row: {journal_path}")
    print(f"Wrote chart record: {record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

