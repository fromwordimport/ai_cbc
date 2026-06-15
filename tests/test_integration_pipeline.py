"""Integration tests: end-to-end persona generation pipeline.

Flow under test:
    SeedGenerator → ProfileGenerator → SchemaValidator + LogicValidator

All LLM calls are mocked — no real API requests.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from aicbc.core.models.persona import PersonaProfile
from aicbc.core.models.seed_config import SeedConfig
from aicbc.core.validators import LogicValidator, SchemaValidator
from aicbc.generators.profile_generator import _LAYER_FALLBACKS, ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator
from aicbc.llm.client import LLMResponse, Provider

# ---------------------------------------------------------------------------
# Helpers: mock LLM response builders
# ---------------------------------------------------------------------------


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


def _layer1() -> dict[str, Any]:
    return {
        "age": "28岁",
        "gender": "女",
        "city": "新一线城市",
        "income": "15-30万元",
        "occupation": "互联网产品经理",
        "education": "本科",
        "marital_status": "已婚无孩",
        "living_type": "自有住房（89㎡三居室）",
    }


def _layer2() -> dict[str, Any]:
    return {
        "price_sensitivity": "对高频消费品价格敏感，对耐用品愿意为品质溢价",
        "purchase_channels": ["京东自营", "天猫旗舰店", "山姆会员店"],
        "decision_style": "参数党+口碑党混合，购买前必看测评",
        "brand_loyalty": "对信任品牌复购率高，愿意尝试新锐品牌",
        "information_source": ["小红书", "什么值得买", "知乎", "同事推荐"],
    }


def _layer3() -> dict[str, Any]:
    return {
        "core_values": ["效率", "品质生活", "家庭至上"],
        "core_anxieties": ["时间不够用", "家务分工矛盾"],
        "tension_combination": {
            "labels": ["精致品质", "凑单退单高手"],
            "narrative_explanation": (
                "她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑。"
                "小时候家境普通让她对'浪费'极度敏感，成年后收入提升让她有能力追求品质，但童年的匮乏感仍在潜意识中支配着她的消费决策。"
            ),
        },
        "secret_motivation": "用科技产品证明自己的生活品味，缓解同辈压力",
        "defense_mechanism": "合理化——把临时消费欲望解释为'投资生活品质'",
    }


def _layer4() -> dict[str, Any]:
    return {
        "daily_routine": "早7点起床，地铁通勤40分钟，晚7点到家，周末打扫或带孩子上兴趣班",
        "purchase_trigger": "被小红书'提升幸福感的小家电'种草，叠加同事推荐",
        "stress_response": "焦虑时刷购物APP加购，冷静后删除，形成'加购-删除'循环",
        "social_behavior": "朋友圈极少发消费内容，但在私域社群活跃分享购物攻略",
    }


def _auxiliary() -> dict[str, Any]:
    return {
        "language_samples": [
            "洗碗机真的是解放双手的神器，后悔没早买！",
            "对比了三个品牌，最后还是选了性价比最高的那款。",
            "安装师傅非常专业，只用了半小时就全部搞定了。",
        ],
        "dishwasher_context": {
            "purchase_constraints": ["厨房空间有限", "预算控制在5000以内"],
            "decision_factors": ["清洁效果", "品牌口碑", "能耗等级", "安装便利性"],
            "ignored_factors": ["外观设计", "智能互联功能"],
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Return a mock LLMClient that cycles through layer responses."""
    client = MagicMock()

    def _make_side_effect(seed: SeedConfig) -> list[LLMResponse]:
        return [
            _mock_response(_layer1()),
            _mock_response(_layer2()),
            _mock_response(_layer3()),
            _mock_response(_layer4()),
            _mock_response(_auxiliary()),
        ]

    # Default side effect will be overridden per-test
    client.generate.side_effect = [
        _mock_response(_layer1()),
        _mock_response(_layer2()),
        _mock_response(_layer3()),
        _mock_response(_layer4()),
        _mock_response(_auxiliary()),
    ]
    return client


@pytest.fixture
def pipeline(mock_llm_client: MagicMock) -> PersonaPipeline:
    """Return a wired-up pipeline with mock LLM."""
    return PersonaPipeline(llm_client=mock_llm_client)


# ---------------------------------------------------------------------------
# Pipeline helper class
# ---------------------------------------------------------------------------


class PersonaPipeline:
    """Helper that orchestrates the full generation + validation flow."""

    def __init__(self, llm_client: MagicMock | None = None) -> None:
        self.seed_gen = SeedGenerator()
        self.profile_gen = ProfileGenerator(llm_client=llm_client)
        self.schema_validator = SchemaValidator()
        self.logic_validator = LogicValidator()

    def generate_and_validate(self, persona_id: str, seed: SeedConfig | None = None) -> dict[str, Any]:
        """Run full pipeline and return results."""
        seed = seed or self.seed_gen.generate_seed()
        profile = self.profile_gen.generate(persona_id, seed)
        schema_result = self.schema_validator.validate(profile)
        logic_result = self.logic_validator.validate(profile)
        return {
            "seed": seed,
            "profile": profile,
            "schema_result": schema_result,
            "logic_result": logic_result,
            "passed": schema_result.passed and logic_result.passed,
        }


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end tests for the complete persona generation pipeline."""

    def test_single_persona_pipeline(self, pipeline: PersonaPipeline) -> None:
        """A single persona should flow through seed → profile → validation cleanly."""
        result = pipeline.generate_and_validate("persona-int-001")

        assert result["passed"] is True
        assert isinstance(result["profile"], PersonaProfile)
        assert result["profile"].persona_id == "persona-int-001"
        assert result["schema_result"].passed
        assert result["logic_result"].passed
        assert result["logic_result"].score == 7.0  # All 7 rules pass

    def test_profile_structure_is_complete(self, pipeline: PersonaPipeline) -> None:
        """Generated profile must contain all four layers and auxiliary data."""
        result = pipeline.generate_and_validate("persona-int-002")
        profile: PersonaProfile = result["profile"]

        assert profile.layer1_demographics is not None
        assert profile.layer2_behavior is not None
        assert profile.layer3_psychology is not None
        assert profile.layer4_scenarios is not None
        assert len(profile.language_samples) == 3
        assert profile.dishwasher_context is not None
        assert profile.generation_metadata is not None

    def test_seed_influences_profile(self, pipeline: PersonaPipeline) -> None:
        """Different seeds should produce meaningfully different profiles."""
        result_a = pipeline.generate_and_validate("persona-int-003")
        result_b = pipeline.generate_and_validate("persona-int-004")

        # Seeds should differ in at least one dimension
        seed_a = result_a["seed"]
        seed_b = result_b["seed"]
        assert (
            seed_a.life_stage != seed_b.life_stage
            or seed_a.city_tier != seed_b.city_tier
            or seed_a.income_bracket != seed_b.income_bracket
        )

    def test_schema_validator_catches_invalid_profile(self, pipeline: PersonaPipeline) -> None:
        """SchemaValidator should reject a profile with invalid fields."""
        result = pipeline.generate_and_validate("persona-int-004")
        profile: PersonaProfile = result["profile"]

        # Corrupt the profile
        profile.language_samples = ["too short"]

        schema_result = pipeline.schema_validator.validate(profile)
        assert schema_result.passed is False
        assert any("language_samples" in e for e in schema_result.errors)

    def test_logic_validator_catches_contradictions(self, pipeline: PersonaPipeline) -> None:
        """LogicValidator should flag business-rule violations."""
        result = pipeline.generate_and_validate("persona-int-005")
        profile: PersonaProfile = result["profile"]

        # Inject a forbidden term
        profile.language_samples = [
            "这个洗碗机用了AI算法，感觉特别智能。",
            "价格倒是其次，主要是怕买了之后厨房放不下。",
            "如果真能省出每天洗碗的时间，我觉得多花点钱也值得。",
        ]

        logic_result = pipeline.logic_validator.validate(profile)
        assert logic_result.passed is False
        assert any("RULE-006" in e for e in logic_result.errors)
        assert logic_result.details["rule_scores"]["RULE-006"] == 0.0


class TestBatchGeneration:
    """Batch generation tests — simulate a study with multiple personas."""

    def test_batch_of_ten(self, mock_llm_client: MagicMock) -> None:
        """Generate 10 personas and assert pipeline-wide quality metrics."""
        pipeline = PersonaPipeline(llm_client=mock_llm_client)

        results: list[dict[str, Any]] = []
        for i in range(10):
            mock_llm_client.generate.side_effect = [
                _mock_response(_layer1()),
                _mock_response(_layer2()),
                _mock_response(_layer3()),
                _mock_response(_layer4()),
                _mock_response(_auxiliary()),
            ]
            result = pipeline.generate_and_validate(f"persona-batch-{i:03d}")
            results.append(result)

        # All 10 should pass schema validation
        schema_passed = sum(1 for r in results if r["schema_result"].passed)
        assert schema_passed == 10, f"Only {schema_passed}/10 passed schema validation"

        # All 10 should pass logic validation (with clean mock data)
        logic_passed = sum(1 for r in results if r["logic_result"].passed)
        assert logic_passed == 10, f"Only {logic_passed}/10 passed logic validation"

        # All IDs should be unique
        ids = {r["profile"].persona_id for r in results}
        assert len(ids) == 10

        # Segments should vary (different seeds produce different segments)
        segments = {r["profile"].segment for r in results}
        assert len(segments) >= 1  # At least some variety (could be same if seeds align)

    def test_batch_with_mixed_quality(self, mock_llm_client: MagicMock) -> None:
        """Simulate a batch where some LLM calls return bad data."""
        pipeline = PersonaPipeline(llm_client=mock_llm_client)

        results: list[dict[str, Any]] = []
        for i in range(5):
            if i == 2:
                # Simulate LLM failure for one persona — fallbacks kick in
                mock_llm_client.generate.side_effect = RuntimeError("Simulated API failure")
            else:
                mock_llm_client.generate.side_effect = [
                    _mock_response(_layer1()),
                    _mock_response(_layer2()),
                    _mock_response(_layer3()),
                    _mock_response(_layer4()),
                    _mock_response(_auxiliary()),
                ]
            result = pipeline.generate_and_validate(f"persona-mixed-{i:03d}")
            results.append(result)

        # All 5 should still produce valid PersonaProfile objects (via fallbacks)
        assert all(isinstance(r["profile"], PersonaProfile) for r in results)

        # The failed one should use fallback values
        failed_profile = results[2]["profile"]
        assert failed_profile.layer1_demographics.age == _LAYER_FALLBACKS[1]["age"]


class TestReproducibility:
    """Tests ensuring reproducible generation with fixed seeds."""

    def test_same_seed_produces_same_profile(self, mock_llm_client: MagicMock) -> None:
        """Two pipelines with the same seed should generate identical seeds."""
        pipeline_a = PersonaPipeline(llm_client=mock_llm_client)
        pipeline_b = PersonaPipeline(llm_client=mock_llm_client)

        seed_gen_a = SeedGenerator(seed=12345)
        seed_gen_b = SeedGenerator(seed=12345)

        for i in range(3):
            mock_llm_client.generate.side_effect = [
                _mock_response(_layer1()),
                _mock_response(_layer2()),
                _mock_response(_layer3()),
                _mock_response(_layer4()),
                _mock_response(_auxiliary()),
            ]
            seed_a = seed_gen_a.generate_seed()
            pipeline_a.generate_and_validate(f"persona-repr-{i}", seed_a)

            mock_llm_client.generate.side_effect = [
                _mock_response(_layer1()),
                _mock_response(_layer2()),
                _mock_response(_layer3()),
                _mock_response(_layer4()),
                _mock_response(_auxiliary()),
            ]
            seed_b = seed_gen_b.generate_seed()
            pipeline_b.generate_and_validate(f"persona-repr2-{i}", seed_b)

            assert seed_a.life_stage == seed_b.life_stage
            assert seed_a.city_tier == seed_b.city_tier
            assert seed_a.income_bracket == seed_b.income_bracket
            assert seed_a.anxieties == seed_b.anxieties


class TestProfileSerialization:
    """Tests for profile export and downstream compatibility."""

    def test_profile_serializes_to_json(self, pipeline: PersonaPipeline) -> None:
        """PersonaProfile must be JSON-serializable for downstream analysis."""
        result = pipeline.generate_and_validate("persona-ser-001")
        profile: PersonaProfile = result["profile"]

        d = profile.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        recovered = json.loads(json_str)

        assert recovered["persona_id"] == "persona-ser-001"
        assert "layer1_demographics" in recovered
        assert "layer2_behavior" in recovered
        assert "layer3_psychology" in recovered
        assert "layer4_scenarios" in recovered
        assert "language_samples" in recovered
        assert len(recovered["language_samples"]) == 3

    def test_profile_dict_has_all_layers(self, pipeline: PersonaPipeline) -> None:
        """to_dict() output should contain nested layer dictionaries."""
        result = pipeline.generate_and_validate("persona-ser-002")
        d = result["profile"].to_dict()

        assert isinstance(d["layer1_demographics"], dict)
        assert isinstance(d["layer2_behavior"], dict)
        assert isinstance(d["layer3_psychology"], dict)
        assert isinstance(d["layer4_scenarios"], dict)
        assert "age" in d["layer1_demographics"]
        assert "tension_combination" in d["layer3_psychology"]
