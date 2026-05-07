"""Summarize chart analysis journal outcomes."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize chart analysis journal.")
    parser.add_argument("--journal", default="data/charts/journal/chart_analyses.csv")
    parser.add_argument("--out", default="reports")
    return parser.parse_args()


def to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except ValueError:
        return None


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def pct(value: float) -> str:
    return f"{value:.1f}%"


def safe_group_lines(rows: list[dict[str, str]], key: str) -> list[str]:
    lines: list[str] = []
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row.get(key) or "unknown", []).append(row)
    for name, group_rows in sorted(groups.items()):
        values = [to_float(row.get("result_r")) for row in group_rows]
        values = [value for value in values if value is not None]
        wins = [value for value in values if value > 0]
        avg_r = sum(values) / len(values) if values else None
        win_rate = len(wins) / len(values) * 100 if values else None
        lines.append(
            f"- {name}: total {len(group_rows)}, closed {len(values)}, "
            f"win_rate {pct(win_rate) if win_rate is not None else 'N/A'}, "
            f"avg_R {f'{avg_r:.2f}' if avg_r is not None else 'N/A'}"
        )
    return lines


def main() -> int:
    args = parse_args()
    journal_path = (ROOT / args.journal).resolve() if not Path(args.journal).is_absolute() else Path(args.journal)
    rows = load_rows(journal_path)
    closed = [row for row in rows if to_float(row.get("result_r")) is not None]
    values = [to_float(row.get("result_r")) for row in closed]
    values = [value for value in values if value is not None]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    avg_r = sum(values) / len(values) if values else None
    win_rate = len(wins) / len(values) * 100 if values else None
    max_loss = min(values) if values else None

    lines = [
        "# Chart Journal Summary",
        "",
        f"- Total analyses: {len(rows)}",
        f"- Closed analyses: {len(values)}",
        f"- Win rate: {pct(win_rate) if win_rate is not None else 'N/A'}",
        f"- Average R: {f'{avg_r:.2f}' if avg_r is not None else 'N/A'}",
        f"- Worst R: {f'{max_loss:.2f}' if max_loss is not None else 'N/A'}",
        "",
        "## By Bias",
        "",
    ]
    lines.extend(safe_group_lines(rows, "bias") or ["- N/A"])
    lines.extend(["", "## By Setup", ""])
    lines.extend(safe_group_lines(rows, "setup_type") or ["- N/A"])
    lines.extend(["", "## Open Items", ""])
    open_rows = [row for row in rows if (row.get("status") or "open") == "open"]
    if open_rows:
        for row in open_rows:
            lines.append(f"- {row.get('analysis_id')}: {row.get('symbol')} {row.get('timeframe')} {row.get('bias')}")
    else:
        lines.append("- None")

    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "chart-journal-summary.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote chart journal summary: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
