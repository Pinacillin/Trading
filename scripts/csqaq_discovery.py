"""CSQAQ discovery-first candidate generator for CS2 T+7 scans."""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSQAQ_BASE_URL = "https://api.csqaq.com"
DEFAULT_STEAMDT_BASE_URL = "https://open.steamdt.com"
DEFAULT_PROFILE = {
    "price_cap_cny": 1000,
    "excluded_terms": ["case", "weapon case", "capsule", "collection package", "souvenir package"],
    "allowed_skin_wears": ["Factory New", "崭新出厂"],
    "allowed_sticker_terms": ["Holo", "全息"],
    "discovery": {
        "candidate_limit": 120,
        "page_size": 50,
        "max_pages": 5,
        "steamdt_base_cache_hours": 24,
        "recent_snapshot_limit": 80,
    },
}


@dataclass
class DiscoveryCandidate:
    market_hash_name: str
    name: str
    category: str
    current_price: float | None
    sell_count: int | None
    buy_price: float | None
    buy_count: int | None
    change_1d_pct: float | None
    change_7d_pct: float | None
    change_30d_pct: float | None
    source: str
    raw: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover fresh CS2 candidates from CSQAQ.")
    parser.add_argument("--out", default="data/snapshots")
    parser.add_argument("--profile", default="config/trading_profile.json")
    parser.add_argument("--watchlist", default="config/watchlist.csv")
    parser.add_argument("--price-cap", type=float)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--detail-prefetch-limit", type=int)
    parser.add_argument("--include-excluded", action="store_true")
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


def load_profile(path: Path) -> dict[str, Any]:
    profile = json.loads(json.dumps(DEFAULT_PROFILE))
    if path.exists():
        user_profile = json.loads(path.read_text(encoding="utf-8"))
        deep_merge(profile, user_profile)
    return profile


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value


def request_json(method: str, url: str, headers: dict[str, str] | None = None, body: Any = None) -> Any:
    req_headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def api_data(response: Any) -> Any:
    if isinstance(response, dict) and response.get("code") not in (None, 200):
        raise RuntimeError(f"CSQAQ returned {response.get('code')}: {response.get('msg')}")
    return response.get("data", response) if isinstance(response, dict) else response


def to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def best_price(row: dict[str, Any]) -> float | None:
    values = [
        to_float(row.get("lowest_sell_price")),
        to_float(row.get("current_price")),
        to_float(row.get("buff_sell_price")),
        to_float(row.get("yyyp_sell_price")),
        to_float(row.get("c5_sell_price")),
        to_float(row.get("igxe_sell_price")),
        to_float(row.get("r8_sell_price")),
        to_float(row.get("steam_sell_price")),
        to_float(row.get("sell_price")),
        to_float(row.get("price")),
    ]
    values = [value for value in values if value and value > 0]
    return min(values) if values else None


def best_sell_count(row: dict[str, Any]) -> int | None:
    values = [
        to_int(row.get("sell_order_count")),
        to_int(row.get("buff_sell_num")),
        to_int(row.get("yyyp_sell_num")),
        to_int(row.get("c5_sell_num")),
        to_int(row.get("igxe_sell_num")),
        to_int(row.get("sell_num")),
    ]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def best_buy(row: dict[str, Any]) -> tuple[float | None, int | None]:
    prices = [
        to_float(row.get("highest_buy_order")),
        to_float(row.get("buy_price")),
        to_float(row.get("buff_buy_price")),
        to_float(row.get("yyyp_buy_price")),
        to_float(row.get("c5_buy_price")),
        to_float(row.get("steam_buy_price")),
    ]
    counts = [
        to_int(row.get("buy_order_count")),
        to_int(row.get("buy_count")),
        to_int(row.get("buff_buy_num")),
        to_int(row.get("yyyp_buy_num")),
        to_int(row.get("c5_buy_num")),
        to_int(row.get("steam_buy_num")),
    ]
    price_values = [value for value in prices if value and value > 0]
    count_values = [value for value in counts if value is not None]
    return (max(price_values) if price_values else None, max(count_values) if count_values else None)


def category_for(name: str, market_hash_name: str, row: dict[str, Any]) -> str:
    localized = str(row.get("type_localized_name") or row.get("type") or "").lower()
    text = f"{name} {market_hash_name} {localized}".lower()
    if "sticker" in text or "印花" in text:
        return "sticker"
    if "glove" in text or "手套" in text:
        return "gloves"
    if "knife" in text or "匕首" in text:
        return "knife"
    if any(token in text for token in ["ak-47", "m4a", "awp", "usp-s", "glock", "desert eagle", "famas", "galil", "mp9", "mac-10"]):
        return "main_weapon"
    return "skin"


def is_excluded(candidate: DiscoveryCandidate, excluded_terms: list[str]) -> str | None:
    text = f"{candidate.category} {candidate.name} {candidate.market_hash_name}".lower()
    for term in excluded_terms:
        if term.lower() in text:
            return term
    return None


def wear_or_sticker_filter(
    candidate: DiscoveryCandidate,
    allowed_skin_wears: list[str],
    allowed_sticker_terms: list[str],
) -> str | None:
    text = f"{candidate.name} {candidate.market_hash_name}".lower()
    if candidate.category == "sticker":
        if any(term.lower() in text for term in allowed_sticker_terms):
            return None
        return "non_holo_sticker"
    if any(term.lower() in text for term in allowed_skin_wears):
        return None
    return "missing_factory_new_wear"


def parse_candidate(row: dict[str, Any], source: str, id_map: dict[str, dict[str, Any]] | None = None) -> DiscoveryCandidate | None:
    mapped = None
    good_id = str(row.get("good_id") or row.get("id") or "")
    if id_map and good_id:
        mapped = id_map.get(good_id)
    name = str(row.get("name") or (mapped or {}).get("name") or "").strip()
    market_hash_name = str(
        row.get("market_hash_name")
        or row.get("marketHashName")
        or (mapped or {}).get("market_hash_name")
        or ""
    ).strip()
    if not market_hash_name:
        return None
    buy_price, buy_count = best_buy(row)
    return DiscoveryCandidate(
        market_hash_name=market_hash_name,
        name=name,
        category=category_for(name, market_hash_name, row),
        current_price=best_price(row),
        sell_count=best_sell_count(row),
        buy_price=buy_price,
        buy_count=buy_count,
        change_1d_pct=to_float(row.get("sell_price_rate_1") or row.get("change_1d_pct")),
        change_7d_pct=to_float(row.get("sell_price_rate_7") or row.get("change_7d_pct")),
        change_30d_pct=to_float(row.get("sell_price_rate_30") or row.get("change_30d_pct")),
        source=source,
        raw=row,
    )


def fetch_good_detail(base_url: str, headers: dict[str, str], good_id: Any) -> dict[str, Any] | None:
    if good_id in (None, ""):
        return None
    response = request_json("GET", f"{base_url.rstrip()}/api/v1/info/good?{urllib.parse.urlencode({'id': good_id})}", headers=headers)
    data = api_data(response)
    if isinstance(data, dict):
        goods_info = data.get("goods_info")
        return goods_info if isinstance(goods_info, dict) else data
    return None


def discovery_score(candidate: DiscoveryCandidate, price_cap: float) -> float:
    seven = candidate.change_7d_pct or 0
    thirty = candidate.change_30d_pct or 0
    one = candidate.change_1d_pct or 0
    price_score = 12 if candidate.current_price is None else max(0, 12 - max(0, candidate.current_price - price_cap * 0.7) / price_cap * 12)
    liquidity_score = min((candidate.buy_count or 0), 80) / 80 * 18
    supply_score = 10 if candidate.sell_count is None else max(0, 10 - min(candidate.sell_count, 300) / 300 * 6)
    momentum = max(0, min(35, (seven + 5) * 2.2)) + max(0, min(15, (thirty + 8) * 0.8)) + max(0, min(10, (one + 2) * 2.0))
    return round(momentum + liquidity_score + supply_score + price_score, 2)


def candidate_to_dict(candidate: DiscoveryCandidate, score: float) -> dict[str, Any]:
    return {
        "market_hash_name": candidate.market_hash_name,
        "name": candidate.name,
        "category": candidate.category,
        "current_price": candidate.current_price,
        "sell_count": candidate.sell_count,
        "buy_price": candidate.buy_price,
        "buy_count": candidate.buy_count,
        "change_1d_pct": candidate.change_1d_pct,
        "change_7d_pct": candidate.change_7d_pct,
        "change_30d_pct": candidate.change_30d_pct,
        "discovery_score": score,
        "source": candidate.source,
    }


def fetch_current_indexes(base_url: str, api_key: str | None) -> list[dict[str, Any]]:
    headers = {"ApiToken": api_key} if api_key else {}
    response = request_json("GET", f"{base_url.rstrip()}/api/v1/current_data?type=init", headers=headers)
    data = api_data(response)
    return data.get("sub_index_data", []) if isinstance(data, dict) else []


def fetch_all_goods_info(base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = request_json("POST", f"{base_url.rstrip()}/api/v1/goods/get_all_goods_info", headers=headers)
    data = api_data(response)
    return data if isinstance(data, list) else []


def fetch_id_map(base_url: str, headers: dict[str, str]) -> dict[str, dict[str, Any]]:
    response = request_json("POST", f"{base_url.rstrip()}/api/v1/goods/get_all_goods_id", headers=headers)
    data = api_data(response)
    if isinstance(data, dict):
        return {str(key): value for key, value in data.items() if isinstance(value, dict)}
    return {}


def fetch_all_goods_rank(base_url: str, headers: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    id_map = fetch_id_map(base_url, headers)
    response = request_json("POST", f"{base_url.rstrip()}/api/v1/goods/get_all_goods_rank", headers=headers)
    data = api_data(response)
    rank_info = data.get("rank_info", {}) if isinstance(data, dict) else {}
    rows = list(rank_info.values()) if isinstance(rank_info, dict) else []
    return [row for row in rows if isinstance(row, dict)], id_map


def unwrap_steamdt_response(response: Any) -> Any:
    if isinstance(response, dict):
        if response.get("success") is False:
            code = response.get("errorCode") or response.get("code")
            message = response.get("errorCodeStr") or response.get("msg") or response.get("errorMsg")
            raise RuntimeError(f"SteamDT returned failure: {code} {message}")
        return response.get("data", response)
    return response


def flatten_dict_lists(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                rows.append(item)
            else:
                rows.extend(flatten_dict_lists(item))
    elif isinstance(value, dict):
        if any(key in value for key in ("marketHashName", "market_hash_name", "hash_name", "name")):
            rows.append(value)
        for key in ("list", "records", "rows", "items", "data", "result"):
            if key in value:
                rows.extend(flatten_dict_lists(value[key]))
    return rows


def fetch_steamdt_base_rows(
    base_url: str,
    api_key: str | None,
    cache_path: Path,
    cache_hours: float,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    errors: list[str] = []
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours <= cache_hours:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return flatten_dict_lists(cached.get("rows", cached)), "steamdt_base_cache", errors

    if not api_key:
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return flatten_dict_lists(cached.get("rows", cached)), "steamdt_base_cache_stale", ["steamdt_base: missing STEAMDT_API_KEY; using stale cache"]
        return [], "steamdt_base_unavailable", ["steamdt_base: missing STEAMDT_API_KEY"]

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = request_json("GET", f"{base_url.rstrip('/')}/open/cs2/v1/base", headers=headers)
        rows = flatten_dict_lists(unwrap_steamdt_response(response))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "rows": rows}, ensure_ascii=False), encoding="utf-8")
        return rows, "steamdt_base_live", errors
    except RuntimeError as exc:
        errors.append(f"steamdt_base: {exc}")
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return flatten_dict_lists(cached.get("rows", cached)), "steamdt_base_cache_stale", errors
        return [], "steamdt_base_unavailable", errors


def fetch_rank_pages(base_url: str, headers: dict[str, str], page_size: int, max_pages: int, request_sleep: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sort_filters = [
        "价格_涨幅(7日)_降序(BUFF)",
        "价格_涨幅(7日)_降序(悠悠有品)",
        "价格_涨幅(30日)_降序(BUFF)",
        "价格_售价减求购价(百分比)_升序(BUFF)",
    ]
    request_count = 0
    for sort_filter in sort_filters:
        for page in range(1, max_pages + 1):
            if request_count:
                time.sleep(request_sleep)
            body = {
                "page_index": page,
                "page_size": page_size,
                "show_recently_price": True,
                "filter": {"排序": [sort_filter]},
            }
            response = request_json("POST", f"{base_url.rstrip()}/api/v1/info/get_rank_list", headers=headers, body=body)
            request_count += 1
            data = api_data(response)
            page_rows = data.get("data", []) if isinstance(data, dict) else []
            if not page_rows:
                break
            rows.extend([row for row in page_rows if isinstance(row, dict)])
    return rows


def read_watchlist_fallback(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "market_hash_name": row.get("market_hash_name"),
                    "name": row.get("market_hash_name"),
                    "category": row.get("category"),
                    "source_notes": row.get("notes"),
                }
            )
    return rows


def read_recent_snapshot_rows(snapshot_dir: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    snapshots = sorted(snapshot_dir.glob("*-cs2-snapshot.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    seen: set[str] = set()
    for snapshot_path in snapshots:
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in snapshot.get("items", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("market_hash_name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            rows.append(
                {
                    "market_hash_name": name,
                    "name": name,
                    "category": item.get("category"),
                    "lowest_sell_price": item.get("lowest_sell_price"),
                    "highest_buy_order": item.get("highest_buy_order"),
                    "sell_order_count": item.get("sell_order_count"),
                    "buy_order_count": item.get("buy_order_count"),
                    "change_7d_pct": item.get("change_7d_pct"),
                    "change_30d_pct": item.get("change_30d_pct"),
                    "source_notes": f"snapshot={snapshot_path.name}; bucket={item.get('bucket')}; t7_score={item.get('t7_score')}",
                }
            )
            if len(rows) >= limit:
                return rows
    return rows


def source_weight(source: str) -> float:
    if source.startswith("csqaq"):
        return 8
    if source.startswith("local_recent_snapshot"):
        return 5
    if source.startswith("local_watchlist"):
        return 4
    if source.startswith("steamdt_base_live"):
        return 2
    if source.startswith("steamdt_base_cache"):
        return 1
    return 0


def score_for_dedupe(candidate: DiscoveryCandidate, price_cap: float) -> float:
    return discovery_score(candidate, price_cap) + source_weight(candidate.source)


def dedupe_candidates(candidates: list[DiscoveryCandidate], price_cap: float) -> list[DiscoveryCandidate]:
    merged: dict[str, DiscoveryCandidate] = {}
    for candidate in candidates:
        existing = merged.get(candidate.market_hash_name)
        if existing is None or score_for_dedupe(candidate, price_cap) > score_for_dedupe(existing, price_cap):
            merged[candidate.market_hash_name] = candidate
    return list(merged.values())


def build_discovery(profile: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    base_url = os.environ.get("CSQAQ_BASE_URL", DEFAULT_CSQAQ_BASE_URL)
    api_key = os.environ.get("CSQAQ_API_KEY") or os.environ.get("CSQAQ_API_TOKEN")
    steamdt_key = os.environ.get("STEAMDT_API_KEY")
    steamdt_base_url = os.environ.get("STEAMDT_BASE_URL", DEFAULT_STEAMDT_BASE_URL)
    headers = {"ApiToken": api_key or "", "Content-Type": "application/json"}
    price_cap = float(getattr(args, "price_cap", None) or profile.get("price_cap_cny") or 1000)
    limit = int(getattr(args, "limit", None) or profile.get("discovery", {}).get("candidate_limit") or 120)
    page_size = int(profile.get("discovery", {}).get("page_size") or 50)
    max_pages = int(profile.get("discovery", {}).get("max_pages") or 5)
    request_sleep = float(profile.get("discovery", {}).get("request_sleep_seconds") or 1.2)
    steamdt_cache_hours = float(profile.get("discovery", {}).get("steamdt_base_cache_hours") or 24)
    recent_snapshot_limit = int(profile.get("discovery", {}).get("recent_snapshot_limit") or 80)
    excluded_terms = list(profile.get("excluded_terms") or DEFAULT_PROFILE["excluded_terms"])
    allowed_skin_wears = list(profile.get("allowed_skin_wears") or DEFAULT_PROFILE["allowed_skin_wears"])
    allowed_sticker_terms = list(profile.get("allowed_sticker_terms") or DEFAULT_PROFILE["allowed_sticker_terms"])
    detail_prefetch_limit = int(
        getattr(args, "detail_prefetch_limit", None)
        or profile.get("discovery", {}).get("detail_prefetch_limit")
        or min(limit * 3, 40)
    )

    errors: list[str] = []
    csqaq_source_status = "unavailable"
    csqaq_rows: list[dict[str, Any]] = []
    id_map: dict[str, dict[str, Any]] | None = None
    source_counts: dict[str, int] = {}

    for idx, (source_name, fetcher) in enumerate((
        ("csqaq_rank_pages", lambda: (fetch_rank_pages(base_url, headers, page_size, max_pages, request_sleep), None)),
        ("csqaq_all_goods_info", lambda: (fetch_all_goods_info(base_url, headers), None)),
        ("csqaq_all_goods_rank", lambda: fetch_all_goods_rank(base_url, headers)),
    )):
        if idx:
            time.sleep(request_sleep)
        try:
            fetched_rows, id_map = fetcher()
            if fetched_rows:
                csqaq_rows = fetched_rows
                csqaq_source_status = source_name
                break
        except RuntimeError as exc:
            message = f"{source_name}: {exc}"
            errors.append(message)
            if "HTTP 429" in message:
                break

    source_rows: list[tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]] | None]] = []
    if csqaq_rows:
        source_rows.append((csqaq_source_status, csqaq_rows, id_map))
        source_counts[csqaq_source_status] = len(csqaq_rows)

    snapshot_rows = read_recent_snapshot_rows(ROOT / "data" / "snapshots", recent_snapshot_limit)
    if snapshot_rows:
        source_rows.append(("local_recent_snapshot", snapshot_rows, None))
        source_counts["local_recent_snapshot"] = len(snapshot_rows)

    watchlist_rows = read_watchlist_fallback(ROOT / getattr(args, "watchlist", "config/watchlist.csv"))
    if watchlist_rows:
        source_rows.append(("local_watchlist", watchlist_rows, None))
        source_counts["local_watchlist"] = len(watchlist_rows)

    steamdt_rows, steamdt_source_status, steamdt_errors = fetch_steamdt_base_rows(
        steamdt_base_url,
        steamdt_key,
        ROOT / "data" / "snapshots" / "steamdt-base-cache.json",
        steamdt_cache_hours,
    )
    errors.extend(steamdt_errors)
    if steamdt_rows:
        source_rows.append((steamdt_source_status, steamdt_rows, None))
        source_counts[steamdt_source_status] = len(steamdt_rows)

    candidates: list[DiscoveryCandidate] = []
    needs_detail: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    total_raw_count = 0
    for source_name, rows, source_id_map in source_rows:
        total_raw_count += len(rows)
        for row in rows:
            candidate = parse_candidate(row, source_name, source_id_map)
            if not candidate:
                if source_name.startswith("csqaq") and (row.get("id") or row.get("good_id")):
                    needs_detail.append(row)
                continue
            reason = is_excluded(candidate, excluded_terms)
            if reason and not getattr(args, "include_excluded", False):
                excluded.append({"market_hash_name": candidate.market_hash_name, "reason": reason, "source": candidate.source})
                continue
            reason = wear_or_sticker_filter(candidate, allowed_skin_wears, allowed_sticker_terms)
            if reason and not getattr(args, "include_excluded", False):
                excluded.append({"market_hash_name": candidate.market_hash_name, "reason": reason, "source": candidate.source})
                continue
            if candidate.current_price is not None and candidate.current_price > price_cap:
                excluded.append(
                    {
                        "market_hash_name": candidate.market_hash_name,
                        "reason": f"price_above_{price_cap}",
                        "current_price": candidate.current_price,
                        "source": candidate.source,
                    }
                )
                continue
            candidates.append(candidate)

    if needs_detail:
        rough_rows = []
        for row in needs_detail:
            current_price = best_price(row)
            if current_price is not None and current_price > price_cap:
                excluded.append(
                    {
                        "market_hash_name": row.get("name") or row.get("id"),
                        "reason": f"price_above_{price_cap}",
                        "current_price": current_price,
                        "source": csqaq_source_status,
                    }
                )
                continue
            rough_score = discovery_score(
                DiscoveryCandidate(
                    market_hash_name=str(row.get("name") or row.get("id")),
                    name=str(row.get("name") or ""),
                    category=category_for(str(row.get("name") or ""), "", row),
                    current_price=current_price,
                    sell_count=best_sell_count(row),
                    buy_price=best_buy(row)[0],
                    buy_count=best_buy(row)[1],
                    change_1d_pct=to_float(row.get("sell_price_rate_1")),
                    change_7d_pct=to_float(row.get("sell_price_rate_7")),
                    change_30d_pct=to_float(row.get("sell_price_rate_30")),
                    source=csqaq_source_status,
                    raw=row,
                ),
                price_cap,
            )
            rough_rows.append((rough_score, row))
        rough_rows.sort(key=lambda item: item[0], reverse=True)
        for idx, (_, row) in enumerate(rough_rows[:detail_prefetch_limit]):
            if idx:
                time.sleep(request_sleep)
            try:
                detail = fetch_good_detail(base_url, headers, row.get("id") or row.get("good_id"))
            except RuntimeError as exc:
                errors.append(f"csqaq_good_detail:{row.get('id')}: {exc}")
                continue
            if not detail:
                continue
            merged = dict(row)
            merged.update(detail)
            candidate = parse_candidate(merged, f"{csqaq_source_status}+good_detail", id_map)
            if not candidate:
                continue
            reason = is_excluded(candidate, excluded_terms)
            if reason and not getattr(args, "include_excluded", False):
                excluded.append({"market_hash_name": candidate.market_hash_name, "reason": reason, "source": candidate.source})
                continue
            reason = wear_or_sticker_filter(candidate, allowed_skin_wears, allowed_sticker_terms)
            if reason and not getattr(args, "include_excluded", False):
                excluded.append({"market_hash_name": candidate.market_hash_name, "reason": reason, "source": candidate.source})
                continue
            if candidate.current_price is not None and candidate.current_price > price_cap:
                excluded.append(
                    {
                        "market_hash_name": candidate.market_hash_name,
                        "reason": f"price_above_{price_cap}",
                        "current_price": candidate.current_price,
                        "source": candidate.source,
                    }
                )
                continue
            candidates.append(candidate)

    scored = [
        (candidate, discovery_score(candidate, price_cap))
        for candidate in dedupe_candidates(candidates, price_cap)
    ]
    scored.sort(key=lambda row: (row[1] + source_weight(row[0].source), row[1]), reverse=True)
    top = scored[:limit]

    indexes: list[dict[str, Any]] = []
    if not any("HTTP 429" in error for error in errors):
        try:
            indexes = fetch_current_indexes(base_url, api_key)
        except RuntimeError as exc:
            errors.append(f"csqaq_current_data: {exc}")

    return {
        "snapshot_time": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": {
            "csqaq": {
                "base_url": base_url,
                "source_status": csqaq_source_status,
                "is_full_market": csqaq_source_status in {"csqaq_all_goods_info", "csqaq_all_goods_rank"},
                "fallback_used": not bool(csqaq_rows),
            },
            "steamdt": {
                "base_url": steamdt_base_url,
                "source_status": steamdt_source_status,
                "cache_hours": steamdt_cache_hours,
            },
            "local": {
                "watchlist_used": bool(watchlist_rows),
                "recent_snapshot_used": bool(snapshot_rows),
            },
        },
        "source_status": "joint_candidates",
        "source_counts": source_counts,
        "filters": {
            "price_cap_cny": price_cap,
            "candidate_limit": limit,
            "excluded_terms": excluded_terms,
            "allowed_skin_wears": allowed_skin_wears,
            "allowed_sticker_terms": allowed_sticker_terms,
            "include_excluded": getattr(args, "include_excluded", False),
        },
        "market_indexes": indexes,
        "candidates": [candidate_to_dict(candidate, score) for candidate, score in top],
        "excluded_count": len(excluded),
        "excluded_sample": excluded[:50],
        "raw_count": total_raw_count,
        "candidate_count": len(top),
        "errors": errors,
    }


def write_discovery(discovery: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = out_dir / f"{stamp}-cs2-discovery.json"
    path.write_text(json.dumps(discovery, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    profile_path = (ROOT / args.profile).resolve() if not Path(args.profile).is_absolute() else Path(args.profile)
    profile = load_profile(profile_path)
    discovery = build_discovery(profile, args)
    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    path = write_discovery(discovery, out_dir)
    print(f"Wrote discovery: {path}")
    print(
        "Sources: "
        f"csqaq={discovery['source']['csqaq']['source_status']}; "
        f"steamdt={discovery['source']['steamdt']['source_status']}; "
        f"candidates={discovery['candidate_count']}; excluded={discovery['excluded_count']}"
    )
    if discovery.get("errors"):
        print("Warnings:")
        for error in discovery["errors"][:5]:
            print(f"- {error[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
