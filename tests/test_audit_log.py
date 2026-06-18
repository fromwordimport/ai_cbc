"""Tests for audit logging middleware and logger."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from fastapi import FastAPI
from starlette.testclient import TestClient

from aicbc.api.middleware.audit_log import AuditLogMiddleware
from aicbc.core.audit import AuditLogger, get_audit_logger, reset_audit_logger


@pytest.fixture(autouse=True)
def _reset_logger():
    reset_audit_logger()
    yield
    reset_audit_logger()


class TestAuditLogger:
    """AuditLogger unit tests."""

    def test_memory_fallback(self) -> None:
        """When MongoDB is unavailable, entries go to memory."""
        logger = AuditLogger()

        class FakeRequest:
            headers = {}
            client = None
            url = type("URL", (), {"path": "/api/v1/studies"})()

        # Run async log_event in sync test.
        import asyncio

        asyncio.run(
            logger.log_event(
                action="POST",
                resource="studies",
                resource_id="s1",
                result="success",
                request=FakeRequest(),  # type: ignore[arg-type]
                user_id="user-1",
            )
        )

        logs = logger.get_memory_logs()
        assert len(logs) == 1
        assert logs[0]["action"] == "POST"
        assert logs[0]["resource"] == "studies"
        assert logs[0]["resource_id"] == "s1"
        assert logs[0]["user_id"] == "user-1"


class TestAuditLogMiddleware:
    """Middleware integration tests."""

    @pytest.fixture
    def client(self) -> TestClient:
        app = FastAPI()

        @app.post("/api/v1/studies")
        def create_study():
            return {"id": "s1"}

        @app.delete("/api/v1/studies/{study_id}")
        def delete_study(study_id: str):
            return {"deleted": study_id}

        @app.get("/api/v1/studies")
        def list_studies():
            return {"items": []}

        app.add_middleware(AuditLogMiddleware)
        return TestClient(app)

    def test_post_request_is_audited(self, client: TestClient) -> None:
        response = client.post("/api/v1/studies", headers={"X-User-Id": "u1"})
        assert response.status_code == 200

        logs = get_audit_logger().get_memory_logs()
        assert len(logs) == 1
        assert logs[0]["action"] == "POST"
        assert logs[0]["resource"] == "studies"
        assert logs[0]["data"]["status_code"] == 200
        assert logs[0]["user_id"] == "u1"

    def test_delete_request_is_audited_with_resource_id(self, client: TestClient) -> None:
        response = client.delete("/api/v1/studies/s1")
        assert response.status_code == 200

        logs = get_audit_logger().get_memory_logs()
        delete_logs = [log for log in logs if log["action"] == "DELETE"]
        assert len(delete_logs) == 1
        assert delete_logs[0]["resource_id"] == "s1"

    def test_get_request_is_not_audited(self, client: TestClient) -> None:
        response = client.get("/api/v1/studies")
        assert response.status_code == 200

        logs = get_audit_logger().get_memory_logs()
        assert len(logs) == 0
