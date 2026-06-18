"""Tests for privacy compliance and data-subject rights endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from aicbc.analysis.models import AnalysisJobStatus
from aicbc.analysis.store import MemoryAnalysisStore, get_analysis_store
from aicbc.api.dependencies import (
    get_llm_client,
    get_logic_validator,
    get_profile_generator,
    get_schema_validator,
    get_seed_generator,
)
from aicbc.core.audit import get_audit_logger
from aicbc.core.store import (
    MemoryPersonaStore,
    MemoryQuestionnaireStore,
    MemoryResponseStore,
    get_questionnaire_store,
    get_response_store,
    get_store,
)
from aicbc.core.validators import LogicValidator, SchemaValidator
from aicbc.generators.profile_generator import ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator
from aicbc.main import app

client = TestClient(app)


def _override_deps(
    mock_llm_client: MagicMock,
    persona_store: MemoryPersonaStore,
    questionnaire_store: MemoryQuestionnaireStore,
    response_store: MemoryResponseStore,
    analysis_store: MemoryAnalysisStore,
) -> None:
    """Override FastAPI dependencies for testing."""
    app.dependency_overrides[get_llm_client] = lambda: mock_llm_client
    app.dependency_overrides[get_seed_generator] = lambda: SeedGenerator(seed=42)
    app.dependency_overrides[get_profile_generator] = lambda: ProfileGenerator(
        llm_client=mock_llm_client
    )
    app.dependency_overrides[get_schema_validator] = SchemaValidator
    app.dependency_overrides[get_logic_validator] = LogicValidator
    app.dependency_overrides[get_store] = lambda: persona_store
    app.dependency_overrides[get_questionnaire_store] = lambda: questionnaire_store
    app.dependency_overrides[get_response_store] = lambda: response_store
    app.dependency_overrides[get_analysis_store] = lambda: analysis_store


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


class TestPersonaExport:
    """Tests for GET /personas/{persona_id}/export."""

    def test_export_existing_persona(
        self,
        mock_llm_client: MagicMock,
        clean_store: MemoryPersonaStore,
    ) -> None:
        _override_deps(
            mock_llm_client,
            clean_store,
            MemoryQuestionnaireStore(),
            MemoryResponseStore(),
            MemoryAnalysisStore(),
        )
        try:
            client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "pexport"})

            response = client.get("/api/v1/personas/persona-pexport-001/export")
            assert response.status_code == 200

            data = response.json()
            assert data["persona_id"] == "persona-pexport-001"
            assert data["export_schema_version"] == "1.0"
            assert "exported_at" in data
            assert data["data_controller"] == "AI_CBC Platform"
            assert "profile" in data
            assert data["profile"]["persona_id"] == "persona-pexport-001"
            assert "generation_metadata" in data
            assert "audit_trail" in data
        finally:
            _clear_overrides()

    def test_export_nonexistent_persona(
        self,
        mock_llm_client: MagicMock,
        clean_store: MemoryPersonaStore,
    ) -> None:
        _override_deps(
            mock_llm_client,
            clean_store,
            MemoryQuestionnaireStore(),
            MemoryResponseStore(),
            MemoryAnalysisStore(),
        )
        try:
            response = client.get("/api/v1/personas/persona-missing-001/export")
            assert response.status_code == 404
        finally:
            _clear_overrides()


class TestPersonaDeleteCascade:
    """Tests that persona deletion removes associated responses."""

    def test_delete_persona_cascades_responses(
        self,
        mock_llm_client: MagicMock,
        clean_store: MemoryPersonaStore,
    ) -> None:
        q_store = MemoryQuestionnaireStore()
        r_store = MemoryResponseStore()
        a_store = MemoryAnalysisStore()
        _override_deps(mock_llm_client, clean_store, q_store, r_store, a_store)

        try:
            # Create study and questionnaire.
            client.post(
                "/api/v1/studies",
                json={
                    "study_id": "pcascade",
                    "product_category": "洗碗机",
                    "research_goal": "test",
                },
            )
            client.post("/api/v1/studies/pcascade/generate")

            # Generate persona and simulate response.
            client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "pcascade"})
            client.post(
                "/api/v1/studies/pcascade/simulate-responses",
                json={"persona_ids": ["persona-pcascade-001"], "mode": "rule"},
            )

            assert r_store.list_responses_by_study("pcascade")[1] == 1

            response = client.delete("/api/v1/personas/persona-pcascade-001")
            assert response.status_code == 204

            assert r_store.list_responses_by_study("pcascade")[1] == 0
            assert clean_store.get("persona-pcascade-001") is None
        finally:
            _clear_overrides()


class TestStudyExport:
    """Tests for GET /studies/{study_id}/export."""

    def test_export_study_with_all_artefacts(
        self,
        mock_llm_client: MagicMock,
        clean_store: MemoryPersonaStore,
    ) -> None:
        q_store = MemoryQuestionnaireStore()
        r_store = MemoryResponseStore()
        a_store = MemoryAnalysisStore()
        _override_deps(mock_llm_client, clean_store, q_store, r_store, a_store)

        try:
            client.post(
                "/api/v1/studies",
                json={
                    "study_id": "sexport",
                    "product_category": "洗碗机",
                    "research_goal": "test",
                },
            )
            client.post("/api/v1/studies/sexport/generate")
            client.post("/api/v1/personas/generate", json={"count": 2, "study_id": "sexport"})
            client.post(
                "/api/v1/studies/sexport/simulate-responses",
                json={
                    "persona_ids": ["persona-sexport-001", "persona-sexport-002"],
                    "mode": "rule",
                },
            )

            # Seed an analysis job for export coverage.
            job = AnalysisJobStatus(
                analysis_id="analysis-sexport-001",
                study_id="sexport",
                status="COMPLETED",
                model_type="hb",
                queued_at=datetime.now(UTC),
                estimated_duration_seconds=60,
            )
            a_store.save_job(job)

            response = client.get("/api/v1/studies/sexport/export")
            assert response.status_code == 200

            data = response.json()
            assert data["study_id"] == "sexport"
            assert data["export_schema_version"] == "1.0"
            assert "exported_at" in data
            assert data["study"]["study_id"] == "sexport"
            assert data["questionnaire"] is not None
            assert len(data["personas"]) == 2
            assert len(data["responses"]) == 2
            assert data["dataset"] is not None
            assert len(data["analyses"]) == 1
        finally:
            _clear_overrides()

    def test_export_nonexistent_study(
        self,
        mock_llm_client: MagicMock,
        clean_store: MemoryPersonaStore,
    ) -> None:
        _override_deps(
            mock_llm_client,
            clean_store,
            MemoryQuestionnaireStore(),
            MemoryResponseStore(),
            MemoryAnalysisStore(),
        )
        try:
            response = client.get("/api/v1/studies/missing/export")
            assert response.status_code == 404
        finally:
            _clear_overrides()


class TestStudyDeleteCascade:
    """Tests that study deletion cascades to all derived artefacts."""

    def test_delete_study_cascades_all(
        self,
        mock_llm_client: MagicMock,
        clean_store: MemoryPersonaStore,
    ) -> None:
        q_store = MemoryQuestionnaireStore()
        r_store = MemoryResponseStore()
        a_store = MemoryAnalysisStore()
        _override_deps(mock_llm_client, clean_store, q_store, r_store, a_store)

        try:
            client.post(
                "/api/v1/studies",
                json={
                    "study_id": "scascade",
                    "product_category": "洗碗机",
                    "research_goal": "test",
                },
            )
            client.post("/api/v1/studies/scascade/generate")
            client.post("/api/v1/personas/generate", json={"count": 2, "study_id": "scascade"})
            client.post(
                "/api/v1/studies/scascade/simulate-responses",
                json={
                    "persona_ids": ["persona-scascade-001", "persona-scascade-002"],
                    "mode": "rule",
                },
            )

            job = AnalysisJobStatus(
                analysis_id="analysis-scascade-001",
                study_id="scascade",
                status="COMPLETED",
                model_type="hb",
                queued_at=datetime.now(UTC),
                estimated_duration_seconds=60,
            )
            a_store.save_job(job)

            response = client.delete("/api/v1/studies/scascade")
            assert response.status_code == 204

            assert q_store.get_study("scascade") is None
            assert q_store.get_questionnaire("scascade") is None
            assert clean_store.list_all(study_id="scascade")[1] == 0
            assert r_store.list_responses_by_study("scascade")[1] == 0
            assert r_store.get_dataset("scascade") is None
            assert a_store.list_jobs_by_study("scascade") == []
        finally:
            _clear_overrides()

    def test_delete_nonexistent_study(
        self,
        mock_llm_client: MagicMock,
        clean_store: MemoryPersonaStore,
    ) -> None:
        _override_deps(
            mock_llm_client,
            clean_store,
            MemoryQuestionnaireStore(),
            MemoryResponseStore(),
            MemoryAnalysisStore(),
        )
        try:
            response = client.delete("/api/v1/studies/missing")
            assert response.status_code == 404
        finally:
            _clear_overrides()


class TestStoreCascadeHelpers:
    """Direct tests for store-level cascade helpers."""

    def test_response_store_delete_by_persona(self) -> None:
        from aicbc.questionnaire.response_models import PersonaResponse

        store = MemoryResponseStore()
        r1 = PersonaResponse(
            response_id="r1",
            study_id="s1",
            persona_id="p1",
            questionnaire_id="q1",
            completion_status="COMPLETED",
        )
        r2 = PersonaResponse(
            response_id="r2",
            study_id="s1",
            persona_id="p2",
            questionnaire_id="q1",
            completion_status="COMPLETED",
        )
        store.save_response(r1)
        store.save_response(r2)

        assert store.delete_by_persona("p1") == 1
        assert store.get_response("r1") is None
        assert store.get_response("r2") is not None

    def test_response_store_delete_by_study(self) -> None:
        from aicbc.questionnaire.response_models import (
            CBCRawDataset,
            DatasetMetadata,
            PersonaResponse,
        )

        store = MemoryResponseStore()
        r1 = PersonaResponse(
            response_id="r1",
            study_id="s1",
            persona_id="p1",
            questionnaire_id="q1",
            completion_status="COMPLETED",
        )
        dataset = CBCRawDataset(
            metadata=DatasetMetadata(
                study_id="s1",
                questionnaire_id="q1",
                n_respondents=1,
                n_choice_sets=1,
                n_alternatives=2,
            ),
            choice_records=[],
        )
        store.save_response(r1)
        store.save_dataset("s1", dataset)

        assert store.delete_by_study("s1") == 2
        assert store.get_response("r1") is None
        assert store.get_dataset("s1") is None

    def test_analysis_store_delete_by_study(self) -> None:
        store = MemoryAnalysisStore()
        job = AnalysisJobStatus(
            analysis_id="a1",
            study_id="s1",
            status="COMPLETED",
            model_type="hb",
            queued_at=datetime.now(UTC),
            estimated_duration_seconds=60,
        )
        store.save_job(job)

        assert store.delete_by_study("s1") == 1
        assert store.get_job("a1") is None


class TestPIIRedactionInAuditLogs:
    """Verify audit logs do not leak raw PII."""

    def test_audit_log_redacts_pii_in_data(self):
        logger = get_audit_logger()
        logger.clear_memory_logs()

        # Simulate an audit entry that accidentally contains PII.
        import asyncio

        asyncio.run(
            logger.log_event(
                action="POST",
                resource="personas",
                resource_id="p1",
                result="success",
                data={
                    "note": "用户电话 13800138000 和邮箱 alice@example.com",
                    "path": "/api/v1/personas",
                },
            )
        )

        entries = logger.get_memory_logs()
        assert len(entries) == 1
        data = entries[0]["data"]
        assert "13800138000" not in data["note"]
        assert "alice@example.com" not in data["note"]
        assert "[REDACTED:" in data["note"]


class TestPIIRedactionInExports:
    """Verify data exports do not leak raw PII."""

    def test_export_persona_redacts_pii_in_profile(
        self,
        mock_llm_client: MagicMock,
        clean_store: MemoryPersonaStore,
    ) -> None:
        _override_deps(
            mock_llm_client,
            clean_store,
            MemoryQuestionnaireStore(),
            MemoryResponseStore(),
            MemoryAnalysisStore(),
        )
        try:
            # Generate a persona, then inject PII into its narrative.
            client.post("/api/v1/personas/generate", json={"count": 1, "study_id": "pii-redact"})
            persona_id = "persona-pii-redact-001"
            profile = clean_store.get(persona_id)
            assert profile is not None
            profile.layer4_scenarios.daily_routine = (
                "我的电话是13800138000，邮箱是alice@example.com。"
            )
            clean_store.save(profile)

            response = client.get(f"/api/v1/personas/{persona_id}/export")
            assert response.status_code == 200

            payload = response.text
            assert "13800138000" not in payload
            assert "alice@example.com" not in payload
            assert "[REDACTED:" in payload
        finally:
            _clear_overrides()
