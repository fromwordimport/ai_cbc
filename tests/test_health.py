"""Health check endpoint tests."""

from fastapi.testclient import TestClient

from aicbc.main import app

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
