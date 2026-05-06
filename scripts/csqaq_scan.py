"""Fetch CSQAQ market and sector indexes."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch CSQAQ market and sector indexes.")
    parser.add_argument("--out", default="data/snapshots")
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


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("CSQAQ_API_KEY")
    base_url = os.environ.get("CSQAQ_BASE_URL", "https://api.csqaq.com")
    if not base_url:
        raise SystemExit("Missing CSQAQ_BASE_URL. Add it to .env when the API contract is confirmed.")

    headers = {"ApiToken": api_key} if api_key else {}
    request = urllib.request.Request(f"{base_url.rstrip('/')}/api/v1/current_data?type=init", headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))

    snapshot = {
        "snapshot_time": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": {"csqaq": {"base_url": base_url, "endpoint": "/api/v1/current_data"}},
        "data": data,
    }
    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-csqaq-index.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote CSQAQ index snapshot: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
