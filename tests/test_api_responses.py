"""Tests for response simulation API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicbc.core.store import (
    PersonaStore,
    QuestionnaireStore,
    ResponseStore,
    get_questionnaire_store,
    get_response_store,
    get_store,
)
from aicbc.main import app


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient with overridden dependencies."""
    test_persona_store = PersonaStore()
    test_questionnaire_store = QuestionnaireStore()
    test_response_store = ResponseStore()

    app.dependency_overrides[get_store] = lambda: test_persona_store
    app.dependency_overrides[get_questionnaire_store] = lambda: test_questionnaire_store
    app.dependency_overrides[get_response_store] = lambda: test_response_store

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def sample_study_and_questionnaire(client: TestClient) -> str:
    """Create a study and generate its questionnaire, return study_id."""
    from aicbc.questionnaire.models import (
        Attribute,
        AttributeLevel,
        AttributeType,
        DesignParameters,
    )

    study_id = "resp-test-study"

    # Use a small attribute set for fast D-optimal generation
    attrs = [
        Attribute(
            id="price",
            name="价格",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value=100, label="100"),
                AttributeLevel(value=200, label="200"),
            ],
        ),
        Attribute(
            id="brand",
            name="品牌",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="A", label="品牌A"),
                AttributeLevel(value="B", label="品牌B"),
            ],
        ),
    ]

    # Create study with small attribute set
    resp = client.post(
        "/api/v1/studies",
        json={
            "study_id": study_id,
            "product_category": "测试",
            "research_goal": "测试集成",
        },
    )
    assert resp.status_code == 201

    # Override the study with small attributes for fast generation
    store = app.dependency_overrides[get_questionnaire_store]()
    study = store.get_study(study_id)
    study.attributes = attrs
    study.design_parameters = DesignParameters(
        n_choice_sets=3, n_alternatives=2, seed=42
    )
    store.save_study(study)

    # Generate questionnaire
    resp = client.post(f"/api/v1/studies/{study_id}/generate", params={"seed": 42})
    assert resp.status_code == 201

    return study_id


@pytest.fixture
def sample_persona_in_store(client: TestClient) -> str:
    """Create and store a sample persona, return persona_id."""
    from tests.test_cbc_choice_simulator import _make_persona

    persona_id = "persona-resp-001"
    persona = _make_persona()
    persona.persona_id = persona_id

    # Get the store through the dependency override
    store = app.dependency_overrides[get_store]()
    store.save(persona)
    return persona_id


class TestSimulateResponses:
    """Tests for POST /studies/{id}/simulate-responses."""

    def test_simulate_single_persona(
        self,
        client: TestClient,
        sample_study_and_questionnaire: str,
        sample_persona_in_store: str,
    ) -> None:
        study_id = sample_study_and_questionnaire
        persona_id = sample_persona_in_store

        resp = client.post(
            f"/api/v1/studies/{study_id}/simulate-responses",
            json={
                "persona_ids": [persona_id],
                "deterministic": True,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["study_id"] == study_id
        assert data["simulated"] == 1
        assert data["failed"] == 0
        assert len(data["summaries"]) == 1
        assert data["summaries"][0]["persona_id"] == persona_id
        assert data["summaries"][0]["completion_status"] == "COMPLETED"

    def test_simulate_multiple_personas(
        self,
        client: TestClient,
        sample_study_and_questionnaire: str,
    ) -> None:
        study_id = sample_study_and_questionnaire

        # Create two personas
        from tests.test_cbc_choice_simulator import _make_persona

        store = app.dependency_overrides[get_store]()
        for i in range(2):
            persona = _make_persona(
                price_sensitivity="低敏感" if i == 0 else "高敏感",
                brand_loyalty="忠诚" if i == 0 else "尝试新品牌",
            )
            persona.persona_id = f"persona-multi-{i}"
            store.save(persona)

        resp = client.post(
            f"/api/v1/studies/{study_id}/simulate-responses",
            json={
                "persona_ids": ["persona-multi-0", "persona-multi-1"],
                "deterministic": False,
                "seed": 42,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["simulated"] == 2
        assert data["failed"] == 0

    def test_simulate_missing_persona(
        self,
        client: TestClient,
        sample_study_and_questionnaire: str,
    ) -> None:
        study_id = sample_study_and_questionnaire

        resp = client.post(
            f"/api/v1/studies/{study_id}/simulate-responses",
            json={
                "persona_ids": ["non-existent-persona"],
                "deterministic": True,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["simulated"] == 0
        assert data["failed"] == 1

    def test_simulate_no_questionnaire(
        self,
        client: TestClient,
        sample_persona_in_store: str,
    ) -> None:
        resp = client.post(
            "/api/v1/studies/nonexistent-study/simulate-responses",
            json={
                "persona_ids": [sample_persona_in_store],
                "deterministic": True,
            },
        )
        assert resp.status_code == 404


class TestListResponses:
    """Tests for GET /studies/{id}/responses."""

    def test_list_after_simulation(
        self,
        client: TestClient,
        sample_study_and_questionnaire: str,
        sample_persona_in_store: str,
    ) -> None:
        study_id = sample_study_and_questionnaire
        persona_id = sample_persona_in_store

        # Run simulation first
        client.post(
            f"/api/v1/studies/{study_id}/simulate-responses",
            json={"persona_ids": [persona_id], "deterministic": True},
        )

        resp = client.get(f"/api/v1/studies/{study_id}/responses")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["persona_id"] == persona_id
        assert data[0]["completion_status"] == "COMPLETED"

    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/v1/studies/no-responses/responses")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []


class TestExportDataset:
    """Tests for GET /studies/{id}/responses/export."""

    def test_export_after_simulation(
        self,
        client: TestClient,
        sample_study_and_questionnaire: str,
        sample_persona_in_store: str,
    ) -> None:
        study_id = sample_study_and_questionnaire
        persona_id = sample_persona_in_store

        # Run simulation
        client.post(
            f"/api/v1/studies/{study_id}/simulate-responses",
            json={"persona_ids": [persona_id], "deterministic": True},
        )

        resp = client.get(f"/api/v1/studies/{study_id}/responses/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["study_id"] == study_id
        assert data["n_respondents"] == 1
        assert data["n_total_records"] > 0
        assert len(data["choice_records"]) > 0

        # Verify structure of choice records
        record = data["choice_records"][0]
        assert "respondent_id" in record
        assert "choice_set_id" in record
        assert "alternatives" in record
        assert "none_chosen" in record

    def test_export_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/studies/no-data/responses/export")
        assert resp.status_code == 404
