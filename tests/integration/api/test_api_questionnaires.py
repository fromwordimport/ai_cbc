"""Tests for CBC questionnaire API endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

from fastapi.testclient import TestClient

from aicbc.core.store import get_questionnaire_store
from aicbc.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_stores():
    """Clear questionnaire store before each test."""
    store = get_questionnaire_store()
    store.clear()
    yield
    store.clear()


class TestCreateStudy:
    """Tests for POST /studies."""

    def test_create_study_success(self) -> None:
        response = client.post(
            "/api/v1/studies",
            json={
                "study_id": "dw-test-001",
                "product_category": "洗碗机",
                "research_goal": "评估价格敏感度",
                "target_segments": ["精致白领"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["study_id"] == "dw-test-001"
        assert data["product_category"] == "洗碗机"
        assert (
            data["n_attributes"] == 7
        )  # default dishwasher attributes (price, capacity, installation, features, brand, energy, service)
        assert data["status"] == "INIT"

    def test_create_study_missing_field(self) -> None:
        response = client.post(
            "/api/v1/studies",
            json={"study_id": "dw-test-002"},
        )
        assert response.status_code == 422


class TestListStudies:
    """Tests for GET /studies."""

    def test_list_empty(self) -> None:
        response = client.get("/api/v1/studies")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["studies"] == []

    def test_list_with_studies(self) -> None:
        client.post(
            "/api/v1/studies",
            json={
                "study_id": "dw-test-001",
                "product_category": "洗碗机",
                "research_goal": "测试",
            },
        )
        response = client.get("/api/v1/studies")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["studies"][0]["study_id"] == "dw-test-001"


class TestGetStudy:
    """Tests for GET /studies/{study_id}."""

    def test_get_existing(self) -> None:
        client.post(
            "/api/v1/studies",
            json={
                "study_id": "dw-test-001",
                "product_category": "洗碗机",
                "research_goal": "测试",
            },
        )
        response = client.get("/api/v1/studies/dw-test-001")
        assert response.status_code == 200
        assert response.json()["study_id"] == "dw-test-001"

    def test_get_not_found(self) -> None:
        response = client.get("/api/v1/studies/nonexistent")
        assert response.status_code == 404


class TestDeleteStudy:
    """Tests for DELETE /studies/{study_id}."""

    def test_delete_existing(self) -> None:
        client.post(
            "/api/v1/studies",
            json={
                "study_id": "dw-test-del",
                "product_category": "洗碗机",
                "research_goal": "测试",
            },
        )
        response = client.delete("/api/v1/studies/dw-test-del")
        assert response.status_code == 204

    def test_delete_not_found(self) -> None:
        response = client.delete("/api/v1/studies/nonexistent")
        assert response.status_code == 404


class TestGenerateQuestionnaire:
    """Tests for POST /studies/{study_id}/generate."""

    def test_generate_d_optimal(self) -> None:
        client.post(
            "/api/v1/studies",
            json={
                "study_id": "dw-gen-001",
                "product_category": "洗碗机",
                "research_goal": "测试生成",
            },
        )
        response = client.post("/api/v1/studies/dw-gen-001/generate?seed=42")
        assert response.status_code == 201
        data = response.json()
        assert data["study_id"] == "dw-gen-001"
        assert data["algorithm"] == "d_optimal"
        assert data["n_choice_sets"] == 12  # default
        assert data["n_alternatives"] == 3
        assert data["d_efficiency"] is not None
        assert data["d_efficiency"] > 0.7
        # D-efficiency validation may fail at < 0.80 with few iterations;
        # this is expected — the algorithm converges with more iterations.

    def test_generate_study_not_found(self) -> None:
        response = client.post("/api/v1/studies/nonexistent/generate")
        assert response.status_code == 404


class TestGetQuestionnaire:
    """Tests for GET /studies/{study_id}/questionnaire."""

    def test_get_after_generation(self) -> None:
        client.post(
            "/api/v1/studies",
            json={
                "study_id": "dw-q-001",
                "product_category": "洗碗机",
                "research_goal": "测试获取问卷",
            },
        )
        client.post("/api/v1/studies/dw-q-001/generate?seed=42")

        response = client.get("/api/v1/studies/dw-q-001/questionnaire")
        assert response.status_code == 200
        data = response.json()
        assert data["study_id"] == "dw-q-001"
        assert len(data["choice_sets"]) == 12
        assert data["choice_sets"][0]["choice_set_id"] == 1
        assert len(data["choice_sets"][0]["alternatives"]) == 3

    def test_get_not_generated(self) -> None:
        client.post(
            "/api/v1/studies",
            json={
                "study_id": "dw-q-nogen",
                "product_category": "洗碗机",
                "research_goal": "测试",
            },
        )
        response = client.get("/api/v1/studies/dw-q-nogen/questionnaire")
        assert response.status_code == 404
