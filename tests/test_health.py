"""Health check endpoint tests."""

from fastapi.testclient import TestClient

from aicbc.main import app

client = TestClient(app)


def test_health_check() -> None:
    """Test basic health check."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_readiness_check() -> None:
    """Test readiness check."""
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
