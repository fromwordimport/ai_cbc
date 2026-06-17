"""Verify a self-hosted AI_CBC stack after `docker compose up`."""

from __future__ import annotations

import argparse
import sys

import httpx


def check(base_url: str, path: str, expected_status: int = 200) -> bool:
    url = f"{base_url}{path}"
    try:
        response = httpx.get(url, timeout=10.0)
    except httpx.RequestError as exc:
        print(f"FAIL {url}: {exc}")
        return False

    ok = response.status_code == expected_status
    status = "PASS" if ok else "FAIL"
    print(f"{status} {url} -> {response.status_code}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost")
    args = parser.parse_args()

    results = [
        check(args.base_url, "/health"),
        check(args.base_url, "/ready"),
    ]

    if all(results):
        print("Stack verification passed")
        return 0
    print("Stack verification failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
