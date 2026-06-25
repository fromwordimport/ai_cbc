"""Tests for graceful shutdown behavior."""

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from aicbc.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def shutting_down():
    """Enable shutdown state for the duration of a test."""
    app.state.shutting_down = True
    yield
    app.state.shutting_down = False


@pytest.mark.asyncio
async def test_shutdown_returns_503(client: AsyncClient, shutting_down):
    response = await client.get("/api/v1/personas")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_health_still_available_during_shutdown(client: AsyncClient, shutting_down):
    response = await client.get("/health")
    assert response.status_code == status.HTTP_200_OK
