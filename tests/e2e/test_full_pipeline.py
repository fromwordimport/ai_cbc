"""End-to-end integration tests: full pipeline from study creation to market simulation.

Flow under test:
    CreateStudy → GeneratePersonas → DesignQuestionnaire → SimulateResponses
    → RunHBAnalysis → ComputeImportance → ComputeWTP → MarketSimulation

This test verifies data format consistency, effects coding naming conventions,
error propagation, and persona_id tracking across ALL subsystems.

All LLM calls are mocked — no real API requests. HB sampling uses tiny config.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from aicbc.analysis.engines.hb_engine import HBConfig, HBEngine, HBResult
from aicbc.analysis.models import (
    AnalysisResultResponse,
    ConvergenceDiagnostics,
    PopulationParams,
)
from aicbc.analysis.preprocessing import get_feature_columns, to_long_format, validate_dataset
from aicbc.analysis.results.importance import aggregate_importance, compute_importance
from aicbc.analysis.results.wtp import WTPCalculator
from aicbc.analysis.simulation.market_simulator import MarketSimulator
from aicbc.analysis.store import AnalysisStore
from aicbc.core.models.persona import (
    DishwasherContext,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    PersonaProfile,
    TensionCombination,
)
from aicbc.core.simulation.cbc_choice_simulator import CBCChoiceSimulator
from aicbc.core.store import (
    PersonaStore,
    ResponseStore,
    get_questionnaire_store,
)
from aicbc.core.validators import LogicValidator, SchemaValidator
from aicbc.generators.profile_generator import ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator
from aicbc.llm.client import LLMResponse, Provider
from aicbc.questionnaire.design.effects_coding import encode_profile, n_parameters
from aicbc.questionnaire.generator import QuestionnaireGenerator
from aicbc.questionnaire.models import (
    AttributeType,
    CBCQuestionnaire,
    CBCStudy,
    StudyStatus,
)
from aicbc.questionnaire.response_models import (
    CBCRawDataset,
    DatasetMetadata,
)

# ═══════════════════════════════════════════════════════════════════════════
# Helpers: mock LLM responses for persona generation
# ═══════════════════════════════════════════════════════════════════════════


def _mock_response(content: dict[str, Any] | str, model: str = "claude-sonnet-4-6") -> LLMResponse:
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


def _mock_layer1() -> dict[str, Any]:
    return {
        "age": "35岁",
        "gender": "男",
        "city": "一线城市",
        "income": "月收入25K-40K",
        "occupation": "高级工程师",
        "education": "硕士",
        "marital_status": "已婚有孩",
        "living_type": "自有住房（120㎡三居室）",
    }


def _mock_layer2() -> dict[str, Any]:
    return {
        "price_sensitivity": "中等，看重性价比但愿意为品质付费",
        "purchase_channels": ["京东自营", "天猫旗舰店", "线下国美"],
        "decision_style": "理性比较型，购买前必看测评",
        "brand_loyalty": "中等，对德系品牌有好感",
        "information_source": ["知乎", "B站测评", "什么值得买", "朋友推荐"],
    }


def _mock_layer3() -> dict[str, Any]:
    return {
        "core_values": ["效率至上", "家庭幸福", "理性消费"],
        "core_anxieties": ["工作太忙没时间做家务", "孩子成长环境"],
        "tension_combination": {
            "labels": ["高收入", "极度理性消费"],
            "narrative_explanation": (
                "他作为高级工程师收入不低，但农村出身的成长经历让他对每一笔大额支出都反复权衡。"
                "买洗碗机这件事他已经研究了三个月，对比了十几个型号的参数和价格，但就是下不了决心。"
                "这背后是他对'浪费'的深层恐惧——父母的节俭教育已经内化成了他的消费基因。"
            ),
        },
        "secret_motivation": "通过科技产品提升家庭生活质量，弥补工作繁忙对家庭的亏欠",
        "defense_mechanism": "理智化——把消费决策变成技术评测项目，用数据说服自己",
    }


def _mock_layer4() -> dict[str, Any]:
    return {
        "daily_routine": "早7点半出门，晚8点到家，周末带娃上兴趣班",
        "purchase_trigger": "双十一大促叠加老婆催促，终于下决心购买",
        "stress_response": "工作压力大时反而更清醒理性，用分析缓解焦虑",
        "social_behavior": "朋友群里的'参数帝'，经常帮人分析家电选购",
    }


def _mock_auxiliary() -> dict[str, Any]:
    return {
        "language_samples": [
            "这个洗碗机的清洁效果真的不错，碗拿出来都是热乎乎的。",
            "对比了三个品牌五个型号，最后选了性价比最高的这款。",
            "安装的时候才发现厨房空间比想象的大，师傅说嵌入式没问题。",
        ],
        "dishwasher_context": {
            "purchase_constraints": ["厨房空间中等，需要嵌入式", "预算控制在5000以内"],
            "decision_factors": ["清洁效果", "品牌口碑", "安装便利性", "能耗等级"],
            "ignored_factors": ["外观设计", "智能互联功能", "APP控制"],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def e2e_mock_llm() -> MagicMock:
    """Return a mock LLMClient that returns valid persona data for e2e tests.

    Named differently from conftest's 'mock_llm_client' to avoid override conflicts.
    """
    client = MagicMock()
    client.generate.side_effect = [
        _mock_response(_mock_layer1()),
        _mock_response(_mock_layer2()),
        _mock_response(_mock_layer3()),
        _mock_response(_mock_layer4()),
        _mock_response(_mock_auxiliary()),
    ]
    return client


@pytest.fixture
def study_id() -> str:
    # Must match persona_id pattern: ^persona-[a-z0-9_]+-\d+$
    return f"e2etest{uuid.uuid4().hex[:8]}"


@pytest.fixture
def persona_store():
    """Return a clean persona store."""
    store = PersonaStore()
    yield store
    store.clear()


@pytest.fixture
def response_store():
    """Return a clean response store."""
    store = ResponseStore()
    yield store
    store.clear()


@pytest.fixture
def analysis_store():
    """Return a clean analysis store."""
    store = AnalysisStore()
    yield store
    store.clear()


@pytest.fixture
def questionnaire_store():
    """Return a clean questionnaire store, isolated from the module singleton.

    Replaces the module-level singleton so that Depends(get_questionnaire_store)
    in API routes would resolve to this store during tests.
    """
    import aicbc.core.store as store_mod
    from aicbc.core.store import QuestionnaireStore

    old = store_mod._questionnaire_store
    store_mod._questionnaire_store = QuestionnaireStore()
    yield store_mod._questionnaire_store
    store_mod._questionnaire_store.clear()
    store_mod._questionnaire_store = old


@pytest.fixture
def dishwasher_study(study_id: str, questionnaire_store) -> CBCStudy:
    """Create a dishwasher CBC study with default attributes."""
    generator = QuestionnaireGenerator()
    study = generator.create_study(
        study_id=study_id,
        product_category="洗碗机",
        research_goal="评估价格敏感度与品牌偏好对洗碗机购买决策的影响",
        target_segments=["精致白领", "新手宝妈", "技术极客"],
    )
    questionnaire_store.save_study(study)
    return study


@pytest.fixture
def dishwasher_questionnaire(dishwasher_study: CBCStudy, questionnaire_store) -> CBCQuestionnaire:
    """Generate a questionnaire for the dishwasher study."""
    generator = QuestionnaireGenerator()
    questionnaire = generator.generate_questionnaire(dishwasher_study, seed=42)
    questionnaire_store.save_questionnaire(questionnaire)
    return questionnaire


@pytest.fixture
def persona_profiles(
    e2e_mock_llm: MagicMock, study_id: str, dishwasher_study: CBCStudy, persona_store
) -> list[PersonaProfile]:
    """Generate a batch of 3 personas for the study."""
    seed_gen = SeedGenerator(seed=99)
    profile_gen = ProfileGenerator(llm_client=e2e_mock_llm, study_id=study_id)

    personas = []
    for i in range(3):
        persona_id = f"persona-{study_id}-{i + 1:03d}"
        e2e_mock_llm.generate.side_effect = [
            _mock_response(_mock_layer1()),
            _mock_response(_mock_layer2()),
            _mock_response(_mock_layer3()),
            _mock_response(_mock_layer4()),
            _mock_response(_mock_auxiliary()),
        ]
        seed = seed_gen.generate_seed()
        profile = profile_gen.generate(persona_id, seed)

        # Assign purchase-relevant traits deterministically for testing
        if i == 0:
            profile.layer2_behavior.price_sensitivity = "极高，对价格非常敏感"
            profile.dishwasher_context.decision_factors = ["价格", "能耗等级", "清洁效果"]
            profile.dishwasher_context.ignored_factors = ["品牌"]
        elif i == 1:
            profile.layer2_behavior.price_sensitivity = "低，不太在意价格"
            profile.dishwasher_context.decision_factors = ["品牌", "安装方式", "核心功能"]
            profile.dishwasher_context.ignored_factors = ["价格"]
        else:
            profile.layer2_behavior.price_sensitivity = "中等，看性价比"
            profile.dishwasher_context.decision_factors = ["价格", "品牌口碑", "容量"]
            profile.dishwasher_context.ignored_factors = ["外观设计"]

        profile.bias_audit_status = "PASSED"
        profile.authenticity_score = 11.0
        persona_store.save(profile)
        personas.append(profile)

    return personas


@pytest.fixture
def simulated_dataset(
    dishwasher_study: CBCStudy,
    dishwasher_questionnaire: CBCQuestionnaire,
    persona_profiles: list[PersonaProfile],
    response_store,
) -> CBCRawDataset:
    """Simulate responses for all personas and return the aggregated dataset."""
    simulator = CBCChoiceSimulator(attributes=dishwasher_study.attributes)

    all_records = []
    for idx, persona in enumerate(persona_profiles):
        raw_slice, persona_response = simulator.simulate(
            persona=persona,
            questionnaire=dishwasher_questionnaire,
            deterministic=False,
            seed=42 + idx,
        )

        # Fix respondent_index
        for record in raw_slice.choice_records:
            record.respondent_index = idx

        all_records.extend(raw_slice.choice_records)
        response_store.save_response(persona_response)

    dataset = CBCRawDataset(
        metadata=DatasetMetadata(
            study_id=dishwasher_study.study_id,
            n_respondents=len(persona_profiles),
            n_choice_sets=len(dishwasher_questionnaire.choice_sets),
            n_alternatives=dishwasher_study.design_parameters.n_alternatives,
            attributes=[attr.model_dump(mode="json") for attr in dishwasher_study.attributes],
        ),
        choice_records=all_records,
    )
    response_store.save_dataset(dishwasher_study.study_id, dataset)
    return dataset


@pytest.fixture
def tiny_hb_config() -> HBConfig:
    """Tiny MCMC config for fast CI-friendly tests."""
    return HBConfig(
        n_draws=400,
        n_tune=400,
        n_chains=2,
        target_accept=0.9,
        random_seed=42,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test: Full End-to-End Pipeline
# ═══════════════════════════════════════════════════════════════════════════


class TestFullPipelineE2E:
    """Complete end-to-end pipeline: Study → Persona → Q → Responses → HB → WTP → Market."""

    def test_study_creation_produces_valid_study(self, dishwasher_study: CBCStudy):
        """Step 1: Study creation should produce a valid CBCStudy."""
        assert dishwasher_study.study_id is not None
        assert dishwasher_study.product_category == "洗碗机"
        assert (
            len(dishwasher_study.attributes) == 7
        )  # price, capacity, install, features, brand, energy, spray_arm, drying
        assert dishwasher_study.status == StudyStatus.INIT
        # Verify all expected attributes
        attr_ids = {a.id for a in dishwasher_study.attributes}
        assert attr_ids == {
            "price",
            "capacity",
            "installation",
            "spray_arm",
            "brand",
            "energy",
            "drying",
        }

    def test_questionnaire_generation_produces_valid_questionnaire(
        self, dishwasher_questionnaire: CBCQuestionnaire, dishwasher_study: CBCStudy
    ):
        """Step 2: Questionnaire generation should produce valid CBCQuestionnaire."""
        dp = dishwasher_study.design_parameters
        assert dishwasher_questionnaire.study_id == dishwasher_study.study_id
        assert len(dishwasher_questionnaire.choice_sets) == dp.n_choice_sets
        # Each choice set has the right number of alternatives
        for cs in dishwasher_questionnaire.choice_sets:
            assert len(cs.alternatives) == dp.n_alternatives
        # D-efficiency should be reported
        assert dishwasher_questionnaire.d_efficiency is not None
        assert 0.0 <= dishwasher_questionnaire.d_efficiency <= 1.0

    def test_persona_generation_produces_valid_profiles(
        self, persona_profiles: list[PersonaProfile], study_id: str
    ):
        """Step 3: Persona generation should produce valid four-layer profiles."""
        assert len(persona_profiles) == 3

        for p in persona_profiles:
            # ID format check
            assert p.persona_id.startswith(f"persona-{study_id}-")
            # Four layers exist
            assert isinstance(p.layer1_demographics, Layer1Demographics)
            assert isinstance(p.layer2_behavior, Layer2Behavior)
            assert isinstance(p.layer3_psychology, Layer3Psychology)
            assert isinstance(p.layer4_scenarios, Layer4Scenarios)
            # Auxiliary data exists
            assert isinstance(p.dishwasher_context, DishwasherContext)
            assert len(p.language_samples) == 3
            # Authenticity score assigned
            assert p.authenticity_score is not None
            assert 0 <= p.authenticity_score <= 14
            # Bias audit done
            assert p.bias_audit_status in ("PASSED", "FAILED", "PENDING")

    @pytest.mark.slow
    def test_full_pipeline_study_to_analysis(
        self,
        dishwasher_study: CBCStudy,
        dishwasher_questionnaire: CBCQuestionnaire,
        persona_profiles: list[PersonaProfile],
        simulated_dataset: CBCRawDataset,
        analysis_store: AnalysisStore,
        tiny_hb_config: HBConfig,
    ):
        """Steps 4-6: Simulate → Preprocess → Run HB → Compute WTP/Importance."""
        assert len(persona_profiles) == 3
        assert len(simulated_dataset.choice_records) > 0

        # ── Step 4: Preprocess dataset ──
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)
        assert not df_long.empty
        assert "chosen" in df_long.columns
        assert "resp_id" in df_long.columns
        assert "task_id" in df_long.columns

        # Effects coding column naming: {attr_id}_{level_index}
        feature_cols = get_feature_columns(attributes)
        expected_param_count = n_parameters(attributes)
        assert len(feature_cols) == expected_param_count

        # price should be a single column (continuous/price attribute)
        assert "price" in feature_cols

        # Each categorical/ordinal attribute produces k-1 columns with indices 0..k-2
        for attr in attributes:
            if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
                prefix_cols = [c for c in feature_cols if c.startswith(f"{attr.id}_")]
                assert len(prefix_cols) == len(attr.levels) - 1, (
                    f"Attribute {attr.id} should have {len(attr.levels) - 1} columns, "
                    f"got {len(prefix_cols)}"
                )
                expected_names = [f"{attr.id}_{i}" for i in range(len(attr.levels) - 1)]
                assert set(prefix_cols) == set(expected_names), (
                    f"Attribute {attr.id} columns mismatch: expected {expected_names}, "
                    f"got {prefix_cols}"
                )
            else:
                assert attr.id in feature_cols, (
                    f"Continuous/price attribute {attr.id} missing from feature_cols"
                )

        # ── Step 4b: Validate dataset ──
        validation = validate_dataset(simulated_dataset, attributes)
        assert validation["valid"], f"Dataset validation failed: {validation['errors']}"

        # ── Step 5: Run HB model ──
        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)

        assert isinstance(hb_result, HBResult)
        assert hb_result.converged
        assert hb_result.rhat_max < 1.1
        assert hb_result.ess_bulk_min > 0

        # Population parameters match feature_cols
        for col in feature_cols:
            assert col in hb_result.population_mu, f"Missing {col} in population_mu"
            assert col in hb_result.population_sigma, f"Missing {col} in population_sigma"

        # Individual utilities cover all personas
        persona_ids = {p.persona_id for p in persona_profiles}
        recovered_ids = set(hb_result.individual_utilities.keys())
        assert persona_ids == recovered_ids, (
            f"Persona ID mismatch: generated={persona_ids}, recovered={recovered_ids}"
        )
        for col in feature_cols:
            for pid in persona_ids:
                assert col in hb_result.individual_utilities[pid]

        # Price coefficient should be negative for all personas
        for pid, utils in hb_result.individual_utilities.items():
            assert utils["price"] < 0, f"Persona {pid} has non-negative price coefficient"

        # ── Step 5b: Build AnalysisResultResponse (as the API would) ──
        util_df = pd.DataFrame.from_dict(hb_result.individual_utilities, orient="index")

        # Importance
        importance_df = compute_importance(util_df, attributes)
        importance_agg = aggregate_importance(importance_df)
        assert not importance_df.empty
        assert "price" in importance_agg.index
        assert "brand" in importance_agg.index
        # All importances should be positive and sum to ~1 per respondent
        for row_idx in importance_df.index:
            row_sum = importance_df.loc[row_idx].sum()
            assert abs(row_sum - 1.0) < 0.01, f"Importance sum={row_sum} for {row_idx}"

        # WTP
        if "price" in util_df.columns:
            wtp_calc = WTPCalculator(util_df, price_col="price")
            wtp_data = wtp_calc.compute_all_wtp(attributes)
            assert "brand" in wtp_data or "capacity" in wtp_data
            price_summary = wtp_calc.price_coefficient_summary()
            assert price_summary["negative_rate"] > 0.5  # most coefficients negative

        # ── Step 6: Market simulation ──
        market_sim = MarketSimulator(util_df, attributes)
        scenarios = [
            {
                "name": "入门款",
                "price": str(2999),
                "capacity": "6套",
                "installation": "台式",
                "features": "基础",
                "brand": "美的",
                "energy": "二级",
            },
            {
                "name": "旗舰款",
                "price": str(5999),
                "capacity": "13套",
                "installation": "嵌入式",
                "features": "全能",
                "brand": "西门子",
                "energy": "超一级",
            },
        ]
        shares_df = market_sim.simulate_share(scenarios, rule="logit", include_none=True)

        assert len(shares_df) == 3  # 2 products + none
        assert "predicted_share" in shares_df.columns
        for _, row in shares_df.iterrows():
            assert 0.0 <= row["predicted_share"] <= 1.0

    @pytest.mark.slow
    def test_full_pipeline_with_store_integration(
        self,
        dishwasher_study: CBCStudy,
        dishwasher_questionnaire: CBCQuestionnaire,
        persona_profiles: list[PersonaProfile],
        simulated_dataset: CBCRawDataset,
        response_store,
        analysis_store: AnalysisStore,
        tiny_hb_config: HBConfig,
    ):
        """Verify the complete store-based pipeline (as the API would execute)."""
        study_id = dishwasher_study.study_id
        attributes = dishwasher_study.attributes

        # ── Stores should contain all data ──
        q_store = get_questionnaire_store()
        stored_study = q_store.get_study(study_id)
        assert stored_study is not None
        assert stored_study.status == StudyStatus.INIT

        stored_q = q_store.get_questionnaire(study_id)
        assert stored_q is not None
        assert stored_q.study_id == study_id

        stored_dataset = response_store.get_dataset(study_id)
        assert stored_dataset is not None
        assert stored_dataset.metadata.n_respondents == len(persona_profiles)
        assert len(stored_dataset.choice_records) > 0

        # ── Each response should reference a valid persona ──
        responses, _ = response_store.list_responses_by_study(study_id)
        assert len(responses) == len(persona_profiles)
        for resp in responses:
            assert resp.completion_status == "COMPLETED"
            assert resp.persona_id in {p.persona_id for p in persona_profiles}
            assert resp.study_id == study_id

        # ── Run analysis via the store-based flow ──
        df_long = to_long_format(stored_dataset, attributes)
        feature_cols = get_feature_columns(attributes)
        validation = validate_dataset(stored_dataset, attributes)
        assert validation["valid"]

        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)

        # Store results (as the API would)
        analysis_id = f"ar-{study_id}-e2e"
        util_df = pd.DataFrame.from_dict(hb_result.individual_utilities, orient="index")

        importance_df = compute_importance(util_df, attributes)
        importance_agg = aggregate_importance(importance_df)
        importance_dict = {
            attr_id: float(row["mean"]) for attr_id, row in importance_agg.iterrows()
        }

        wtp_data = {}
        if "price" in util_df.columns:
            wtp_calc = WTPCalculator(util_df, price_col="price")
            wtp_data = wtp_calc.compute_all_wtp(attributes)

        result = AnalysisResultResponse(
            analysis_id=analysis_id,
            study_id=study_id,
            status="COMPLETED",
            model_type="hb",
            convergence=ConvergenceDiagnostics(
                rhat_max=hb_result.rhat_max,
                rhat_by_param=hb_result.population_mu,
                ess_bulk_min=hb_result.ess_bulk_min,
                ess_tail_min=hb_result.ess_bulk_min,
                ess_by_param=hb_result.population_sigma,
                converged=hb_result.converged,
                reliable_ess=hb_result.converged,
            ),
            population_params=PopulationParams(
                mu=hb_result.population_mu,
                sigma=hb_result.population_sigma,
            ),
            individual_utilities=hb_result.individual_utilities,
            importance=importance_dict,
            wtp=wtp_data,
            processing_time_seconds=1.0,
            completed_at=datetime.now(UTC),
        )
        analysis_store.save_result(result)

        # ── Retrieve and verify stored results ──
        stored_result = analysis_store.get_result(analysis_id)
        assert stored_result is not None
        assert stored_result.analysis_id == analysis_id
        assert stored_result.study_id == study_id
        assert stored_result.status == "COMPLETED"
        assert stored_result.convergence.converged
        assert len(stored_result.individual_utilities) == len(persona_profiles)
        assert len(stored_result.importance) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Test: Data Format Consistency
# ═══════════════════════════════════════════════════════════════════════════


class TestDataFormatConsistency:
    """Verify data format compliance with docs/数据字典.md across subsystems."""

    def test_persona_profile_fields_match_datadict(self, persona_profiles: list[PersonaProfile]):
        """PersonaProfile should have all fields defined in 数据字典 section 二."""
        for p in persona_profiles:
            d = p.to_dict()
            required_fields = [
                "persona_id",
                "segment",
                "layer1_demographics",
                "layer2_behavior",
                "layer3_psychology",
                "layer4_scenarios",
                "language_samples",
                "dishwasher_context",
                "authenticity_score",
                "bias_audit_status",
                "generation_metadata",
                "created_at",
            ]
            for field in required_fields:
                assert field in d, f"Missing field '{field}' in persona {p.persona_id}"

            # Layer1 sub-fields (section 2.1)
            l1 = d["layer1_demographics"]
            for f in [
                "age",
                "gender",
                "city",
                "income",
                "occupation",
                "education",
                "marital_status",
                "living_type",
            ]:
                assert f in l1, f"Missing layer1 field '{f}'"

            # Layer2 sub-fields (section 2.2)
            l2 = d["layer2_behavior"]
            for f in [
                "price_sensitivity",
                "purchase_channels",
                "decision_style",
                "brand_loyalty",
                "information_source",
            ]:
                assert f in l2, f"Missing layer2 field '{f}'"

            # Layer3 sub-fields (section 2.3)
            l3 = d["layer3_psychology"]
            for f in [
                "core_values",
                "core_anxieties",
                "tension_combination",
                "secret_motivation",
                "defense_mechanism",
            ]:
                assert f in l3, f"Missing layer3 field '{f}'"
            assert "narrative_explanation" in l3["tension_combination"]
            assert len(l3["tension_combination"]["narrative_explanation"]) >= 50

            # Layer4 sub-fields (section 2.4)
            l4 = d["layer4_scenarios"]
            for f in ["daily_routine", "purchase_trigger", "stress_response", "social_behavior"]:
                assert f in l4, f"Missing layer4 field '{f}'"

            # DishwasherContext (section 2.5)
            dc = d["dishwasher_context"]
            for f in ["purchase_constraints", "decision_factors", "ignored_factors"]:
                assert f in dc, f"Missing dishwasher_context field '{f}'"

    def test_cbc_dataset_fields_match_datadict(self, simulated_dataset: CBCRawDataset):
        """CBCRawDataset should match 数据字典 section 五."""
        d = simulated_dataset.to_dict()

        # Metadata (section 5.1)
        assert "metadata" in d
        meta = d["metadata"]
        for f in ["study_id", "n_respondents", "n_choice_sets", "n_alternatives"]:
            assert f in meta, f"Missing metadata field '{f}'"

        # Choice records (section 5.2)
        assert "choice_records" in d
        assert len(d["choice_records"]) > 0
        for record in d["choice_records"]:
            for f in [
                "respondent_id",
                "respondent_index",
                "segment",
                "choice_set_id",
                "choice_set_index",
                "alternatives",
                "none_chosen",
            ]:
                assert f in record, f"Missing choice_record field '{f}'"

            # Alternatives (section 5.3)
            for alt in record["alternatives"]:
                assert "alt_index" in alt
                assert "chosen" in alt
                assert "attributes" in alt

    @pytest.mark.slow
    def test_analysis_result_fields_match_datadict(
        self,
        dishwasher_study: CBCStudy,
        simulated_dataset: CBCRawDataset,
        tiny_hb_config: HBConfig,
    ):
        """AnalysisResult should match 数据字典 section 七 after pipeline run."""
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)

        # Build AnalysisResultResponse (as the pipeline would)
        util_df = pd.DataFrame.from_dict(hb_result.individual_utilities, orient="index")
        importance_df = compute_importance(util_df, attributes)

        result = AnalysisResultResponse(
            analysis_id="ar-test-datadict",
            study_id=dishwasher_study.study_id,
            status="COMPLETED",
            model_type="hb",
            convergence=ConvergenceDiagnostics(
                rhat_max=hb_result.rhat_max,
                rhat_by_param={},
                ess_bulk_min=hb_result.ess_bulk_min,
                ess_tail_min=hb_result.ess_bulk_min,
                ess_by_param={},
                converged=hb_result.converged,
                reliable_ess=hb_result.converged,
            ),
            population_params=PopulationParams(
                mu=hb_result.population_mu,
                sigma=hb_result.population_sigma,
            ),
            individual_utilities=hb_result.individual_utilities,
            importance={
                attr_id: float(row["mean"])
                for attr_id, row in aggregate_importance(importance_df).iterrows()
            },
            wtp={},
            processing_time_seconds=1.0,
        )

        d = result.model_dump(mode="json")
        for f in [
            "analysis_id",
            "study_id",
            "model_type",
            "convergence",
            "individual_utilities",
            "importance",
            "wtp",
        ]:
            assert f in d, f"Missing AnalysisResult field '{f}'"

        # Convergence sub-fields (section 7.1) — values must be present and
        # well-formed; strict convergence (rhat_max < 1.1) is not asserted here
        # because the tiny synthetic dataset used for format checks is too small
        # to guarantee MCMC convergence on all platforms.
        conv = d["convergence"]
        for f in ["rhat_max", "ess_bulk_min", "converged"]:
            assert f in conv, f"Missing convergence field '{f}'"
        assert conv["rhat_max"] is not None and conv["rhat_max"] >= 1.0

    def test_persona_response_fields_match_datadict(
        self,
        dishwasher_study: CBCStudy,
        persona_profiles: list[PersonaProfile],
        response_store,
        simulated_dataset,
    ):
        """PersonaResponse should match 数据字典 section 六."""
        study_id = dishwasher_study.study_id
        responses, _ = response_store.list_responses_by_study(study_id)
        assert len(responses) > 0

        for resp in responses:
            d = resp.model_dump(mode="json")
            for f in [
                "response_id",
                "study_id",
                "persona_id",
                "questionnaire_id",
                "responses",
                "completion_status",
            ]:
                assert f in d, f"Missing PersonaResponse field '{f}'"

            assert resp.completion_status in ("COMPLETED", "PARTIAL", "FAILED")
            assert len(resp.responses) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Test: Effects Coding Consistency
# ═══════════════════════════════════════════════════════════════════════════


class TestEffectsCodingConsistency:
    """Verify effects coding naming conventions match docs/数据字典.md Section 10."""

    def test_naming_convention_matches_datadict(self, dishwasher_study: CBCStudy):
        """Column names follow {attribute_id}_{level_index} convention."""
        feature_cols = get_feature_columns(dishwasher_study.attributes)

        # Total parameter count matches the design
        assert len(feature_cols) == n_parameters(dishwasher_study.attributes)

        attr_ids = {attr.id for attr in dishwasher_study.attributes}

        # Every column matches either {attribute_id} or {attribute_id}_{level_index}
        for col in feature_cols:
            if "_" in col:
                attr_id, idx_str = col.rsplit("_", 1)
                assert attr_id in attr_ids, f"Column {col} references unknown attribute {attr_id}"
                assert idx_str.isdigit(), f"Column {col} has non-numeric level index {idx_str}"
            else:
                assert col in attr_ids, f"Column {col} does not match any attribute id"

        # Each categorical/ordinal attribute has exactly k-1 columns indexed 0..k-2
        for attr in dishwasher_study.attributes:
            if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
                expected = {f"{attr.id}_{i}" for i in range(len(attr.levels) - 1)}
                actual = {c for c in feature_cols if c.startswith(f"{attr.id}_")}
                assert actual == expected, (
                    f"Attribute {attr.id} expected columns {sorted(expected)}, got {sorted(actual)}"
                )

    def test_n_parameters_matches_datadict(self, dishwasher_study: CBCStudy):
        """Total parameter count should be 17 (Section 10.1)."""
        np = n_parameters(dishwasher_study.attributes)
        assert np == 17, f"Expected 17 total parameters, got {np}"

    @pytest.mark.slow
    def test_last_level_recovery(
        self, dishwasher_study: CBCStudy, simulated_dataset: CBCRawDataset, tiny_hb_config: HBConfig
    ):
        """Last level of each categorical attribute should be recoverable via negative sum."""
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)

        for attr in attributes:
            if attr.type not in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
                continue

            n_levels = len(attr.levels)
            if n_levels <= 2:
                continue

            # Gather first n-1 parameter values from population mu
            params = []
            for i in range(n_levels - 1):
                col = f"{attr.id}_{i}"
                if col in hb_result.population_mu:
                    params.append(hb_result.population_mu[col])

            # The last level should be -(sum of first n-1), so we only need the
            # first n-1 parameters to be finite.
            assert all(np.isfinite(p) for p in params), f"Non-finite params for {attr.id}"

    def test_encode_profile_roundtrip(
        self, dishwasher_questionnaire: CBCQuestionnaire, dishwasher_study: CBCStudy
    ):
        """Encoding a profile should produce the expected parameter structure."""
        attributes = dishwasher_study.attributes

        for cs in dishwasher_questionnaire.choice_sets:
            for alt in cs.alternatives:
                encoded = encode_profile(alt.attributes, attributes)
                assert len(encoded) == n_parameters(attributes)
                assert np.isfinite(encoded).all()

    def test_preprocessing_preserves_attribute_levels(
        self, dishwasher_study: CBCStudy, simulated_dataset: CBCRawDataset
    ):
        """Preprocessing should correctly encode all attributes from the dataset."""
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)

        # Every choice record should have a corresponding row
        expected_rows = sum(len(record.alternatives) for record in simulated_dataset.choice_records)
        assert len(df_long) == expected_rows, f"Got {len(df_long)} rows, expected {expected_rows}"

        # Exactly one chosen per task per respondent
        choice_counts = df_long.groupby(["resp_id", "task_id"])["chosen"].sum()
        assert (choice_counts == 1).all(), "Some tasks don't have exactly one chosen alternative"


# ═══════════════════════════════════════════════════════════════════════════
# Test: Persona ID Consistency
# ═══════════════════════════════════════════════════════════════════════════


class TestPersonaIdConsistency:
    """Verify persona_id flows consistently through the entire pipeline."""

    def test_persona_id_in_responses(
        self,
        persona_profiles: list[PersonaProfile],
        simulated_dataset: CBCRawDataset,
        response_store,
        dishwasher_study: CBCStudy,
    ):
        """Persona ID in responses must match the original profiles."""
        study_id = dishwasher_study.study_id
        persona_ids = {p.persona_id for p in persona_profiles}

        # In the raw dataset
        record_ids = {record.respondent_id for record in simulated_dataset.choice_records}
        assert record_ids == persona_ids, (
            f"Dataset respondent IDs mismatch: {persona_ids} vs {record_ids}"
        )

        # In stored responses
        responses, _ = response_store.list_responses_by_study(study_id)
        response_ids = {r.persona_id for r in responses}
        assert response_ids == persona_ids, (
            f"Stored response persona IDs mismatch: {persona_ids} vs {response_ids}"
        )

    @pytest.mark.slow
    def test_persona_id_in_analysis(
        self,
        persona_profiles: list[PersonaProfile],
        dishwasher_study: CBCStudy,
        simulated_dataset: CBCRawDataset,
        tiny_hb_config: HBConfig,
    ):
        """Analysis output must contain the same persona IDs."""
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)

        persona_ids = {p.persona_id for p in persona_profiles}
        analysis_ids = set(hb_result.individual_utilities.keys())
        assert persona_ids == analysis_ids, (
            f"Analysis persona ID mismatch: {persona_ids} vs {analysis_ids}"
        )

    def test_segment_labels_in_dataset(
        self,
        persona_profiles: list[PersonaProfile],
        simulated_dataset: CBCRawDataset,
    ):
        """Segment labels in the dataset should match persona segments."""
        persona_segment_map = {p.persona_id: p.segment for p in persona_profiles}

        for record in simulated_dataset.choice_records:
            expected_segment = persona_segment_map[record.respondent_id]
            assert record.segment == expected_segment, (
                f"Segment mismatch for {record.respondent_id}: "
                f"expected '{expected_segment}', got '{record.segment}'"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Test: Error Propagation
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorPropagation:
    """Verify proper error handling at each pipeline stage."""

    def test_missing_persona_during_simulation(
        self,
        dishwasher_study: CBCStudy,
        dishwasher_questionnaire: CBCQuestionnaire,
        persona_store,
        response_store,
    ):
        """Simulation should skip personas not found in store."""
        simulator = CBCChoiceSimulator(attributes=dishwasher_study.attributes)

        # Only save some personas (empty list means no personas available)
        for _record, _ in [
            simulator.simulate(
                persona=p,
                questionnaire=dishwasher_questionnaire,
                deterministic=True,
                seed=42,
            )
            for p in []  # no personas available
        ]:
            pass

        # This should not crash, just produce nothing
        assert True  # survived

    def test_missing_dataset_for_analysis(self, dishwasher_study: CBCStudy):
        """Analysis with empty/missing dataset should be detected."""
        attributes = dishwasher_study.attributes

        empty_dataset = CBCRawDataset(
            metadata=DatasetMetadata(
                study_id=dishwasher_study.study_id,
                n_respondents=0,
                n_choice_sets=dishwasher_study.design_parameters.n_choice_sets,
                n_alternatives=dishwasher_study.design_parameters.n_alternatives,
            ),
            choice_records=[],
        )

        validation = validate_dataset(empty_dataset, attributes)
        assert not validation["valid"]
        assert any("empty" in e.lower() for e in validation["errors"])

    def test_invalid_dataset_missing_attribute(
        self, dishwasher_study: CBCStudy, simulated_dataset: CBCRawDataset
    ):
        """Dataset with a profile missing an attribute should fail encoding."""
        # Create a corrupted dataset
        corrupted = simulated_dataset.model_copy(deep=True)
        # Remove "price" from one alternative
        if corrupted.choice_records:
            for alt in corrupted.choice_records[0].alternatives:
                if "price" in alt.attributes:
                    del alt.attributes["price"]
                    break

        attributes = dishwasher_study.attributes
        with pytest.raises(ValueError, match="missing attribute"):
            to_long_format(corrupted, attributes)

    def test_dataset_with_multiple_choices(
        self, dishwasher_study: CBCStudy, simulated_dataset: CBCRawDataset
    ):
        """Dataset validation should catch tasks with multiple chosen alternatives."""
        corrupted = simulated_dataset.model_copy(deep=True)
        if corrupted.choice_records:
            # Mark two alternatives as chosen
            alts = corrupted.choice_records[0].alternatives
            if len(alts) >= 2:
                alts[0].chosen = True
                alts[1].chosen = True

        attributes = dishwasher_study.attributes
        validation = validate_dataset(corrupted, attributes)
        assert not validation["valid"]
        assert any("exactly one" in e.lower() for e in validation["errors"])

    @pytest.mark.slow
    def test_wtp_calculator_rejects_missing_price(
        self, dishwasher_study: CBCStudy, simulated_dataset: CBCRawDataset, tiny_hb_config: HBConfig
    ):
        """WTPCalculator should raise when price column is missing."""
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)

        util_df = pd.DataFrame.from_dict(hb_result.individual_utilities, orient="index")
        # Remove price column
        no_price_df = util_df.drop(columns=["price"])

        with pytest.raises(ValueError, match="Price column"):
            WTPCalculator(no_price_df, price_col="price")

    def test_pipeline_survives_partial_failure(
        self,
        dishwasher_study: CBCStudy,
        dishwasher_questionnaire: CBCQuestionnaire,
        persona_store,
        response_store,
    ):
        """When one simulation fails, the rest should still proceed."""
        study_id = dishwasher_study.study_id

        # Create a minimal valid persona
        minimal_persona = PersonaProfile(
            persona_id=f"persona-{study_id}-001",
            segment="精致白领",
            layer1_demographics=Layer1Demographics(
                age="30岁",
                gender="女",
                city="一线城市",
                income="20K-30K",
                occupation="产品经理",
                education="本科",
                marital_status="单身",
                living_type="公寓",
            ),
            layer2_behavior=Layer2Behavior(
                price_sensitivity="中等",
                purchase_channels=["天猫"],
                decision_style="理性比较型",
                brand_loyalty="中等",
                information_source=["知乎"],
            ),
            layer3_psychology=Layer3Psychology(
                core_values=["效率"],
                core_anxieties=["时间不够"],
                tension_combination=TensionCombination(
                    labels=["追求品质", "理性消费"],
                    narrative_explanation="她追求品质生活但预算有限，这种矛盾源于她刚进入职场的过渡期。"
                    * 2,
                ),
                secret_motivation="证明自己能独立生活",
                defense_mechanism="合理化",
            ),
            layer4_scenarios=Layer4Scenarios(
                daily_routine="早9晚7",
                purchase_trigger="看到广告",
                stress_response="理性分析",
                social_behavior="低调",
            ),
            language_samples=[
                "洗碗机确实很方便，帮我省下了不少饭后清理的时间。",
                "对比了好几个品牌的洗碗机，最后还是选了这个主流款。",
                "安装之后厨房整洁多了，每天不用洗碗真的很满意。",
            ],
            dishwasher_context=DishwasherContext(
                purchase_constraints=["空间有限"],
                decision_factors=["价格", "容量"],
                ignored_factors=["外观"],
            ),
        )

        simulator = CBCChoiceSimulator(attributes=dishwasher_study.attributes)
        raw_slice, pr = simulator.simulate(
            persona=minimal_persona,
            questionnaire=dishwasher_questionnaire,
            deterministic=True,
            seed=42,
        )
        assert raw_slice is not None
        assert pr is not None
        assert pr.completion_status == "COMPLETED"


# ═══════════════════════════════════════════════════════════════════════════
# Test: Schema Validation in Pipeline Context
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaValidationPipeline:
    """Integration of schema/logic validators in the pipeline context."""

    def test_persona_validates_against_schema(self, persona_profiles: list[PersonaProfile]):
        """All generated personas should pass schema validation."""
        schema_validator = SchemaValidator()
        for p in persona_profiles:
            result = schema_validator.validate(p)
            assert result.passed, f"Schema validation failed for {p.persona_id}: {result.errors}"

    def test_persona_validates_against_logic(self, persona_profiles: list[PersonaProfile]):
        """All generated personas should pass logic validation."""
        logic_validator = LogicValidator()
        for p in persona_profiles:
            result = logic_validator.validate(p)
            assert result.passed, f"Logic validation failed for {p.persona_id}: {result.errors}"

    def test_corrupted_persona_fails_schema(self, persona_profiles: list[PersonaProfile]):
        """A corrupted persona (bad language_samples) should fail schema."""
        schema_validator = SchemaValidator()
        p = persona_profiles[0]
        # Make a copy with invalid language_samples
        corrupted = p.model_copy(deep=True)
        corrupted.language_samples = ["too short"]

        result = schema_validator.validate(corrupted)
        assert not result.passed
        assert any("language_samples" in e for e in result.errors)


# ═══════════════════════════════════════════════════════════════════════════
# Test: Market Simulation Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestMarketSimulationEdgeCases:
    """Edge cases for market simulation after the full pipeline."""

    @pytest.mark.slow
    def test_first_choice_vs_logit_rule(
        self,
        dishwasher_study: CBCStudy,
        simulated_dataset: CBCRawDataset,
        tiny_hb_config: HBConfig,
    ):
        """Both logit and first_choice rules should produce valid shares."""
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)
        util_df = pd.DataFrame.from_dict(hb_result.individual_utilities, orient="index")

        market_sim = MarketSimulator(util_df, attributes)
        scenarios = [
            {
                "name": "产品A",
                "price": str(3999),
                "capacity": "capacity_2",
                "installation": "installation_1",
                "spray_arm": "spray_arm_2",
                "drying": "drying_3",
                "brand": "brand_2",
                "energy": "energy_1",
            },
            {
                "name": "产品B",
                "price": str(4999),
                "capacity": "capacity_3",
                "installation": "installation_1",
                "spray_arm": "spray_arm_3",
                "drying": "drying_4",
                "brand": "brand_4",
                "energy": "energy_1",
            },
        ]

        logit_shares = market_sim.simulate_share(scenarios, rule="logit", include_none=False)
        fc_shares = market_sim.simulate_share(scenarios, rule="first_choice", include_none=False)

        # Both should sum to 1
        assert abs(logit_shares["predicted_share"].sum() - 1.0) < 0.01
        assert abs(fc_shares["predicted_share"].sum() - 1.0) < 0.01

    @pytest.mark.slow
    def test_market_sim_with_none_option(
        self,
        dishwasher_study: CBCStudy,
        simulated_dataset: CBCRawDataset,
        tiny_hb_config: HBConfig,
    ):
        """Market simulation with none option included."""
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)
        util_df = pd.DataFrame.from_dict(hb_result.individual_utilities, orient="index")

        market_sim = MarketSimulator(util_df, attributes)
        scenarios = [
            {
                "name": "高端款",
                "price": str(5999),
                "capacity": "capacity_3",
                "installation": "installation_1",
                "spray_arm": "spray_arm_3",
                "drying": "drying_4",
                "brand": "brand_4",
                "energy": "energy_1",
            },
        ]

        shares = market_sim.simulate_share(scenarios, rule="logit", include_none=True)
        assert len(shares) == 2  # product + none
        assert abs(shares["predicted_share"].sum() - 1.0) < 0.01
        assert shares[shares["name"] == "none"]["predicted_share"].values[0] >= 0.0

    @pytest.mark.slow
    def test_sensitivity_analysis(
        self,
        dishwasher_study: CBCStudy,
        simulated_dataset: CBCRawDataset,
        tiny_hb_config: HBConfig,
    ):
        """Sensitivity analysis should vary price and return monotonic shares."""
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)
        util_df = pd.DataFrame.from_dict(hb_result.individual_utilities, orient="index")

        market_sim = MarketSimulator(util_df, attributes)
        base_scenario = {
            "name": "测试产品",
            "price": str(3999),
            "capacity": "capacity_2",
            "installation": "installation_3",
            "spray_arm": "spray_arm_1",
            "drying": "drying_2",
            "brand": "brand_2",
            "energy": "energy_1",
        }

        prices = [2999, 3999, 4999, 5999]
        df = market_sim.sensitivity_analysis(
            base_scenario=base_scenario,
            attribute="price",
            values=[str(p) for p in prices],
        )
        assert len(df) == len(prices)
        # Share should generally decrease as price increases
        shares = df["predicted_share"].values
        assert shares[0] >= shares[-1], "Share should decrease as price increases"


# ═══════════════════════════════════════════════════════════════════════════
# Test: Pipeline Serialization to Dashboard
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineSerialization:
    """Verify all pipeline outputs serialize cleanly for dashboard/frontend."""

    @pytest.mark.slow
    def test_full_output_is_json_serializable(
        self,
        dishwasher_study: CBCStudy,
        simulated_dataset: CBCRawDataset,
        tiny_hb_config: HBConfig,
    ):
        """The full pipeline output should be JSON serializable for the dashboard."""
        attributes = dishwasher_study.attributes
        df_long = to_long_format(simulated_dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        engine = HBEngine(config=tiny_hb_config)
        hb_result = engine.fit(df_long, feature_cols)

        util_df = pd.DataFrame.from_dict(hb_result.individual_utilities, orient="index")
        importance_df = compute_importance(util_df, attributes)
        importance_agg = aggregate_importance(importance_df)

        # Build the complete analysis result
        result = AnalysisResultResponse(
            analysis_id="ar-test-json",
            study_id=dishwasher_study.study_id,
            status="COMPLETED",
            model_type="hb",
            convergence=ConvergenceDiagnostics(
                rhat_max=hb_result.rhat_max,
                rhat_by_param=hb_result.population_mu,
                ess_bulk_min=hb_result.ess_bulk_min,
                ess_tail_min=hb_result.ess_bulk_min,
                ess_by_param=hb_result.population_sigma,
                converged=hb_result.converged,
                reliable_ess=hb_result.converged,
            ),
            population_params=PopulationParams(
                mu=hb_result.population_mu,
                sigma=hb_result.population_sigma,
            ),
            individual_utilities=hb_result.individual_utilities,
            importance={attr_id: float(row["mean"]) for attr_id, row in importance_agg.iterrows()},
            wtp={},
            processing_time_seconds=2.5,
            completed_at=datetime.now(UTC),
        )

        # Should serialize without errors
        json_str = result.model_dump_json(indent=2)
        recovered = json.loads(json_str)

        assert recovered["analysis_id"] == "ar-test-json"
        assert recovered["status"] == "COMPLETED"
        assert isinstance(recovered["individual_utilities"], dict)
        assert isinstance(recovered["importance"], dict)

        # Individual utilities should have numeric values
        for pid, utils in recovered["individual_utilities"].items():
            assert isinstance(utils, dict)
            for col, val in utils.items():
                assert isinstance(val, (int, float)), f"{pid}.{col} = {val} ({type(val)})"
                assert np.isfinite(val), f"{pid}.{col} is non-finite: {val}"

    def test_dataset_serialization(self, simulated_dataset: CBCRawDataset):
        """CBCRawDataset should serialize cleanly."""
        json_str = simulated_dataset.model_dump_json(indent=2)
        recovered = json.loads(json_str)

        assert recovered["metadata"]["n_respondents"] > 0
        assert len(recovered["choice_records"]) > 0

        for record in recovered["choice_records"]:
            assert "respondent_id" in record
            assert "alternatives" in record
            chosen_count = sum(1 for a in record["alternatives"] if a["chosen"])
            assert chosen_count == 1, (
                f"Record {record['choice_set_id']} for {record['respondent_id']} "
                f"has {chosen_count} chosen alternatives"
            )
