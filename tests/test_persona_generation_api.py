"""Tests for async persona generation API."""

from __future__ import annotations

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import patch

from aicbc.main import app

client = TestClient(app)


@pytest.mark.integration
class TestAsyncPersonaGeneration:
    """Tests for async persona generation endpoints."""

    def test_generate_personas_async_returns_202(self):
        with patch("aicbc.api.routes.personas.run_persona_generation_task") as mock_task:
            mock_task.delay.return_value = None
            response = client.post("/api/v1/personas/generate-async", json={
                "study_id": "async-test",
                "count": 10,
            })
            assert response.status_code == status.HTTP_202_ACCEPTED
            data = response.json()
            assert data["status"] == "QUEUED"
            assert "job_id" in data
            mock_task.delay.assert_called_once()

    def test_get_persona_generation_status_404(self):
        response = client.get("/api/v1/personas/generation/nonexistent/status")
        assert response.status_code == status.HTTP_404_NOT_FOUND
