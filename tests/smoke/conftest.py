"""pytest options for smoke tests."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the deployed AI_CBC instance for smoke tests",
    )
