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


class _MockPersonaGenerationJobDocument:
    """Stand-in for PersonaGenerationJobDocument in tests.

    Avoids Beanie initialization requirements while supporting the expression
    style used in production queries (``Document.field == value``).
    """

    class _MockField:
        def __init__(self, name: str) -> None:
            self._name = name

        def __eq__(self, other: object) -> dict[str, object]:
            return {self._name: other}

    job_id = _MockField("job_id")
    study_id = _MockField("study_id")
    status = _MockField("status")
    requested = _MockField("requested")
    generated = _MockField("generated")
    failed = _MockField("failed")
    total_cost_cny = _MockField("total_cost_cny")
    progress = _MockField("progress")
    bias_failed_count = _MockField("bias_failed_count")
    bias_warning = _MockField("bias_warning")
    created_at = _MockField("created_at")
    updated_at = _MockField("updated_at")

    @classmethod
    async def find_one(cls, query: dict[str, object] | None = None) -> object | None:
        """Return whatever the test patches in."""
        # Tests patch this method directly on the class in the route module.
        return None

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    async def insert(self) -> None:
        pass


@pytest.mark.asyncio
class TestAsyncPersonaGeneration:
    """Tests for async persona generation endpoints."""

    async def test_generate_personas_async_returns_202(self, client: AsyncClient):
        with patch(
            "aicbc.api.routes.personas.PersonaGenerationJobDocument",
            _MockPersonaGenerationJobDocument,
        ), patch(
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
            mock_delay.assert_called_once()

    async def test_get_persona_generation_status_200(self, client: AsyncClient):
        expected_job_id = "pg-test-123abc"
        expected_study_id = "test-study"
        expected_status = "RUNNING"
        expected_requested = 10

        mock_doc = type(
            "MockDoc",
            (),
            {
                "job_id": expected_job_id,
                "study_id": expected_study_id,
                "status": expected_status,
                "requested": expected_requested,
                "generated": 5,
                "failed": 0,
                "total_cost_cny": 1.23,
                "progress": 0.5,
                "bias_failed_count": 1,
                "bias_warning": None,
                "created_at": "2026-06-25T00:00:00Z",
                "updated_at": "2026-06-25T01:00:00Z",
            },
        )()

        with patch(
            "aicbc.api.routes.personas.PersonaGenerationJobDocument",
            _MockPersonaGenerationJobDocument,
        ):
            _MockPersonaGenerationJobDocument.find_one = AsyncMock(return_value=mock_doc)
            response = await client.get(
                f"/api/v1/personas/generation/{expected_job_id}/status"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["job_id"] == expected_job_id
            assert data["study_id"] == expected_study_id
            assert data["status"] == expected_status

    async def test_get_persona_generation_status_404(self, client: AsyncClient):
        with patch(
            "aicbc.api.routes.personas.PersonaGenerationJobDocument",
            _MockPersonaGenerationJobDocument,
        ):
            _MockPersonaGenerationJobDocument.find_one = AsyncMock(return_value=None)
            response = await client.get("/api/v1/personas/generation/nonexistent/status")
            assert response.status_code == status.HTTP_404_NOT_FOUND
