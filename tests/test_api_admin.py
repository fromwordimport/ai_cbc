"""Tests for admin endpoints (settings, cost-status, audit-logs)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicbc.config.settings import get_settings
from aicbc.core.audit import reset_audit_logger
from aicbc.core.security.encryption import is_encrypted
from aicbc.core.store import get_questionnaire_store
from aicbc.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_stores():
    """Clear stores and audit logs before and after each test."""
    store = get_questionnaire_store()
    store.clear()
    reset_audit_logger()
    yield
    store.clear()
    reset_audit_logger()


class TestAdminSettings:
    """Tests for /api/v1/admin/settings."""

    def test_get_admin_settings(self) -> None:
        response = client.get("/api/v1/admin/settings")
        assert response.status_code == 200
        data = response.json()
        assert "environment" in data
        assert "llm" in data
        assert "providers" in data
        assert "cost_fuse" in data
        # API keys must not be exposed.
        for cfg in data["providers"].values():
            assert "api_key" not in cfg
            assert isinstance(cfg["api_key_set"], bool)

    def test_put_admin_settings_allowed(self) -> None:
        response = client.put(
            "/api/v1/admin/settings",
            json={"temperature": 0.5, "max_tokens": 2048},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "temperature" in data["applied"]

    def test_put_admin_settings_updates_provider_and_encrypts_key(self) -> None:
        response = client.put(
            "/api/v1/admin/settings",
            json={
                "llm_provider": "deepseek",
                "llm_model": "deepseek-chat",
                "providers": {
                    "deepseek": {
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "sk-deepseek-test",
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["applied"]["llm_provider"] == "deepseek"
        assert data["applied"]["providers.deepseek"]["api_key"] == "***"

        settings = get_settings()
        assert settings.llm.provider == "deepseek"
        assert settings.llm.model == "deepseek-chat"
        assert settings.deepseek.enabled is True
        assert settings.deepseek.base_url == "https://api.deepseek.com/v1"
        assert settings.deepseek.api_key
        assert is_encrypted(settings.deepseek.api_key)

    def test_put_admin_settings_rejects_unknown(self) -> None:
        response = client.put(
            "/api/v1/admin/settings",
            json={"unknown_field": "value"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        assert "unknown_field" in data["rejected"]


class TestCostStatus:
    """Tests for /cost-status."""

    def test_get_cost_status(self) -> None:
        response = client.get("/cost-status")
        assert response.status_code == 200
        data = response.json()
        assert "fuse_status" in data


class TestAuditLogs:
    """Tests for /api/v1/admin/audit-logs."""

    def test_audit_logs_require_admin(self) -> None:
        response = client.get(
            "/api/v1/admin/audit-logs",
            headers={"X-User-Role": "viewer"},
        )
        assert response.status_code == 403

    def test_audit_logs_empty(self) -> None:
        response = client.get("/api/v1/admin/audit-logs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["entries"] == []

    def test_audit_logs_after_mutation(self) -> None:
        # Generate an audited write event.
        response = client.post(
            "/api/v1/studies",
            json={
                "study_id": "admin-audit-001",
                "product_category": "洗碗机",
                "research_goal": "审计日志测试",
            },
        )
        assert response.status_code == 201

        response = client.get("/api/v1/admin/audit-logs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        entry = data["entries"][0]
        assert "timestamp" in entry
        assert "action" in entry
        assert "resource" in entry

    def test_audit_logs_filter_by_action(self) -> None:
        client.post(
            "/api/v1/studies",
            json={
                "study_id": "admin-audit-002",
                "product_category": "洗碗机",
                "research_goal": "过滤测试",
            },
        )

        response = client.get("/api/v1/admin/audit-logs?action=POST")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for entry in data["entries"]:
            assert entry["action"] == "POST"

    def test_audit_logs_pagination(self) -> None:
        response = client.get("/api/v1/admin/audit-logs?page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["entries"]) <= 5


class TestDashboardSummary:
    """Tests for the migrated /dashboard/summary endpoint."""

    def test_dashboard_summary(self) -> None:
        response = client.get("/dashboard/summary")
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "recent_studies" in data
        assert "total_studies" in data["summary"]
        assert "total_personas" in data["summary"]
