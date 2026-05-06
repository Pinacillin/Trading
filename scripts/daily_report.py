"""Build a daily trading analyst Markdown report from a CS2 snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a daily report from snapshot files.")
    parser.add_argument("--snapshot-dir", default="data/snapshots")
    parser.add_argument("--snapshot", help="Specific snapshot JSON to render.")
    parser.add_argument("--out", default="reports")
    return parser.parse_args()


BUCKET_LABELS = {
    "breakout": "爆发票",
    "steady": "稳健票",
    "watch": "观察票",
    "not_touch": "不碰票",
}


def latest_snapshot(snapshot_dir: Path) -> Path:
    snapshots = sorted(snapshot_dir.glob("*-cs2-snapshot.json"), key=lambda path: path.stat().st_mtime)
    if not snapshots:
        raise SystemExit(f"No snapshots found in {snapshot_dir}")
    return snapshots[-1]


def fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def one_line(value: Any, limit: int = 300) -> str:
    return " ".join(str(value).split())[:limit]


def item_reason(item: dict[str, Any]) -> str:
    parts = item.get("score_parts", {})
    premium = item.get("bid_premium_pct")
    if premium is not None and item.get("same_platform_exit_used"):
        premium_text = f"，同平台买盘高于最低卖价 {fmt(premium, '%')}"
    elif premium is not None:
        premium_text = f"，跨平台/平台不明买盘高于最低卖价 {fmt(premium, '%')}"
    else:
        premium_text = ""
    return (
        f"7日 {fmt(item.get('change_7d_pct'), '%')}，30日 {fmt(item.get('change_30d_pct'), '%')}，"
        f"回撤 {fmt(item.get('drawdown_from_30d_high_pct'), '%')}，"
        f"点差 {fmt(item.get('spread_pct'), '%')}{premium_text}；"
        f"动量 {parts.get('momentum', 'N/A')} / 抗风险 {parts.get('risk_resilience', 'N/A')} / "
        f"流动性 {parts.get('liquidity', 'N/A')}"
    )


def render_bucket(items: list[dict[str, Any]], bucket: str) -> list[str]:
    label = BUCKET_LABELS[bucket]
    lines = [f"## {label}", ""]
    selected = [item for item in items if item.get("bucket") == bucket]
    if not selected:
        lines += ["暂无。", ""]
        return lines

    for idx, item in enumerate(selected, 1):
        buy_range = item.get("buy_range") or [None, None]
        sector = item.get("sector") or {}
        sector_label = sector.get("name") or sector.get("name_key") or "N/A"
        lines += [
            f"### {idx}. {item.get('market_hash_name')} | T+7 score {item.get('t7_score')}",
            "",
            f"- 数据来源：SteamDT price/batch + item/v1/kline；CSQAQ 指数参考 `{sector_label}`。",
            f"- 买入平台：{item.get('buy_platform') or 'N/A'}；当前最低卖价：{fmt(item.get('lowest_sell_price'))}；最高求购：{fmt(item.get('highest_buy_order'))}。",
            f"- 买入区间：{fmt(buy_range[0])} - {fmt(buy_range[1])}；止损/减仓线：{fmt(item.get('stop_or_reduce_price'))}。",
            f"- 目标价：{fmt(item.get('target_price'))}；强势目标：{fmt(item.get('stretch_target_price'))}。",
            f"- 仓位建议：{item.get('position_suggestion')}",
            f"- T+7 到期处理：{item.get('t7_exit_rule')}",
            f"- 理由：{item_reason(item)}。",
            f"- 无效条件：{item.get('invalidation')}",
        ]
        notes = item.get("data_quality_notes") or []
        if notes:
            lines.append(f"- 数据质量提示：{', '.join(notes)}")
        lines.append("")
    return lines


def render_report(snapshot: dict[str, Any], snapshot_path: Path) -> str:
    items = snapshot.get("items") or []
    indexes = snapshot.get("market_indexes") or []
    discovery = snapshot.get("discovery") or {}
    source = (snapshot.get("source") or {}).get("csqaq", {}).get("discovery") or {}
    lines = [
        "# CS2 T+7 Daily Scan",
        "",
        f"- 扫描时间：{snapshot.get('snapshot_time')}",
        f"- 模式：{snapshot.get('mode', 'watchlist')}",
        f"- 数据状态：{snapshot.get('source_status', 'unknown')}",
        f"- 扫描范围：{snapshot.get('scan_scope')}",
        f"- 候选数量：{snapshot.get('watchlist_count')}",
        f"- 单品价格上限：{fmt(snapshot.get('price_cap_cny'))} CNY；单品仓位上限：{snapshot.get('max_single_item_position_pct', 30)}%。",
        f"- 默认排除：箱子、收藏包、胶囊；本次排除 {snapshot.get('excluded_count', 0)} 个。",
        f"- 快照文件：`{snapshot_path}`",
        "",
        "## 候选来源",
        "",
        f"- 来源状态：{source.get('source_status') or 'N/A'}",
        f"- 是否全量：{source.get('is_full_market') if source else 'N/A'}",
        f"- 是否降级：{source.get('fallback_used') if source else 'N/A'}",
        f"- Discovery 原始数量：{discovery.get('raw_count', 'N/A')}；入围数量：{discovery.get('candidate_count', 'N/A')}；排除数量：{discovery.get('excluded_count', 'N/A')}",
        "",
        "## 市场概况",
        "",
    ]

    if indexes:
        for idx in indexes[:12]:
            lines.append(
                f"- {idx.get('name')} (`{idx.get('name_key')}`)：指数 {fmt(idx.get('market_index'))}，"
                f"涨跌 {fmt(idx.get('chg_rate'), '%')}，更新时间 {idx.get('updated_at')}"
            )
    else:
        lines.append("- CSQAQ 指数不可用，本次评分的板块项按中性处理。")

    lines.append("")
    for bucket in ("breakout", "steady", "watch", "not_touch"):
        lines.extend(render_bucket(items, bucket))

    errors = snapshot.get("errors") or {}
    discovery_errors = discovery.get("errors") or []
    if errors.get("steamdt_price") or errors.get("csqaq") or errors.get("kline") or discovery_errors:
        lines += ["## 数据风险", ""]
        if errors.get("steamdt_price"):
            cache_time = snapshot.get("cache_source_time") or "N/A"
            lines.append(f"- SteamDT 实时价格：{one_line(errors.get('steamdt_price'))}")
            lines.append(f"- 本次使用最近一次成功快照作为缓存参考，缓存时间：{cache_time}。")
        if errors.get("csqaq"):
            lines.append(f"- CSQAQ：{one_line(errors.get('csqaq'))}")
        for error in discovery_errors:
            lines.append(f"- Discovery：{one_line(error)}")
        kline_errors = errors.get("kline") or {}
        for name, error in kline_errors.items():
            lines.append(f"- K线 `{name}`：{one_line(error)}")
        lines.append("")

    lines += [
        "## 执行原则",
        "",
        "- 这份报告是规则扫描，不是自动下单。",
        "- 爆发票优先控制 T+7 锁定风险，稳健票优先看点差和求购深度。",
        "- 观察票必须等价格、板块或流动性确认后再重新评分。",
        "- 不碰票不因为短线涨幅强而破例。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    snapshot_path = Path(args.snapshot) if args.snapshot else latest_snapshot(Path(args.snapshot_dir))
    if not snapshot_path.exists():
        raise SystemExit(f"Snapshot not found: {snapshot_path}")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / snapshot_path.name.replace("-snapshot.json", "-report.md")
    report_path.write_text(render_report(snapshot, snapshot_path), encoding="utf-8")
    print(f"Wrote report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
