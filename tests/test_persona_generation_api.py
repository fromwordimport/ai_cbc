"""Tests for async persona generation API."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from aicbc.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestAsyncPersonaGeneration:
    """Tests for async persona generation endpoints."""

    async def test_generate_personas_async_returns_202(self, client: AsyncClient):
        with patch(
            "aicbc.core.models.db_documents.PersonaGenerationJobDocument.__init__",
            return_value=None,
        ), patch(
            "aicbc.core.models.db_documents.PersonaGenerationJobDocument.insert",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_insert, patch(
            "aicbc.api.routes.personas.run_persona_generation_task.delay"
        ) as mock_delay:
            response = await client.post("/api/v1/personas/generate-async", json={
                "study_id": "async-test",
                "count": 10,
            })

            assert response.status_code == status.HTTP_202_ACCEPTED
            data = response.json()
            assert data["status"] == "QUEUED"
            assert "job_id" in data
            job_id = data["job_id"]
            assert re.match(r"^pg-async-test-[0-9a-f]{8}$", job_id)
            mock_insert.assert_called_once()
            mock_delay.assert_called_once()

    async def test_get_persona_generation_status_404(self, client: AsyncClient):
        with patch(
            "aicbc.core.models.db_documents.PersonaGenerationJobDocument.find_one",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await client.get("/api/v1/personas/generation/nonexistent/status")
            assert response.status_code == status.HTTP_404_NOT_FOUND
