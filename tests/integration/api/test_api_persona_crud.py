"""Tests for GET /personas, GET /personas/{id}, POST /validate, DELETE endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from aicbc.api.dependencies import (
    get_llm_client,
    get_logic_validator,
    get_profile_generator,
    get_schema_validator,
    get_seed_generator,
)
from aicbc.core.store import PersonaStore, get_store
from aicbc.core.validators import LogicValidator, SchemaValidator
from aicbc.generators.profile_generator import ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator
from aicbc.main import app

client = TestClient(app)


def _override_deps(mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
    """Override FastAPI dependencies for testing."""
    app.dependency_overrides[get_llm_client] = lambda: mock_llm_client
    app.dependency_overrides[get_seed_generator] = lambda: SeedGenerator(seed=42)
    app.dependency_overrides[get_profile_generator] = lambda: ProfileGenerator(
        llm_client=mock_llm_client
    )
    app.dependency_overrides[get_schema_validator] = SchemaValidator
    app.dependency_overrides[get_logic_validator] = LogicValidator
    app.dependency_overrides[get_store] = lambda: clean_store


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# DELETE /personas/{persona_id}
# ---------------------------------------------------------------------------


class TestDeletePersona:
    """Tests for persona deletion endpoint."""

    def test_delete_existing_persona(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """DELETE an existing persona should return 204."""
        _override_deps(mock_llm_client, clean_store)

        try:
            client.post(
                "/api/v1/personas/generate",
                json={"count": 1, "study_id": "del"},
                headers={"X-User-Role": "admin"},
            )

            response = client.delete(
                "/api/v1/personas/persona-del-001",
                headers={"X-User-Role": "admin"},
            )
            assert response.status_code == 204

            # Should be gone
            get_resp = client.get("/api/v1/personas/persona-del-001")
            assert get_resp.status_code == 404
        finally:
            _clear_overrides()

    def test_delete_nonexistent_persona(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """DELETE a non-existent persona should return 404."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.delete(
                "/api/v1/personas/persona-none-001",
                headers={"X-User-Role": "admin"},
            )
            assert response.status_code == 404
        finally:
            _clear_overrides()

    def test_delete_persona_returns_204(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """DELETE /api/v1/personas/{id} returns 204 for existing persona."""
        _override_deps(mock_llm_client, clean_store)
        try:
            client.post(
                "/api/v1/personas/generate",
                json={"count": 1, "study_id": "del-204"},
                headers={"X-API-Key": "dev-key-change-in-prod", "X-User-Role": "admin"},
            )
            response = client.delete(
                "/api/v1/personas/persona-del-204-001",
                headers={"X-API-Key": "dev-key-change-in-prod", "X-User-Role": "admin"},
            )
            assert response.status_code == 204
        finally:
            _clear_overrides()

    def test_delete_nonexistent_persona_returns_404(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """DELETE unknown id returns 404."""
        _override_deps(mock_llm_client, clean_store)
        try:
            response = client.delete(
                "/api/v1/personas/persona-unknown-001",
                headers={"X-API-Key": "dev-key-change-in-prod", "X-User-Role": "admin"},
            )
            assert response.status_code == 404
        finally:
            _clear_overrides()

    @pytest.mark.xfail(reason="bulk-delete endpoint not yet implemented")
    def test_bulk_delete_personas_returns_204(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """POST /api/v1/personas/bulk-delete with ids list returns 204."""
        _override_deps(mock_llm_client, clean_store)
        try:
            client.post(
                "/api/v1/personas/generate",
                json={"count": 3, "study_id": "bulkdel"},
                headers={"X-API-Key": "dev-key-change-in-prod", "X-User-Role": "admin"},
            )
            response = client.post(
                "/api/v1/personas/bulk-delete",
                json={"ids": ["persona-bulkdel-001", "persona-bulkdel-002"]},
                headers={"X-API-Key": "dev-key-change-in-prod", "X-User-Role": "admin"},
            )
            assert response.status_code == 204
            assert clean_store.get("persona-bulkdel-001") is None
            assert clean_store.get("persona-bulkdel-002") is None
            assert clean_store.get("persona-bulkdel-003") is not None
        finally:
            _clear_overrides()
