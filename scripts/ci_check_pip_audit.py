"""CI helper: parse pip-audit JSON report and fail on HIGH/CRITICAL vulnerabilities."""

from __future__ import annotations

import json
import sys


def main() -> int:
    with open("pip-audit.json", encoding="utf-8") as f:
        data = json.load(f)

    failures: list[tuple[str | None, str | None, str | None, str]] = []
    for dep in data:
        for vuln in dep.get("vulns", []):
            severity = vuln.get("severity", "UNKNOWN")
            if severity in ("HIGH", "CRITICAL"):
                failures.append(
                    (
                        dep.get("name"),
                        dep.get("version"),
                        vuln.get("id"),
                        severity,
                    )
                )

    if failures:
        print(f"FAIL: {len(failures)} HIGH/CRITICAL vulnerabilities found")
        for name, version, vid, severity in failures:
            print(f"  {severity}: {name}@{version} -> {vid}")
        return 1

    print("OK: pip-audit passed, no HIGH/CRITICAL vulnerabilities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
