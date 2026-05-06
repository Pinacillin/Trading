"""CS2 T+7 daily scanner.

Reads a watchlist, fetches SteamDT item data and CSQAQ market indexes, computes
rule-based T+7 scores, and writes a JSON snapshot. API keys are loaded from the
environment or a local .env file; never hard-code them in source files.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from csqaq_discovery import build_discovery, load_profile as load_trading_profile, write_discovery


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STEAMDT_BASE_URL = "https://open.steamdt.com"
DEFAULT_CSQAQ_BASE_URL = "https://api.csqaq.com"
DEFAULT_EXCLUDED_CATEGORIES = {"case", "weapon_case", "collection_package", "capsule"}
DEFAULT_EXCLUDED_NAME_TERMS = (
    "case",
    "weapon case",
    "capsule",
    "collection package",
    "souvenir package",
)


@dataclass
class WatchItem:
    category: str
    market_hash_name: str
    max_buy_price: float | None
    notes: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan CS2 items with SteamDT.")
    parser.add_argument("--mode", choices=["discovery", "watchlist", "holdings"], default="discovery")
    parser.add_argument("--profile", default="config/trading_profile.json")
    parser.add_argument("--discovery", help="Existing *-cs2-discovery.json to deep scan.")
    parser.add_argument("--watchlist", default="config/watchlist.csv")
    parser.add_argument("--holdings", default="data/trades/holdings.csv")
    parser.add_argument("--out", default="data/snapshots")
    parser.add_argument("--report-out", default="reports")
    parser.add_argument("--skip-report", action="store_true")
    parser.add_argument("--platform", default="", help="Optional SteamDT platform for kline requests.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between per-item kline calls.")
    parser.add_argument("--price-cap", type=float)
    parser.add_argument("--deep-scan-limit", type=int)
    parser.add_argument(
        "--include-excluded",
        action="store_true",
        help="Include cases, collection packages, and capsules. Default is to exclude them.",
    )
    return parser.parse_args()


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request_json(method: str, url: str, headers: dict[str, str] | None = None, body: Any = None) -> Any:
    data: bytes | None = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error from {url}: {exc.reason}") from exc
    if not text:
        return None
    return json.loads(text)


def is_default_excluded(category: str, market_hash_name: str) -> bool:
    normalized_category = category.strip().lower()
    normalized_name = market_hash_name.strip().lower()
    return normalized_category in DEFAULT_EXCLUDED_CATEGORIES or any(
        term in normalized_name for term in DEFAULT_EXCLUDED_NAME_TERMS
    )


def read_watchlist(path: Path, include_excluded: bool = False) -> tuple[list[WatchItem], list[WatchItem]]:
    rows: list[WatchItem] = []
    excluded: list[WatchItem] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("market_hash_name") or "").strip()
            if not name:
                continue
            max_raw = (row.get("max_buy_price") or "").strip()
            watch_item = WatchItem(
                category=(row.get("category") or "unknown").strip(),
                market_hash_name=name,
                max_buy_price=float(max_raw) if max_raw else None,
                notes=(row.get("notes") or "").strip(),
            )
            if not include_excluded and is_default_excluded(watch_item.category, watch_item.market_hash_name):
                excluded.append(watch_item)
                continue
            rows.append(watch_item)
    return rows, excluded


def read_holdings(path: Path) -> list[WatchItem]:
    if not path.exists():
        return []
    rows: list[WatchItem] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("status") or "open").lower() not in {"open", "holding", "active"}:
                continue
            name = (row.get("market_hash_name") or "").strip()
            if not name:
                continue
            rows.append(
                WatchItem(
                    category=(row.get("category") or "holding").strip(),
                    market_hash_name=name,
                    max_buy_price=None,
                    notes=f"holding_id={row.get('holding_id') or ''}; platform={row.get('platform') or ''}",
                )
            )
    return rows


def watch_items_from_discovery(discovery: dict[str, Any], max_buy_price: float | None, limit: int | None) -> list[WatchItem]:
    candidates = discovery.get("candidates") or []
    rows: list[WatchItem] = []
    for candidate in candidates[:limit]:
        name = (candidate.get("market_hash_name") or "").strip()
        if not name:
            continue
        rows.append(
            WatchItem(
                category=(candidate.get("category") or "unknown").strip(),
                market_hash_name=name,
                max_buy_price=max_buy_price,
                notes=f"discovery_score={candidate.get('discovery_score')}; source={candidate.get('source')}",
            )
        )
    return rows


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def unwrap_response(response: Any, success_key: str = "success") -> Any:
    if isinstance(response, dict):
        if success_key in response and response.get(success_key) is False:
            code = response.get("errorCode") or response.get("code")
            code_str = response.get("errorCodeStr") or response.get("msg") or response.get("errorMsg")
            raise RuntimeError(f"API returned failure: {code} {code_str}")
        return response.get("data", response)
    return response


def pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return (current - base) / base * 100


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_kline(raw_data: Any) -> list[dict[str, float]]:
    data = unwrap_response(raw_data)
    if not isinstance(data, list):
        return []

    candles: list[dict[str, float]] = []
    for item in data:
        if isinstance(item, dict):
            ts = to_float(item.get("timestamp") or item.get("time") or item.get("date") or item.get("t"))
            open_ = to_float(item.get("open") or item.get("o"))
            close = to_float(item.get("close") or item.get("c"))
            high = to_float(item.get("high") or item.get("h"))
            low = to_float(item.get("low") or item.get("l"))
        elif isinstance(item, list) and item and isinstance(item[0], list):
            nested = parse_kline({"data": item})
            candles.extend(nested)
            continue
        elif isinstance(item, list) and len(item) >= 5:
            ts = to_float(item[0])
            open_ = to_float(item[1])
            close = to_float(item[2])
            high = to_float(item[3])
            low = to_float(item[4])
        else:
            continue

        if None in (open_, close, high, low):
            continue
        candles.append(
            {
                "timestamp": ts or 0,
                "open": float(open_),
                "close": float(close),
                "high": float(high),
                "low": float(low),
            }
        )
    return sorted(candles, key=lambda candle: candle["timestamp"])


def parse_price_batch(raw_data: Any) -> dict[str, dict[str, Any]]:
    data = unwrap_response(raw_data)
    results: dict[str, dict[str, Any]] = {}
    if not isinstance(data, list):
        return results

    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("marketHashName") or item.get("market_hash_name") or item.get("name")
        platforms = item.get("dataList") or item.get("data_list") or item.get("platforms") or []
        parsed_platforms: list[dict[str, Any]] = []
        for platform in platforms:
            if not isinstance(platform, dict):
                continue
            sell = to_float(platform.get("sellPrice") or platform.get("sell_price"))
            bid = to_float(platform.get("biddingPrice") or platform.get("bidding_price") or platform.get("buyPrice"))
            parsed_platforms.append(
                {
                    "platform": platform.get("platform") or platform.get("platformName") or "",
                    "sell_price": sell,
                    "sell_count": to_int(platform.get("sellCount") or platform.get("sell_count")),
                    "bidding_price": bid,
                    "bidding_count": to_int(platform.get("biddingCount") or platform.get("bidding_count")),
                    "update_time": platform.get("updateTime") or platform.get("update_time"),
                }
            )
        sell_candidates = [p for p in parsed_platforms if p["sell_price"] and p["sell_price"] > 0]
        bid_candidates = [p for p in parsed_platforms if p["bidding_price"] and p["bidding_price"] > 0]
        lowest = min(sell_candidates, key=lambda p: p["sell_price"], default=None)
        highest_bid = max(bid_candidates, key=lambda p: p["bidding_price"], default=None)
        if name:
            results[str(name)] = {
                "platforms": parsed_platforms,
                "lowest_sell_price": lowest["sell_price"] if lowest else None,
                "lowest_sell_platform": lowest["platform"] if lowest else None,
                "sell_order_count": lowest["sell_count"] if lowest else None,
                "highest_buy_order": highest_bid["bidding_price"] if highest_bid else None,
                "highest_buy_platform": highest_bid["platform"] if highest_bid else None,
                "buy_order_count": highest_bid["bidding_count"] if highest_bid else None,
            }
    return results


def market_index_score(category: str, indexes: list[dict[str, Any]]) -> tuple[float, dict[str, Any] | None]:
    if not indexes:
        return 7.5, None
    category_map = {
        "main_weapon": ["main_weapon", "thousand_weapon"],
        "red_skin": ["covert_weapon"],
        "sticker": ["sticker"],
        "case": ["init"],
        "agent": ["agent"],
        "knife": ["knives"],
    }
    keys = category_map.get(category, [category, "init"])
    matched = next((idx for idx in indexes if idx.get("name_key") in keys), None)
    if matched is None:
        matched = next((idx for idx in indexes if idx.get("name_key") == "init"), indexes[0])
    chg_rate = to_float(matched.get("chg_rate")) or 0.0
    score = clamp(7.5 + chg_rate * 2.2, 0, 15)
    return score, matched


def compute_item_metrics(
    watch_item: WatchItem,
    price_info: dict[str, Any] | None,
    candles: list[dict[str, float]],
    indexes: list[dict[str, Any]],
) -> dict[str, Any]:
    price_info = price_info or {}
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    current_price = price_info.get("lowest_sell_price") or (closes[-1] if closes else None)
    recent_7 = closes[-8:] if len(closes) >= 8 else closes
    recent_30 = closes[-31:] if len(closes) >= 31 else closes
    change_7d = pct_change(current_price, recent_7[0] if recent_7 else None)
    change_30d = pct_change(current_price, recent_30[0] if recent_30 else None)
    high_30 = max(highs[-30:]) if highs else None
    low_30 = min(lows[-30:]) if lows else None
    drawdown_30 = pct_change(current_price, high_30)
    bounce_30 = pct_change(current_price, low_30)
    avg_7 = mean(recent_7)
    avg_30 = mean(recent_30)
    dev_7 = pct_change(current_price, avg_7)
    dev_30 = pct_change(current_price, avg_30)
    bid = price_info.get("highest_buy_order")
    raw_spread_pct = ((current_price - bid) / current_price * 100) if current_price and bid else None
    spread_pct = max(0.0, raw_spread_pct) if raw_spread_pct is not None else None
    bid_premium_pct = abs(raw_spread_pct) if raw_spread_pct is not None and raw_spread_pct < 0 else None
    sector_score, sector = market_index_score(watch_item.category, indexes)

    momentum = clamp(((change_7d or 0) + 3) / 18 * 22, 0, 22)
    momentum += clamp(((change_30d or 0) + 5) / 35 * 12, 0, 12)
    momentum += clamp(((bounce_30 or 0) - 5) / 35 * 6, 0, 6)

    drawdown_abs = abs(drawdown_30 or 0)
    risk = 25
    risk -= clamp(max(0, drawdown_abs - 4) * 0.85, 0, 10)
    risk -= clamp(abs(dev_7 or 0) * 0.55, 0, 6)
    risk -= clamp(abs(dev_30 or 0) * 0.35, 0, 5)
    if watch_item.max_buy_price and current_price and current_price > watch_item.max_buy_price:
        risk -= 5
    risk = clamp(risk, 0, 25)

    spread_score = 8 if spread_pct is None else clamp(8 - max(0, spread_pct - 2) * 1.2, 0, 8)
    buy_depth = price_info.get("buy_order_count") or 0
    sell_depth = price_info.get("sell_order_count") or 0
    depth_score = clamp(min(buy_depth, 50) / 50 * 7, 0, 7)
    supply_score = clamp(5 - min(sell_depth, 300) / 300 * 3, 0, 5)
    liquidity = spread_score + depth_score + supply_score

    data_quality = 0
    if price_info.get("lowest_sell_price"):
        data_quality += 2
    if price_info.get("highest_buy_order"):
        data_quality += 1
    if len(candles) >= 7:
        data_quality += 1
    if len(candles) >= 30:
        data_quality += 1

    sector_score = clamp(sector_score / 15 * 10, 0, 10)
    total_score = round(momentum + risk + liquidity + sector_score + data_quality, 2)
    bucket = classify_item(total_score, change_7d, risk, liquidity, spread_pct, current_price, watch_item.max_buy_price)

    stop_price = round(current_price * 0.95, 2) if current_price else None
    target_price = round(current_price * 1.08, 2) if current_price else None
    stretched_target = round(current_price * 1.15, 2) if current_price else None
    buy_low = round(current_price * 0.98, 2) if current_price else None
    buy_high = round(current_price * 1.01, 2) if current_price else None

    return {
        "market_hash_name": watch_item.market_hash_name,
        "category": watch_item.category,
        "notes": watch_item.notes,
        "buy_platform": price_info.get("lowest_sell_platform"),
        "lowest_sell_price": current_price,
        "highest_buy_order": bid,
        "sell_order_count": price_info.get("sell_order_count"),
        "buy_order_count": price_info.get("buy_order_count"),
        "change_7d_pct": round(change_7d, 2) if change_7d is not None else None,
        "change_30d_pct": round(change_30d, 2) if change_30d is not None else None,
        "drawdown_from_30d_high_pct": round(drawdown_30, 2) if drawdown_30 is not None else None,
        "bounce_from_30d_low_pct": round(bounce_30, 2) if bounce_30 is not None else None,
        "avg_7d": round(avg_7, 2) if avg_7 is not None else None,
        "avg_30d": round(avg_30, 2) if avg_30 is not None else None,
        "deviation_from_7d_avg_pct": round(dev_7, 2) if dev_7 is not None else None,
        "deviation_from_30d_avg_pct": round(dev_30, 2) if dev_30 is not None else None,
        "spread_pct": round(spread_pct, 2) if spread_pct is not None else None,
        "bid_premium_pct": round(bid_premium_pct, 2) if bid_premium_pct is not None else None,
        "sector": sector,
        "score_parts": {
            "momentum": round(momentum, 2),
            "risk_resilience": round(risk, 2),
            "liquidity": round(liquidity, 2),
            "sector": round(sector_score, 2),
            "data_quality": data_quality,
        },
        "t7_score": total_score,
        "bucket": bucket,
        "buy_range": [buy_low, buy_high],
        "stop_or_reduce_price": stop_price,
        "target_price": target_price,
        "stretch_target_price": stretched_target,
        "position_suggestion": position_suggestion(bucket),
        "t7_exit_rule": t7_exit_rule(bucket),
        "invalidation": invalidation_text(bucket),
        "data_quality_notes": data_quality_notes(price_info, candles, indexes),
        "raw_platform_prices": price_info.get("platforms", []),
    }


def classify_item(
    score: float,
    change_7d: float | None,
    risk: float,
    liquidity: float,
    spread_pct: float | None,
    current_price: float | None,
    max_buy_price: float | None,
) -> str:
    if current_price is None:
        return "not_touch"
    if max_buy_price and current_price > max_buy_price:
        return "watch"
    if spread_pct is not None and spread_pct > 12:
        return "not_touch"
    if liquidity < 6:
        return "not_touch"
    if score >= 70 and (change_7d or 0) >= 3 and risk >= 14 and liquidity >= 10:
        return "breakout"
    if score >= 66 and risk >= 18:
        return "steady"
    if score >= 50:
        return "watch"
    return "not_touch"


def position_suggestion(bucket: str) -> str:
    return {
        "breakout": "机会仓；单品不超过总资金30%，只在回踩不破或继续放量时加仓",
        "steady": "标准仓；单品不超过总资金30%，分批买入，避免单点追价",
        "watch": "暂不建标准仓；最多小仓试错，等价格/点差/板块确认",
        "not_touch": "不建仓",
    }[bucket]


def t7_exit_rule(bucket: str) -> str:
    return {
        "breakout": "T+7 解锁时若涨幅达到目标先减仓；跌回买入区下沿则退出",
        "steady": "T+7 解锁时看板块是否继续强于大盘；不强则减半",
        "watch": "T+7 前不主动追；触发确认后重新评分",
        "not_touch": "不进入 T+7 锁定",
    }[bucket]


def invalidation_text(bucket: str) -> str:
    base = "跌破减仓线、点差扩大、求购深度消失或所属板块转弱"
    if bucket == "breakout":
        return base + "；爆发票若 7 日动量断掉，优先兑现风险"
    if bucket == "steady":
        return base + "；稳健票若回撤明显放大，降为观察"
    if bucket == "watch":
        return "未突破/未回踩确认前，交易逻辑不成立"
    return "风险回报比或流动性不满足规则"


def data_quality_notes(price_info: dict[str, Any], candles: list[dict[str, float]], indexes: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    if not price_info.get("lowest_sell_price"):
        notes.append("missing_lowest_sell_price")
    if not price_info.get("highest_buy_order"):
        notes.append("missing_buy_order")
    if len(candles) < 7:
        notes.append("kline_less_than_7_days")
    elif len(candles) < 30:
        notes.append("kline_less_than_30_days")
    if not indexes:
        notes.append("missing_csqaq_index")
    return notes


def fetch_steamdt_prices(names: list[str], api_key: str, base_url: str) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for group in chunked(names, 100):
        url = f"{base_url.rstrip('/')}/open/cs2/v1/price/batch"
        response = request_json("POST", url, headers=headers, body={"marketHashNames": group})
        merged.update(parse_price_batch(response))
    return merged


def fetch_steamdt_kline(name: str, api_key: str, base_url: str, platform: str = "") -> list[dict[str, float]]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body: dict[str, Any] = {"marketHashName": name, "type": 2}
    if platform:
        body["platform"] = platform
    url = f"{base_url.rstrip('/')}/open/cs2/item/v1/kline"
    response = request_json("POST", url, headers=headers, body=body)
    return parse_kline(response)


def fetch_csqaq_indexes(api_key: str | None, base_url: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    url = f"{base_url.rstrip('/')}/api/v1/current_data?{urllib.parse.urlencode({'type': 'init'})}"
    headers = {"ApiToken": api_key} if api_key else {}
    response = request_json("GET", url, headers=headers)
    data = response.get("data", {}) if isinstance(response, dict) else {}
    indexes = data.get("sub_index_data") if isinstance(data, dict) else None
    return indexes if isinstance(indexes, list) else [], response


def write_snapshot(snapshot: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = out_dir / f"{stamp}-cs2-snapshot.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_latest_snapshot(out_dir: Path) -> dict[str, Any] | None:
    snapshots = sorted(out_dir.glob("*-cs2-snapshot.json"), key=lambda path: path.stat().st_mtime)
    if not snapshots:
        return None
    return json.loads(snapshots[-1].read_text(encoding="utf-8"))


def run_report(snapshot_path: Path, report_out: Path) -> None:
    daily_report = ROOT / "scripts" / "daily_report.py"
    subprocess.run(
        [sys.executable, str(daily_report), "--snapshot", str(snapshot_path), "--out", str(report_out)],
        check=True,
    )


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")

    profile_path = (ROOT / args.profile).resolve() if not Path(args.profile).is_absolute() else Path(args.profile)
    profile = load_trading_profile(profile_path)
    price_cap = float(args.price_cap or profile.get("price_cap_cny") or 1000)
    deep_scan_limit = int(args.deep_scan_limit or profile.get("discovery", {}).get("deep_scan_limit") or 40)

    api_key = os.environ.get("STEAMDT_API_KEY")
    if not api_key:
        raise SystemExit("Missing STEAMDT_API_KEY. Put it in .env or your shell environment.")

    discovery: dict[str, Any] | None = None
    excluded_items: list[WatchItem] = []
    scan_scope = args.mode
    if args.mode == "discovery":
        if args.discovery:
            discovery_path = (ROOT / args.discovery).resolve() if not Path(args.discovery).is_absolute() else Path(args.discovery)
            discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
        else:
            discovery = build_discovery(profile, args)
            discovery_path = write_discovery(discovery, (ROOT / args.out).resolve())
            print(f"Wrote discovery: {discovery_path}")
        items = watch_items_from_discovery(discovery, price_cap, deep_scan_limit)
        scan_scope = f"discovery:{discovery.get('source', {}).get('csqaq', {}).get('source_status')}"
    elif args.mode == "holdings":
        holdings = (ROOT / args.holdings).resolve() if not Path(args.holdings).is_absolute() else Path(args.holdings)
        items = read_holdings(holdings)
        scan_scope = str(holdings)
    else:
        watchlist = (ROOT / args.watchlist).resolve() if not Path(args.watchlist).is_absolute() else Path(args.watchlist)
        if not watchlist.exists():
            raise SystemExit(f"Watchlist not found: {watchlist}")
        items, excluded_items = read_watchlist(watchlist, include_excluded=args.include_excluded)
        scan_scope = str(watchlist)

    if not items:
        raise SystemExit(f"No eligible items for mode={args.mode}")

    steamdt_base = os.environ.get("STEAMDT_BASE_URL", DEFAULT_STEAMDT_BASE_URL)
    csqaq_base = os.environ.get("CSQAQ_BASE_URL", DEFAULT_CSQAQ_BASE_URL)
    csqaq_key = os.environ.get("CSQAQ_API_KEY")

    names = [item.market_hash_name for item in items]
    out_dir = (ROOT / args.out).resolve()
    errors: dict[str, Any] = {"kline": {}, "csqaq": None, "steamdt_price": None}
    cached_snapshot: dict[str, Any] | None = None
    live_steamdt_price = True
    try:
        prices = fetch_steamdt_prices(names, api_key, steamdt_base)
    except RuntimeError as exc:
        live_steamdt_price = False
        errors["steamdt_price"] = str(exc)
        cached_snapshot = load_latest_snapshot(out_dir)
        if cached_snapshot is None:
            raise
        prices = {}

    indexes: list[dict[str, Any]] = []
    raw_csqaq: dict[str, Any] | None = None
    try:
        indexes, raw_csqaq = fetch_csqaq_indexes(csqaq_key, csqaq_base)
    except RuntimeError as exc:
        raw_csqaq = {"error": str(exc)}
        errors["csqaq"] = str(exc)

    scored_items: list[dict[str, Any]] = []
    if live_steamdt_price:
        for item in items:
            try:
                candles = fetch_steamdt_kline(item.market_hash_name, api_key, steamdt_base, args.platform)
            except RuntimeError as exc:
                candles = []
                errors["kline"][item.market_hash_name] = str(exc)
            scored_items.append(compute_item_metrics(item, prices.get(item.market_hash_name), candles, indexes))
            if args.sleep:
                time.sleep(args.sleep)
    else:
        cached_items = {
            row.get("market_hash_name"): row for row in (cached_snapshot or {}).get("items", [])
        }
        for item in items:
            cached = dict(cached_items.get(item.market_hash_name) or {})
            if not cached:
                cached = compute_item_metrics(item, None, [], indexes)
            notes = list(cached.get("data_quality_notes") or [])
            if "cached_due_to_steamdt_error" not in notes:
                notes.append("cached_due_to_steamdt_error")
            cached["data_quality_notes"] = notes
            cached["source_status"] = "cached"
            scored_items.append(cached)

    scored_items.sort(key=lambda row: row["t7_score"], reverse=True)
    snapshot = {
        "snapshot_time": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": {
            "steamdt": {
                "base_url": steamdt_base,
                "endpoints": ["/open/cs2/v1/price/batch", "/open/cs2/item/v1/kline"],
            },
            "csqaq": {
                "base_url": csqaq_base,
                "endpoints": ["/api/v1/current_data"],
                "discovery": (discovery or {}).get("source", {}).get("csqaq"),
            },
        },
        "mode": args.mode,
        "scan_scope": scan_scope,
        "source_status": "live" if live_steamdt_price else "cached_due_to_steamdt_error",
        "cache_source_time": (cached_snapshot or {}).get("snapshot_time") if cached_snapshot else None,
        "watchlist_count": len(items),
        "price_cap_cny": price_cap,
        "max_single_item_position_pct": profile.get("max_single_item_position_pct", 30),
        "discovery": {
            "candidate_count": (discovery or {}).get("candidate_count"),
            "raw_count": (discovery or {}).get("raw_count"),
            "excluded_count": (discovery or {}).get("excluded_count"),
            "errors": (discovery or {}).get("errors"),
        },
        "excluded_count": len(excluded_items),
        "excluded_policy": "cases, collection packages, and capsules are excluded by default",
        "excluded_items": [
            {"category": item.category, "market_hash_name": item.market_hash_name, "notes": item.notes}
            for item in excluded_items
        ],
        "market_indexes": indexes,
        "items": scored_items,
        "errors": errors,
    }
    snapshot_path = write_snapshot(snapshot, out_dir)
    print(f"Wrote snapshot: {snapshot_path}")

    if not args.skip_report:
        run_report(snapshot_path, (ROOT / args.report_out).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
