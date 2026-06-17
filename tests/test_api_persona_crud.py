"""Tests for GET /personas, GET /personas/{id}, POST /validate, DELETE endpoints."""

from __future__ import annotations

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
# GET /personas/{persona_id}
# ---------------------------------------------------------------------------


class TestGetPersona:
    """Tests for retrieving a single persona."""

    def test_get_existing_persona(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """GET an existing persona should return 200 with full details."""
        _override_deps(mock_llm_client, clean_store)

        try:
            # Generate first
            client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "get"})

            # Then retrieve
            response = client.get("/api/v1/personas/persona-get-001")
            assert response.status_code == 200

            data = response.json()
            assert data["persona_id"] == "persona-get-001"
            assert "layer1_demographics" in data
            assert "layer2_behavior" in data
            assert "layer3_psychology" in data
            assert "layer4_scenarios" in data
            assert "language_samples" in data
            assert "dishwasher_context" in data
            assert "generation_metadata" in data
        finally:
            _clear_overrides()

    def test_get_nonexistent_persona(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """GET a non-existent persona should return 404."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.get("/api/v1/personas/persona-does-not-exist")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
        finally:
            _clear_overrides()


# ---------------------------------------------------------------------------
# GET /personas (list)
# ---------------------------------------------------------------------------


class TestListPersonas:
    """Tests for persona list endpoint."""

    def test_list_empty_store(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """List on empty store should return 0 total."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.get("/api/v1/personas")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert data["personas"] == []
            assert data["page"] == 1
        finally:
            _clear_overrides()

    def test_list_with_data(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """List should return generated personas."""
        _override_deps(mock_llm_client, clean_store)

        try:
            client.post("/api/v1/personas/generate", json={"count": 5, "study_id": "list"})

            response = client.get("/api/v1/personas")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 5
            assert len(data["personas"]) == 5
        finally:
            _clear_overrides()

    def test_list_pagination(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """Pagination should return correct slices."""
        _override_deps(mock_llm_client, clean_store)

        try:
            client.post("/api/v1/personas/generate", json={"count": 5, "study_id": "page"})

            # Page 1, size 2
            r1 = client.get("/api/v1/personas?page=1&page_size=2")
            assert r1.json()["total"] == 5
            assert len(r1.json()["personas"]) == 2

            # Page 2, size 2
            r2 = client.get("/api/v1/personas?page=2&page_size=2")
            assert len(r2.json()["personas"]) == 2

            # Page 3, size 2 (only 1 left)
            r3 = client.get("/api/v1/personas?page=3&page_size=2")
            assert len(r3.json()["personas"]) == 1
        finally:
            _clear_overrides()

    def test_list_filter_by_study_id(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """Filter by study_id should narrow results."""
        _override_deps(mock_llm_client, clean_store)

        try:
            client.post("/api/v1/personas/generate", json={"count": 3, "study_id": "studya"})
            client.post("/api/v1/personas/generate", json={"count": 2, "study_id": "studyb"})

            response = client.get("/api/v1/personas?study_id=studya")
            assert response.json()["total"] == 3

            response = client.get("/api/v1/personas?study_id=studyb")
            assert response.json()["total"] == 2
        finally:
            _clear_overrides()


# ---------------------------------------------------------------------------
# POST /personas/{persona_id}/validate
# ---------------------------------------------------------------------------


class TestValidatePersona:
    """Tests for persona validation endpoint."""

    def test_validate_existing_persona(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """Validate a valid persona should return all-pass."""
        _override_deps(mock_llm_client, clean_store)

        try:
            client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "val"})

            response = client.post("/api/v1/personas/persona-val-001/validate")
            assert response.status_code == 200

            data = response.json()
            assert data["persona_id"] == "persona-val-001"
            assert data["schema_passed"] is True
            assert data["logic_passed"] is True
            assert data["overall_passed"] is True
            assert data["logic_score"] == 7.0
            assert data["logic_max_score"] == 7.0
        finally:
            _clear_overrides()

    def test_validate_nonexistent_persona(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """Validate a non-existent persona should return 404."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.post("/api/v1/personas/persona-missing-001/validate")
            assert response.status_code == 404
        finally:
            _clear_overrides()


# ---------------------------------------------------------------------------
# GET /personas/{persona_id}/layers/{layer_number}
# ---------------------------------------------------------------------------


class TestGetLayer:
    """Tests for layer retrieval endpoint."""

    def test_get_layer_1(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """GET layer 1 should return demographics."""
        _override_deps(mock_llm_client, clean_store)

        try:
            client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "layer"})

            response = client.get("/api/v1/personas/persona-layer-001/layers/1")
            assert response.status_code == 200

            data = response.json()
            assert data["layer_number"] == 1
            assert data["layer_name"] == "demographics"
            assert "age" in data["data"]
            assert "gender" in data["data"]
        finally:
            _clear_overrides()

    def test_get_layer_3(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """GET layer 3 should return psychology with tension."""
        _override_deps(mock_llm_client, clean_store)

        try:
            client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "layer3"})

            response = client.get("/api/v1/personas/persona-layer3-001/layers/3")
            assert response.status_code == 200

            data = response.json()
            assert data["layer_number"] == 3
            assert data["layer_name"] == "psychology"
            assert "tension_combination" in data["data"]
        finally:
            _clear_overrides()

    def test_get_invalid_layer_number(
        self, mock_llm_client: MagicMock, clean_store: PersonaStore
    ) -> None:
        """GET layer 5 should return 422."""
        _override_deps(mock_llm_client, clean_store)

        try:
            client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "layerr"})

            response = client.get("/api/v1/personas/persona-layerr-001/layers/5")
            assert response.status_code == 422
        finally:
            _clear_overrides()


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
            client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "del"})

            response = client.delete("/api/v1/personas/persona-del-001")
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
            response = client.delete("/api/v1/personas/persona-none-001")
            assert response.status_code == 404
        finally:
            _clear_overrides()
