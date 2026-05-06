"""Import safe, user-provided holdings CSV into data/trades/holdings.csv.

This script does not log in to Steam and does not read browser cookies. It only
normalizes a CSV that the user provides.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "holding_id",
    "opened_at",
    "t7_unlock_at",
    "market_hash_name",
    "category",
    "platform",
    "quantity",
    "entry_price",
    "total_cost",
    "stop_price",
    "target_price",
    "status",
    "plan",
    "notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import user-provided CS2 holdings CSV.")
    parser.add_argument("source", help="CSV with at least market_hash_name, quantity, entry_price.")
    parser.add_argument("--out", default="data/trades/holdings.csv")
    parser.add_argument("--default-category", default="skin")
    parser.add_argument("--default-platform", default="unknown")
    parser.add_argument("--holding-days", type=int, default=7)
    parser.add_argument("--append", action="store_true", help="Append to existing holdings instead of replacing open rows.")
    return parser.parse_args()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_date(value: str | None) -> str:
    if value:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date().isoformat()
            except ValueError:
                pass
    return date.today().isoformat()


def load_existing(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_row(row: dict[str, str], idx: int, args: argparse.Namespace) -> dict[str, str]:
    name = (row.get("market_hash_name") or row.get("name") or row.get("symbol") or "").strip()
    if not name:
        raise ValueError(f"Row {idx} missing market_hash_name/name/symbol")
    quantity = to_float(row.get("quantity") or row.get("qty"), 1.0)
    entry = to_float(row.get("entry_price") or row.get("price") or row.get("buy_price"), 0.0)
    opened_at = normalize_date(row.get("opened_at") or row.get("buy_date") or row.get("date"))
    unlock = row.get("t7_unlock_at")
    if not unlock:
        unlock = (datetime.fromisoformat(opened_at).date() + timedelta(days=args.holding_days)).isoformat()
    total = to_float(row.get("total_cost"), quantity * entry)
    stop = to_float(row.get("stop_price"), entry * 0.95 if entry else 0)
    target = to_float(row.get("target_price"), entry * 1.08 if entry else 0)
    return {
        "holding_id": row.get("holding_id") or f"holding-{datetime.now().strftime('%Y%m%d%H%M%S')}-{idx}",
        "opened_at": opened_at,
        "t7_unlock_at": unlock,
        "market_hash_name": name,
        "category": row.get("category") or args.default_category,
        "platform": row.get("platform") or args.default_platform,
        "quantity": f"{quantity:g}",
        "entry_price": f"{entry:.2f}" if entry else "",
        "total_cost": f"{total:.2f}" if total else "",
        "stop_price": f"{stop:.2f}" if stop else "",
        "target_price": f"{target:.2f}" if target else "",
        "status": row.get("status") or "open",
        "plan": row.get("plan") or "imported holding; review before acting",
        "notes": row.get("notes") or "",
    }


def main() -> int:
    args = parse_args()
    source = Path(args.source)
    out = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        imported = [normalize_row(row, idx + 1, args) for idx, row in enumerate(csv.DictReader(handle))]
    rows = load_existing(out) if args.append else []
    rows.extend(imported)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in FIELDS} for row in rows])
    print(f"Imported {len(imported)} holdings into {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
