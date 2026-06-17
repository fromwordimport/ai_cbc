"""CI helper: parse bandit JSON report and fail on HIGH severity issues."""

from __future__ import annotations

import json
import sys


def main() -> int:
    with open("bandit-report.json", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    high = [r for r in results if r.get("issue_severity") == "HIGH"]

    if high:
        print(f"FAIL: {len(high)} High severity issues found")
        for r in high:
            print(
                f"  {r['issue_severity']}: {r['issue_text']} "
                f"at {r['filename']}:{r['line_number']}"
            )
        return 1

    print(f"OK: {len(results)} total issues, {len(high)} High")
    return 0


if __name__ == "__main__":
    sys.exit(main())
