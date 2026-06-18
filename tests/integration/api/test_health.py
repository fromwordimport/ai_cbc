"""Health check endpoint tests."""

import pytest

pytestmark = pytest.mark.integration

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aicbc.main import app
from aicbc.monitoring.health import _check_mongodb, _check_redis

client = TestClient(app)


def test_health_check() -> None:
    """Test basic health check."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data


def test_readiness_check() -> None:
    """Test readiness check with dependency verification."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ("ready", "degraded", "not_ready")
    assert "checks" in data
    assert "timestamp" in data

    # Verify all expected dependencies are checked
    checks = data["checks"]
    assert "mongodb" in checks
    assert "redis" in checks
    assert "llm_api" in checks

    # Each check should have required fields
    for check in checks.values():
        assert "name" in check
        assert "status" in check
        assert "latency_ms" in check
        assert check["status"] in ("ok", "degraded", "fail")


def test_metrics_endpoint() -> None:
    """Test Prometheus metrics endpoint."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    # Should contain at least some AI_CBC metrics
    content = response.text
    assert "aicbc_" in content or "python_" in content or "process_" in content


@pytest.mark.asyncio
async def test_check_mongodb_pings():
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})

    with patch("aicbc.main._mongo_client", mock_client):
        result = await _check_mongodb()

    assert result.status == "ok"
    mock_client.admin.command.assert_awaited_once_with("ping")


@pytest.mark.asyncio
async def test_check_mongodb_fail():
    with patch("aicbc.main._mongo_client", None):
        result = await _check_mongodb()

    assert result.status == "fail"


@pytest.mark.asyncio
async def test_check_redis_pings():
    mock_redis = MagicMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    with (
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch("aicbc.config.settings.get_settings") as mock_settings,
    ):
        mock_settings.return_value.database.redis_url = "redis://localhost:6379/0"
        result = await _check_redis()

    assert result.status == "ok"
    mock_redis.ping.assert_awaited_once()
    mock_redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_redis_fail():
    mock_redis = MagicMock()
    mock_redis.ping = AsyncMock(side_effect=ConnectionError("Redis is down"))
    mock_redis.aclose = AsyncMock()

    with (
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch("aicbc.config.settings.get_settings") as mock_settings,
    ):
        mock_settings.return_value.database.redis_url = "redis://localhost:6379/0"
        result = await _check_redis()

    assert result.status == "fail"
    mock_redis.ping.assert_awaited_once()
    mock_redis.aclose.assert_awaited_once()
