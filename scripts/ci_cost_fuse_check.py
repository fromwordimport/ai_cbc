#!/usr/bin/env python3
"""Check cost fuse status before deployment.

Exits non-zero if fuse_status is DEGRADE, FUSE, or EMERGENCY.
Usage:
    python scripts/ci_cost_fuse_check.py https://api.example.com/cost-status
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def _validate_url(url: str) -> None:
    if not (url.startswith("http://") or url.startswith("https://")):
        raise SystemExit(f"ERROR: URL must use http:// or https:// scheme: {url}")


def check_cost_status(url: str) -> int:
    _validate_url(url)

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read().decode("utf-8")
    except Exception as exc:
        print(f"WARN: Could not reach cost-status endpoint: {exc}")
        # Fail open only if endpoint is unreachable; production should require it.
        return 0

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        print(f"WARN: Invalid JSON from cost-status endpoint: {exc}")
        return 0

    fuse_status = data.get("fuse_status")
    if fuse_status in ("DEGRADE", "FUSE", "EMERGENCY"):
        print(f"FAIL: Cost fuse status is {fuse_status}, blocking deployment")
        return 1

    print("OK: Cost fuse status allows deployment")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check cost fuse before deployment")
    parser.add_argument("url", help="URL of /cost-status endpoint")
    args = parser.parse_args()
    return check_cost_status(args.url)


if __name__ == "__main__":
    sys.exit(main())
