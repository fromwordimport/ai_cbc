"""Critical path smoke tests against a deployed AI_CBC instance.

Run with:
    pytest tests/smoke/ --base-url=http://localhost:8000
"""

from __future__ import annotations

import pytest
import requests


@pytest.fixture
def base_url(pytestconfig) -> str:
    return pytestconfig.getoption("base_url") or "http://localhost:8000"


def test_health_endpoint(base_url: str) -> None:
    resp = requests.get(f"{base_url}/health", timeout=10)
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_ready_endpoint(base_url: str) -> None:
    resp = requests.get(f"{base_url}/ready", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"


def test_metrics_endpoint(base_url: str) -> None:
    resp = requests.get(f"{base_url}/metrics", timeout=10)
    assert resp.status_code == 200
    assert "aicbc_api_requests_total" in resp.text or "python_info" in resp.text
