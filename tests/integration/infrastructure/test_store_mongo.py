"""Integration tests for MongoDB-backed stores.

These tests require a running MongoDB instance.  If ``MONGODB_URL`` is not
reachable the module falls back to ``mongomock`` so the suite still runs in
memory-only CI environments.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

import os
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient

from aicbc.analysis.models import (
    AnalysisJobStatus,
    AnalysisResultResponse,
    ConvergenceDiagnostics,
)
from aicbc.analysis.store import MemoryAnalysisStore
from aicbc.core.models.persona import PersonaProfile
from aicbc.core.store import (
    MemoryPersonaStore,
    MemoryQuestionnaireStore,
    MemoryResponseStore,
)
from aicbc.core.store_mongo import (
    MongoAnalysisStore,
    MongoPersonaStore,
    MongoQuestionnaireStore,
    MongoResponseStore,
)
from aicbc.questionnaire.models import CBCStudy
from aicbc.questionnaire.response_models import CBCRawDataset, PersonaResponse


async def _mongo_available() -> bool:
    """Check whether the configured MongoDB is reachable."""
    url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
    try:
        client: AsyncIOMotorClient = AsyncIOMotorClient(url, serverSelectionTimeoutMS=1500)
        await client.admin.command("ping")
        client.close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module")
async def mongo_client():
    """Yield a MongoDB client (real or mocked) and drop the test database afterwards."""
    if await _mongo_available():
        url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
        client = AsyncIOMotorClient(url)
        db_name = "aicbc_test_stores"
        db = client[db_name]
        # Reset test database.
        await client.drop_database(db_name)
    else:
        # Fall back to mongomock for CI environments without MongoDB.
        from mongomock_motor import AsyncMongoMockClient

        client = AsyncMongoMockClient()
        db_name = "aicbc_test_stores"
        db = client[db_name]

    # Initialize Beanie with all document models.
    from beanie import init_beanie

    from aicbc.core.models.db_documents import ALL_DOCUMENT_MODELS

    # Patch mongomock's list_collection_names to ignore unknown kwargs
    # and patch mongomock_motor to properly await Beanie query objects.
    if not await _mongo_available():
        import mongomock

        _orig_list_collections = mongomock.database.Database.list_collection_names

        def _patched_list_collection_names(self, *args, **kwargs):
            for key in list(kwargs.keys()):
                if key not in ("session",):
                    kwargs.pop(key, None)
            return _orig_list_collections(self, *args, **kwargs)

        mongomock.database.Database.list_collection_names = _patched_list_collection_names

        # Patch _run in store_mongo to handle mongomock_motor query objects
        import aicbc.core.store_mongo as _store_mongo_module

        _orig_run = _store_mongo_module._run

        def _patched_run(awaitable):
            async def _execute():
                # Handle Beanie query objects by awaiting them
                if hasattr(awaitable, "__await__"):
                    return await awaitable
                return awaitable

            try:
                import asyncio

                asyncio.get_running_loop()
                # We're in an async context, just await directly
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, _execute())
                    return future.result()
            except RuntimeError:
                return asyncio.run(_execute())

        _store_mongo_module._run = _patched_run

    await init_beanie(database=db, document_models=ALL_DOCUMENT_MODELS)

    yield client

    if await _mongo_available():
        await client.drop_database(db_name)
        client.close()


@pytest.fixture
async def clean_db(mongo_client):
    """Drop all collections before each test for isolation."""
    from aicbc.core.models.db_documents import ALL_DOCUMENT_MODELS

    db = mongo_client["aicbc_test_stores"]
    for doc_model in ALL_DOCUMENT_MODELS:
        await db[doc_model.Settings.name].delete_many({})


@pytest.fixture
def sample_study() -> CBCStudy:
    return CBCStudy(
        study_id="study-test-001",
        product_category="test",
        research_goal="test",
        target_segments=["A"],
        attributes=[
            {
                "id": "price",
                "name": "价格",
                "type": "price",
                "levels": [
                    {"value": 100, "label": "100"},
                    {"value": 200, "label": "200"},
                ],
            },
            {
                "id": "brand",
                "name": "品牌",
                "type": "categorical",
                "levels": [
                    {"value": "A", "label": "品牌A"},
                    {"value": "B", "label": "品牌B"},
                ],
            },
        ],
    )


def _build_persona(persona_id: str = "persona-study-test-001-1") -> PersonaProfile:
    return PersonaProfile(
        persona_id=persona_id,
        segment="A",
        layer1_demographics={
            "age": "25-30",
            "gender": "女",
            "city": "一线城市",
            "income": "15-30万",
            "occupation": "白领",
            "education": "本科",
            "marital_status": "未婚",
            "living_type": "租房",
            "life_stage": "初入职场单身",
            "brand_relationship_stage": "初次了解",
        },
        layer2_behavior={
            "price_sensitivity": "中",
            "purchase_channels": ["线上"],
            "decision_style": "理性",
            "brand_loyalty": "低",
            "information_source": ["社交媒体"],
        },
        layer3_psychology={
            "core_values": ["品质"],
            "core_anxieties": ["时间焦虑"],
            "tension_combination": {
                "labels": ["高收入", "节俭"],
                "narrative_explanation": "她收入不错但成长于节俭家庭，习惯货比三家。" * 3,
            },
            "secret_motivation": "证明自己选择的眼光",
            "defense_mechanism": "合理化",
        },
        layer4_scenarios={
            "daily_routine": "朝九晚六，周末宅家",
            "purchase_trigger": "促销或朋友推荐",
            "stress_response": "先做攻略",
            "social_behavior": "朋友圈分享好物",
        },
        dishwasher_context={
            "purchase_constraints": [],
            "decision_factors": [],
            "ignored_factors": [],
        },
        language_samples=[
            "我觉得价格合适最重要，同时品质也要有保障，才会考虑购买。",
            "朋友推荐的产品我会优先考虑，但最终还是要自己亲自看看评价。",
            "大促活动期间我会适当囤货，平时消费则会比较克制和理性。",
        ],
        authenticity_score=10,
        bias_audit_status="PASSED",
        created_at=datetime.now(UTC),
    )


class TestMongoPersonaStore:
    """Persona persistence tests."""

    def test_save_and_get(self, clean_db):
        store = MongoPersonaStore()
        persona = _build_persona()
        assert store.save(persona) is True

        loaded = store.get(persona.persona_id)
        assert loaded is not None
        assert loaded.persona_id == persona.persona_id
        assert loaded.segment == persona.segment

    def test_duplicate_rejected(self, clean_db):
        store = MongoPersonaStore()
        persona = _build_persona("persona-dup-001")
        assert store.save(persona) is True
        # Same content with a different persona_id must be rejected.
        duplicate = _build_persona("persona-dup-002")
        assert store.save(duplicate) is False
        # Same persona_id with updated content should be accepted (upsert).
        persona2 = _build_persona("persona-dup-001")
        persona2.segment = "B"
        assert store.save(persona2) is True

    def test_delete(self, clean_db):
        store = MongoPersonaStore()
        persona = _build_persona()
        store.save(persona)
        assert store.delete(persona.persona_id) is True
        assert store.get(persona.persona_id) is None

    def test_list_with_filters(self, clean_db):
        store = MongoPersonaStore()
        p1 = _build_persona("persona-s1-001")
        p2 = _build_persona("persona-s1-002")
        p2.segment = "B"
        p2.layer1_demographics.city = "二线城市"
        store.save(p1)
        store.save(p2)

        items, total = store.list_all(segment="A")
        assert total == 1
        assert items[0].persona_id == p1.persona_id

        items, total = store.list_all(city_tier="二线城市")
        assert total == 1
        assert items[0].persona_id == p2.persona_id


class TestMongoQuestionnaireStore:
    """Study/questionnaire persistence tests."""

    def test_save_and_get_study(self, clean_db, sample_study):
        store = MongoQuestionnaireStore()
        store.save_study(sample_study)
        loaded = store.get_study(sample_study.study_id)
        assert loaded is not None
        assert loaded.study_id == sample_study.study_id

    def test_delete_study_cascades_questionnaire(self, clean_db, sample_study):
        from aicbc.questionnaire.models import (
            Alternative,
            CBCQuestionnaire,
            ChoiceSet,
        )

        store = MongoQuestionnaireStore()
        store.save_study(sample_study)
        choice_sets = [
            ChoiceSet(
                choice_set_id=i,
                alternatives=[
                    Alternative(alt_index=0, attributes={"price": 100, "brand": "A"}),
                    Alternative(alt_index=1, attributes={"price": 200, "brand": "B"}),
                    Alternative(alt_index=2, attributes={"price": 150, "brand": "A"}),
                ],
            )
            for i in range(1, 13)
        ]
        questionnaire = CBCQuestionnaire(
            questionnaire_id=f"q-{sample_study.study_id}",
            study_id=sample_study.study_id,
            attributes=sample_study.attributes,
            choice_sets=choice_sets,
            design_parameters=sample_study.design_parameters,
        )
        store.save_questionnaire(questionnaire)

        assert store.get_questionnaire(sample_study.study_id) is not None
        assert store.delete_study(sample_study.study_id) is True
        assert store.get_study(sample_study.study_id) is None
        assert store.get_questionnaire(sample_study.study_id) is None


class TestMongoResponseStore:
    """Response/dataset persistence tests."""

    def test_save_and_get_response(self, clean_db):
        store = MongoResponseStore()
        response = PersonaResponse(
            response_id="resp-001",
            study_id="study-test-001",
            persona_id="persona-001",
            questionnaire_id="q-001",
        )
        store.save_response(response)
        loaded = store.get_response(response.response_id)
        assert loaded is not None
        assert loaded.response_id == response.response_id

    def test_save_and_get_dataset(self, clean_db):
        store = MongoResponseStore()
        from aicbc.questionnaire.response_models import DatasetMetadata

        dataset = CBCRawDataset(
            metadata=DatasetMetadata(
                study_id="study-test-001",
                n_respondents=1,
                n_choice_sets=1,
                n_alternatives=2,
            ),
            choice_records=[],
        )
        store.save_dataset("study-test-001", dataset)
        loaded = store.get_dataset("study-test-001")
        assert loaded is not None
        assert loaded.metadata.study_id == dataset.metadata.study_id


class TestMongoAnalysisStore:
    """Analysis persistence tests."""

    def _make_job(self, analysis_id: str = "analysis-001") -> AnalysisJobStatus:
        return AnalysisJobStatus(
            analysis_id=analysis_id,
            study_id="study-test-001",
            status="QUEUED",
            model_type="hb",
            queued_at=datetime.now(UTC),
            estimated_duration_seconds=60,
        )

    def test_save_and_get_job(self, clean_db):
        store = MongoAnalysisStore()
        job = self._make_job()
        store.save_job(job)
        loaded = store.get_job(job.analysis_id)
        assert loaded is not None
        assert loaded.status == "QUEUED"

    def test_update_job_status(self, clean_db):
        store = MongoAnalysisStore()
        job = self._make_job()
        store.save_job(job)
        updated = store.update_job_status(job.analysis_id, "RUNNING", progress=50.0)
        assert updated is not None
        assert updated.status == "RUNNING"
        assert updated.progress_percent == 50.0

    def test_save_and_get_result(self, clean_db):
        store = MongoAnalysisStore()
        result = AnalysisResultResponse(
            analysis_id="analysis-001",
            study_id="study-test-001",
            status="COMPLETED",
            model_type="hb",
            convergence=ConvergenceDiagnostics(
                rhat_max=1.05,
                rhat_by_param={"price": 1.01},
                ess_bulk_min=100.0,
                ess_tail_min=100.0,
                ess_by_param={"price": 150.0},
                converged=True,
                reliable_ess=True,
            ),
            population_params={"mu": {}, "sigma": {}},
            individual_utilities={},
            importance={},
            wtp={},
            processing_time_seconds=1.0,
        )
        store.save_result(result)
        loaded = store.get_result(result.analysis_id)
        assert loaded is not None
        assert loaded.status == "COMPLETED"


class TestStoreFactoryMemoryFallback:
    """Ensure the factory selects memory stores when requested."""

    def test_memory_store_aliases(self):
        from aicbc.analysis.store import AnalysisStore
        from aicbc.core.store import (
            PersonaStore,
            QuestionnaireStore,
            ResponseStore,
        )

        assert PersonaStore is MemoryPersonaStore
        assert QuestionnaireStore is MemoryQuestionnaireStore
        assert ResponseStore is MemoryResponseStore
        assert AnalysisStore is MemoryAnalysisStore
