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


@pytest.mark.asyncio
async def test_shutdown_returns_503(client: AsyncClient):
    app.state.shutting_down = True
    try:
        response = await client.get("/api/v1/personas")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    finally:
        app.state.shutting_down = False


@pytest.mark.asyncio
async def test_health_still_available_during_shutdown(client: AsyncClient):
    app.state.shutting_down = True
    try:
        response = await client.get("/health")
        assert response.status_code == status.HTTP_200_OK
    finally:
        app.state.shutting_down = False
