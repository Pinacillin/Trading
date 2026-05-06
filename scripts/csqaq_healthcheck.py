"""Bind CSQAQ local IP and check discovery API availability."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bind/check CSQAQ API access.")
    parser.add_argument("--bind-ip", action="store_true", help="Bind current public IP to the ApiToken. CSQAQ limits this to once per 30 seconds.")
    parser.add_argument("--sleep", type=float, default=1.2, help="Delay between calls; CSQAQ documents 1 req/sec.")
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


def request_json(method: str, url: str, token: str, body: Any = None) -> tuple[int | None, str, Any | None]:
    headers = {"ApiToken": token}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            text = response.read().decode("utf-8")
        return response.status, text[:500], json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return exc.code, text[:500], None
    except urllib.error.URLError as exc:
        return None, str(exc.reason)[:500], None


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    token = os.environ.get("CSQAQ_API_KEY")
    base_url = os.environ.get("CSQAQ_BASE_URL", "https://api.csqaq.com").rstrip("/")
    if not token:
        raise SystemExit("Missing CSQAQ_API_KEY in .env")

    checks: list[tuple[str, str, str, Any]] = []
    if args.bind_ip:
        checks.append(("bind_local_ip", "POST", f"{base_url}/api/v1/sys/bind_local_ip", None))
    checks.extend(
        [
            ("current_data", "GET", f"{base_url}/api/v1/current_data?type=init", None),
            ("rank_list", "POST", f"{base_url}/api/v1/info/get_rank_list", {
                "page_index": 1,
                "page_size": 5,
                "show_recently_price": True,
                "filter": {"排序": ["价格_涨幅(7日)_降序(BUFF)"]},
            }),
            ("goods_template", "POST", f"{base_url}/api/v1/goods/get_goods_template", {
                "page_index": 1,
                "page_size": 5,
            }),
            ("popular_goods", "POST", f"{base_url}/api/v1/info/get_popular_goods", None),
        ]
    )

    for idx, (name, method, url, body) in enumerate(checks):
        if idx:
            time.sleep(args.sleep)
        status, text, parsed = request_json(method, url, token, body)
        code = parsed.get("code") if isinstance(parsed, dict) else None
        msg = parsed.get("msg") if isinstance(parsed, dict) else text
        print(f"{name}: http={status} code={code} msg={msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
