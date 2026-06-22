#!/usr/bin/env python3
"""Parse pytest JUnit XML and fail if red-team defense rate is below threshold."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_THRESHOLD = 0.95


def main() -> int:
    xml_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("test-results/redteam-fast.xml")
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_THRESHOLD

    if not xml_path.exists():
        print(f"FAIL: XML report not found: {xml_path}")
        return 1

    root = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    total = int(root.get("tests", "0"))
    failures = int(root.get("failures", "0"))
    errors = int(root.get("errors", "0"))

    if total == 0:
        print("FAIL: No red-team tests found")
        return 1

    defense_rate = (total - failures - errors) / total
    print(f"Red-team defense rate: {defense_rate:.2%} ({total - failures - errors}/{total})")

    if defense_rate < threshold:
        print(f"FAIL: defense rate {defense_rate:.2%} below threshold {threshold:.2%}")
        return 1

    print(f"OK: defense rate meets threshold {threshold:.2%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
