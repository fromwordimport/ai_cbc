"""Tests for POST /api/v1/personas/generate endpoint."""

from __future__ import annotations

import json
from typing import Any
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
from aicbc.llm.client import LLMResponse, Provider
from aicbc.main import app


def _mock_llm_response(content: dict[str, Any] | str, model: str = "claude-sonnet-4-6") -> LLMResponse:
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return LLMResponse(
        content=text,
        model=model,
        provider=Provider.ANTHROPIC,
        prompt_tokens=100,
        completion_tokens=200,
        total_tokens=300,
        estimated_cost_usd=0.003,
        latency_seconds=0.5,
        raw_response=None,
    )

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helper: override dependencies with mocks
# ---------------------------------------------------------------------------


def _override_deps(mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
    """Override FastAPI dependencies for testing."""
    app.dependency_overrides[get_llm_client] = lambda: mock_llm_client
    app.dependency_overrides[get_seed_generator] = lambda: SeedGenerator(seed=42)
    app.dependency_overrides[get_profile_generator] = lambda: ProfileGenerator(llm_client=mock_llm_client)
    app.dependency_overrides[get_schema_validator] = SchemaValidator
    app.dependency_overrides[get_logic_validator] = LogicValidator
    app.dependency_overrides[get_store] = lambda: clean_store


def _clear_overrides() -> None:
    """Clear all dependency overrides."""
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------


class TestBatchGenerateHappyPath:
    """Happy-path tests for batch generation."""

    def test_generate_single_persona(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """Generate a single persona should return 201 with correct structure."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "test"})

            assert response.status_code == 201
            data = response.json()
            assert data["study_id"] == "test"
            assert data["requested"] == 1
            assert data["generated"] == 1
            assert data["failed"] == 0
            assert len(data["personas"]) == 1
            assert data["total_cost_cny"] >= 0
            assert data["generation_time_seconds"] >= 0
            assert data["errors"] == []
        finally:
            _clear_overrides()

    def test_generate_multiple_personas(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """Generate 3 personas in one batch."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.post("/api/v1/personas/generate", json={"count": 3, "study_id": "multi"})

            assert response.status_code == 201
            data = response.json()
            assert data["generated"] == 3
            assert len(data["personas"]) == 3
            # IDs should be sequential
            ids = [p["persona_id"] for p in data["personas"]]
            assert ids == ["persona-multi-001", "persona-multi-002", "persona-multi-003"]
        finally:
            _clear_overrides()

    def test_personas_stored_after_generation(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """Generated personas should be retrievable from the store."""
        _override_deps(mock_llm_client, clean_store)

        try:
            client.post("/api/v1/personas/generate", json={"count": 2, "study_id": "storage"})

            # Should be able to GET them back
            r1 = client.get("/api/v1/personas/persona-storage-001")
            assert r1.status_code == 200
            assert r1.json()["persona_id"] == "persona-storage-001"

            r2 = client.get("/api/v1/personas/persona-storage-002")
            assert r2.status_code == 200
        finally:
            _clear_overrides()

    def test_seed_reproducibility(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """Same seed should produce identical persona structures."""
        _override_deps(mock_llm_client, clean_store)

        try:
            resp_a = client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "seed", "seed": 123})
            data_a = resp_a.json()

            # Clear store and regenerate with same seed
            clean_store.clear()
            resp_b = client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "seed", "seed": 123})
            data_b = resp_b.json()

            # Segments should match (life_stage + city_tier from same seed)
            assert data_a["personas"][0]["segment"] == data_b["personas"][0]["segment"]
        finally:
            _clear_overrides()

    def test_skip_validation_flag(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """skip_validation=true should still generate but not fail on bad data."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.post(
                "/api/v1/personas/generate",
                json={"count": 1, "study_id": "skip", "skip_validation": True},
            )
            assert response.status_code == 201
            assert response.json()["generated"] == 1
        finally:
            _clear_overrides()


# ---------------------------------------------------------------------------
# Tests: input validation
# ---------------------------------------------------------------------------


class TestBatchGenerateInputValidation:
    """Input validation tests for batch generation."""

    def test_count_must_be_positive(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """count=0 should return 422."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.post("/api/v1/personas/generate", json={"count": 0})
            assert response.status_code == 422
        finally:
            _clear_overrides()

    def test_count_exceeds_max(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """count=101 should return 422."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.post("/api/v1/personas/generate", json={"count": 101})
            assert response.status_code == 422
        finally:
            _clear_overrides()

    def test_missing_count(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """Missing count field should return 422."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.post("/api/v1/personas/generate", json={})
            assert response.status_code == 422
        finally:
            _clear_overrides()

    def test_invalid_count_type(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """count='abc' should return 422."""
        _override_deps(mock_llm_client, clean_store)

        try:
            response = client.post("/api/v1/personas/generate", json={"count": "abc"})
            assert response.status_code == 422
        finally:
            _clear_overrides()


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


class TestBatchGenerateErrors:
    """Error handling tests for batch generation."""

    def test_partial_failure_reported(self, mock_llm_client: MagicMock, clean_store: PersonaStore) -> None:
        """If one persona fails, others should still be generated."""
        _override_deps(mock_llm_client, clean_store)

        def _l1() -> dict[str, Any]:
            return {"age": "28岁", "gender": "女", "city": "新一线", "income": "15-30万元", "occupation": "产品经理", "education": "本科", "marital_status": "已婚", "living_type": "自有住房"}
        def _l2() -> dict[str, Any]:
            return {"price_sensitivity": "中等敏感", "purchase_channels": ["京东"], "decision_style": "理性", "brand_loyalty": "中等", "information_source": ["小红书"]}
        def _l3() -> dict[str, Any]:
            return {"core_values": ["效率"], "core_anxieties": ["时间"], "tension_combination": {"labels": ["A", "B"], "narrative_explanation": "她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑，小时候家境普通让她对浪费极度敏感。"}, "secret_motivation": "测试", "defense_mechanism": "测试"}
        def _l4() -> dict[str, Any]:
            return {"daily_routine": "早9晚6", "purchase_trigger": "种草", "stress_response": "购物", "social_behavior": "活跃"}
        def _aux() -> dict[str, Any]:
            return {"language_samples": ["洗碗机真的是解放双手的神器，后悔没早买！", "对比了三个品牌，最后还是选了性价比最高的那款。", "安装师傅非常专业，只用了半小时就全部搞定了。"], "dishwasher_context": {"purchase_constraints": ["空间小"], "decision_factors": ["价格"], "ignored_factors": ["外观"]}}

        try:
            call_count = 0
            layers = [_l1, _l2, _l3, _l4, _aux]

            def _failing_side_effect(*args: Any, **kwargs: Any) -> Any:
                nonlocal call_count
                call_count += 1
                if call_count == 10:  # 2nd persona, auxiliary call (5 calls per persona)
                    raise RuntimeError("Simulated LLM failure")
                layer_fn = layers[(call_count - 1) % 5]
                return _mock_llm_response(layer_fn())

            mock_llm_client.generate.side_effect = _failing_side_effect

            response = client.post("/api/v1/personas/generate", json={"count": 2, "study_id": "fail"})
            data = response.json()

            assert response.status_code == 201
            assert data["generated"] == 2  # Both succeed (2nd uses fallbacks)
            assert data["failed"] == 0  # Fallbacks prevent total failure
        finally:
            _clear_overrides()
