"""Review T+7 outcomes from saved CS2 snapshots."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ACTIONABLE_BUCKETS = {"breakout", "steady", "watch"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review 7-day outcomes from CS2 snapshots.")
    parser.add_argument("--snapshot-dir", default="data/snapshots")
    parser.add_argument("--out", default="reports")
    parser.add_argument("--days", type=int, default=7)
    return parser.parse_args()


def parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def load_snapshots(path: Path) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for file in sorted(path.glob("*-cs2-snapshot.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        when = parse_time(data.get("snapshot_time"))
        if when:
            data["_path"] = str(file)
            data["_time"] = when
            snapshots.append(data)
    return snapshots


def item_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item.get("market_hash_name"): item for item in snapshot.get("items", []) if item.get("market_hash_name")}


def pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return (current - base) / base * 100


def nearest_future_snapshot(snapshots: list[dict[str, Any]], start: dict[str, Any], days: int) -> dict[str, Any] | None:
    target_seconds = days * 24 * 3600
    candidates = [
        snapshot for snapshot in snapshots
        if (snapshot["_time"] - start["_time"]).total_seconds() >= target_seconds
    ]
    return candidates[0] if candidates else None


def main() -> int:
    args = parse_args()
    snapshot_dir = (ROOT / args.snapshot_dir).resolve() if not Path(args.snapshot_dir).is_absolute() else Path(args.snapshot_dir)
    snapshots = load_snapshots(snapshot_dir)
    rows: list[dict[str, Any]] = []
    for start in snapshots:
        future = nearest_future_snapshot(snapshots, start, args.days)
        if not future:
            continue
        future_items = item_map(future)
        for item in start.get("items", []):
            if item.get("bucket") not in ACTIONABLE_BUCKETS:
                continue
            name = item.get("market_hash_name")
            future_item = future_items.get(name)
            if not future_item:
                continue
            result = pct_change(future_item.get("lowest_sell_price"), item.get("lowest_sell_price"))
            rows.append(
                {
                    "start_time": start.get("snapshot_time"),
                    "review_time": future.get("snapshot_time"),
                    "market_hash_name": name,
                    "bucket": item.get("bucket"),
                    "start_price": item.get("lowest_sell_price"),
                    "review_price": future_item.get("lowest_sell_price"),
                    "return_pct": round(result, 2) if result is not None else None,
                    "start_score": item.get("t7_score"),
                    "review_score": future_item.get("t7_score"),
                }
            )

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp}-t7-review.md"
    lines = ["# CS2 T+7 Review", "", f"- 样本数：{len(rows)}", ""]
    if rows:
        by_bucket: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_bucket.setdefault(row["bucket"], []).append(row)
        for bucket, bucket_rows in by_bucket.items():
            returns = [row["return_pct"] for row in bucket_rows if row["return_pct"] is not None]
            avg_return = sum(returns) / len(returns) if returns else None
            win_rate = len([value for value in returns if value > 0]) / len(returns) * 100 if returns else None
            lines += [
                f"## {bucket}",
                "",
                f"- 数量：{len(bucket_rows)}；平均收益：{avg_return:.2f}%；胜率：{win_rate:.1f}%" if avg_return is not None else f"- 数量：{len(bucket_rows)}；收益数据不足。",
                "",
            ]
        lines += ["## 明细", ""]
        for row in rows:
            lines.append(
                f"- {row['market_hash_name']} | {row['bucket']} | {row['start_price']} -> {row['review_price']} | {row['return_pct']}%"
            )
    else:
        lines.append("暂无跨越 T+7 的快照样本。")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote T+7 review: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
