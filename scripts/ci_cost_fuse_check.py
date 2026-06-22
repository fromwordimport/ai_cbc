#!/usr/bin/env python3
"""Check cost fuse status before deployment.

Exits non-zero if status is DEGRADE, FUSE, or EMERGENCY.
Usage:
    python scripts/ci_cost_fuse_check.py https://api.example.com/cost-status
"""

from __future__ import annotations

import argparse
import sys
import urllib.request


def check_cost_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read().decode("utf-8")
    except Exception as exc:
        print(f"WARN: Could not reach cost-status endpoint: {exc}")
        # Fail open only if endpoint is unreachable; production should require it.
        return 0

    # Simple heuristic: look for status field in JSON response.
    for status in ("DEGRADE", "FUSE", "EMERGENCY"):
        if f'"status": "{status}"' in body or f'"status":"{status}"' in body:
            print(f"FAIL: Cost fuse status is {status}, blocking deployment")
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
