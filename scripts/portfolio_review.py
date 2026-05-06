"""Review current holdings against live SteamDT data."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from steamdt_scan import (
    DEFAULT_STEAMDT_BASE_URL,
    WatchItem,
    compute_item_metrics,
    fetch_csqaq_indexes,
    fetch_steamdt_kline,
    fetch_steamdt_prices,
    load_latest_snapshot,
    load_dotenv,
    load_trading_profile,
)


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review CS2 holdings and T+7 actions.")
    parser.add_argument("--holdings", default="data/trades/holdings.csv")
    parser.add_argument("--profile", default="config/trading_profile.json")
    parser.add_argument("--out", default="reports")
    parser.add_argument("--json-out", default="data/snapshots")
    parser.add_argument("--sleep", type=float, default=0.1)
    return parser.parse_args()


def to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_holdings(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("status") or "open").lower() in {"open", "holding", "active"} and row.get("market_hash_name"):
                rows.append(row)
    return rows


def holding_action(row: dict[str, Any], metrics: dict[str, Any]) -> str:
    entry = to_float(row.get("entry_price"))
    current = to_float(metrics.get("lowest_sell_price"))
    stop = to_float(row.get("stop_price")) or to_float(metrics.get("stop_or_reduce_price"))
    target = to_float(row.get("target_price")) or to_float(metrics.get("target_price"))
    unlock = row.get("t7_unlock_at") or ""
    today = date.today()
    unlocked = False
    if unlock:
        try:
            unlocked = datetime.fromisoformat(unlock).date() <= today
        except ValueError:
            unlocked = False
    if current is None:
        return "数据不足：无法判断，先不加仓。"
    if stop and current <= stop:
        return "触发止损/减仓线：优先减仓或退出。"
    if unlocked and target and current >= target:
        return "T+7已解锁且达到目标：优先止盈减仓。"
    if unlocked and metrics.get("bucket") in {"not_touch", "watch"}:
        return "T+7已解锁但评分不强：减半或退出观察。"
    if entry and current > entry and metrics.get("bucket") == "breakout":
        return "持仓盈利且仍为爆发票：可继续持有，禁止无计划加仓。"
    if metrics.get("bucket") == "not_touch":
        return "评分转弱：不加仓，等待退出窗口。"
    return "继续持有观察，按原计划处理。"


def cached_price_map(snapshot_dir: Path) -> dict[str, dict[str, Any]]:
    snapshot = load_latest_snapshot(snapshot_dir)
    if not snapshot:
        return {}
    return {item.get("market_hash_name"): item for item in snapshot.get("items", []) if item.get("market_hash_name")}


def fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def one_line(value: Any, limit: int = 300) -> str:
    return " ".join(str(value).split())[:limit]


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    profile_path = (ROOT / args.profile).resolve() if not Path(args.profile).is_absolute() else Path(args.profile)
    profile = load_trading_profile(profile_path)
    holdings_path = (ROOT / args.holdings).resolve() if not Path(args.holdings).is_absolute() else Path(args.holdings)
    holdings = load_holdings(holdings_path)
    if not holdings:
        raise SystemExit(f"No active holdings found: {holdings_path}")

    api_key = os.environ.get("STEAMDT_API_KEY")
    if not api_key:
        raise SystemExit("Missing STEAMDT_API_KEY")
    steamdt_base = os.environ.get("STEAMDT_BASE_URL", DEFAULT_STEAMDT_BASE_URL)
    csqaq_base = os.environ.get("CSQAQ_BASE_URL", "https://api.csqaq.com")
    csqaq_key = os.environ.get("CSQAQ_API_KEY")
    indexes, _ = fetch_csqaq_indexes(csqaq_key, csqaq_base)

    names = [row["market_hash_name"] for row in holdings]
    live_prices = True
    errors: list[str] = []
    try:
        prices = fetch_steamdt_prices(names, api_key, steamdt_base)
    except RuntimeError as exc:
        live_prices = False
        errors.append(str(exc))
        prices = {}
    cached_items = cached_price_map(ROOT / "data" / "snapshots") if not live_prices else {}
    reviewed: list[dict[str, Any]] = []
    for row in holdings:
        item = WatchItem(
            category=row.get("category") or "holding",
            market_hash_name=row["market_hash_name"],
            max_buy_price=to_float(row.get("entry_price")),
            notes=row.get("plan") or "",
        )
        if live_prices:
            try:
                candles = fetch_steamdt_kline(item.market_hash_name, api_key, steamdt_base)
            except RuntimeError as exc:
                errors.append(f"{item.market_hash_name}: {exc}")
                candles = []
            metrics = compute_item_metrics(item, prices.get(item.market_hash_name), candles, indexes)
        else:
            metrics = dict(cached_items.get(item.market_hash_name) or compute_item_metrics(item, None, [], indexes))
            notes = list(metrics.get("data_quality_notes") or [])
            notes.append("cached_due_to_steamdt_error")
            metrics["data_quality_notes"] = notes
        reviewed.append({"holding": row, "metrics": metrics, "action": holding_action(row, metrics)})

    snapshot = {
        "snapshot_time": datetime.now(timezone.utc).astimezone().isoformat(),
        "profile": {
            "max_single_item_position_pct": profile.get("max_single_item_position_pct", 30),
            "default_holding_days": profile.get("default_holding_days", 7),
        },
        "source_status": "live" if live_prices else "cached_due_to_steamdt_error",
        "errors": errors,
        "holdings": reviewed,
    }
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    json_dir = (ROOT / args.json_out).resolve()
    json_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_dir / f"{stamp}-portfolio-review.json"
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# CS2 Portfolio Review", "", f"- 时间：{snapshot['snapshot_time']}", f"- 数据状态：{snapshot['source_status']}", ""]
    if errors:
        lines += ["## 数据风险", ""]
        for error in errors:
            lines.append(f"- {one_line(error)}")
        lines.append("")
    for item in reviewed:
        holding = item["holding"]
        metrics = item["metrics"]
        lines += [
            f"## {holding.get('market_hash_name')}",
            "",
            f"- 平台：{holding.get('platform') or 'N/A'}；数量：{holding.get('quantity') or 'N/A'}；买入价：{holding.get('entry_price') or 'N/A'}。",
            f"- 当前最低价：{fmt(metrics.get('lowest_sell_price'))}；评分：{metrics.get('t7_score')}；类别：{metrics.get('bucket')}。",
            f"- 止损/减仓线：{fmt(metrics.get('stop_or_reduce_price'))}；目标价：{fmt(metrics.get('target_price'))}。",
            f"- 操作建议：{item['action']}",
            "",
        ]
    out_dir = (ROOT / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{stamp}-portfolio-review.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote portfolio snapshot: {json_path}")
    print(f"Wrote portfolio report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
