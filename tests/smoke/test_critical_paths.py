"""Critical path smoke tests against a deployed AI_CBC instance.

Run with:
    pytest tests/smoke/ --base-url=http://localhost:8000
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
import requests

if TYPE_CHECKING:
    from pytest import Config


def _get_with_retry(
    url: str,
    *,
    expected_status: int = 200,
    retries: int = 5,
    backoff: float = 2.0,
    timeout: int = 10,
) -> requests.Response:
    """GET *url* with retries to tolerate cold-start flakiness."""
    last_exc: Exception | None = None
    for _attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == expected_status:
                return resp
        except requests.RequestException as exc:
            last_exc = exc
        time.sleep(backoff)
    if last_exc is not None:
        raise AssertionError(
            f"Smoke test failed to connect to {url} — is the deployment reachable?"
        ) from last_exc
    raise AssertionError(
        f"Smoke test received unexpected status from {url} after {retries} retries"
    )


@pytest.fixture
def base_url(pytestconfig: Config) -> str:
    return pytestconfig.getoption("base_url")


def test_health_endpoint(base_url: str) -> None:
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
    except requests.RequestException as exc:
        raise AssertionError(
            f"Smoke test failed to connect to {base_url}/health — is the deployment reachable?"
        ) from exc
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_ready_endpoint(base_url: str) -> None:
    resp = _get_with_retry(f"{base_url}/ready", retries=5, backoff=2.0, timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"


def test_metrics_endpoint(base_url: str) -> None:
    try:
        resp = requests.get(f"{base_url}/metrics", timeout=10)
    except requests.RequestException as exc:
        raise AssertionError(
            f"Smoke test failed to connect to {base_url}/metrics — is the deployment reachable?"
        ) from exc
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("text/plain")
    assert "aicbc_api_requests_total" in resp.text or "python_info" in resp.text
