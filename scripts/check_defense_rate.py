#!/usr/bin/env python3
"""Parse pytest JUnit XML and fail if red-team defense rate is below threshold."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_THRESHOLD = 0.95
DEFAULT_XML_PATH = "test-results/redteam-fast.xml"


def _get_testsuite(root: ET.Element) -> ET.Element | None:
    """Return the relevant <testsuite> element from a JUnit XML root."""
    if root.tag == "testsuite":
        return root
    if root.tag == "testsuites":
        return root.find("testsuite")
    return None


def _int_attr(elem: ET.Element, name: str) -> int:
    """Return an integer attribute value, raising ValueError on bad data."""
    value = elem.get(name, "0")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name}={value!r}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse pytest JUnit XML and fail if red-team defense rate is below threshold."
    )
    parser.add_argument(
        "xml_path",
        nargs="?",
        default=DEFAULT_XML_PATH,
        help=f"Path to JUnit XML report (default: {DEFAULT_XML_PATH})",
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Defense rate threshold (default: {DEFAULT_THRESHOLD})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    xml_path = Path(args.xml_path)
    threshold = args.threshold
    if not (0.0 <= threshold <= 1.0):
        print(f"FAIL: Threshold must be between 0.0 and 1.0, got {threshold}")
        return 1

    if not xml_path.exists():
        print(f"FAIL: XML report not found: {xml_path}")
        return 1

    try:
        root = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    except ET.ParseError as exc:
        print(f"FAIL: Could not parse XML report: {exc}")
        return 1

    suite = _get_testsuite(root)
    if suite is None:
        print(f"FAIL: Expected root tag <testsuite> or <testsuites>, got <{root.tag}>")
        return 1

    try:
        total = _int_attr(suite, "tests")
        failures = _int_attr(suite, "failures")
        errors = _int_attr(suite, "errors")
        skipped = _int_attr(suite, "skipped")
    except ValueError as exc:
        print(f"FAIL: Invalid numeric attribute in XML report: {exc}")
        return 1

    effective_total = total - skipped
    if effective_total == 0:
        print("FAIL: No executed red-team tests found")
        return 1

    defense_rate = (effective_total - failures - errors) / effective_total
    print(
        f"Red-team defense rate: {defense_rate:.2%} "
        f"({effective_total - failures - errors}/{effective_total})"
    )

    if defense_rate < threshold:
        print(f"FAIL: defense rate {defense_rate:.2%} below threshold {threshold:.2%}")
        return 1

    print(f"OK: defense rate meets threshold {threshold:.2%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
