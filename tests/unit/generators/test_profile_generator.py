"""Unit tests for ProfileGenerator.

All LLM calls are mocked — no real API requests are made.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from aicbc.core.models.persona import (
    DishwasherContext,
    PersonaProfile,
)
from aicbc.core.models.seed_config import SeedConfig, TensionPair
from aicbc.generators.profile_generator import (
    _LAYER_FALLBACKS,
    ProfileGenerationError,
    ProfileGenerator,
)
from aicbc.llm.client import LLMResponse, Provider

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_config() -> SeedConfig:
    """Return a deterministic seed config for testing."""
    return SeedConfig(
        life_stage="初入职场单身",
        anxieties=["同辈压力", "职业倦怠"],
        income_bracket="8-15万元",
        city_tier="新一线城市",
        tension_score=0.45,
        tension_pairs=[
            TensionPair(
                tag_a="躺平/低欲望",
                tag_b="内卷/奋斗",
                tension_value=0.85,
                narrative="想卷卷不动，想躺躺不平的45度青年",
            )
        ],
        extra_tags={"生活态度": "躺平/低欲望", "消费观念": "理性比价/精明型"},
    )


@pytest.fixture
def mock_llm_response_factory():
    """Factory for creating mock LLMResponse objects."""

    def _make(content: str | dict[str, Any], model: str = "claude-sonnet-4-6") -> LLMResponse:
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

    return _make


@pytest.fixture
def mock_llm_client(mock_llm_response_factory):
    """Return a mock LLMClient with configurable responses."""
    client = MagicMock()
    client.generate.return_value = mock_llm_response_factory({})
    return client


@pytest.fixture
def profile_generator(mock_llm_client) -> ProfileGenerator:
    """Return a ProfileGenerator using the mock LLM client."""
    return ProfileGenerator(llm_client=mock_llm_client)


# ---------------------------------------------------------------------------
# Helpers: layer response builders
# ---------------------------------------------------------------------------


def _layer1_response() -> dict[str, Any]:
    return {
        "age": "26-30岁",
        "gender": "女",
        "city": "杭州（新一线城市）",
        "income": "8-15万元",
        "occupation": "互联网运营",
        "education": "本科",
        "marital_status": "未婚，独居",
        "living_type": "租房（一居室，45㎡）",
    }


def _layer2_response() -> dict[str, Any]:
    return {
        "price_sensitivity": "对日常消费品价格敏感，对提升生活品质的耐用品愿意适度溢价",
        "purchase_channels": ["淘宝/天猫", "拼多多", "小红书商城"],
        "decision_style": "口碑党+参数党混合，购买前必看测评和用户真实反馈",
        "brand_loyalty": "对信任品牌有较高复购率，但愿意尝试新锐品牌",
        "information_source": ["小红书", "豆瓣", "B站测评", "朋友推荐"],
    }


def _layer3_response() -> dict[str, Any]:
    return {
        "core_values": ["自我实现", "性价比", "生活品质"],
        "core_anxieties": ["同辈压力", "职业倦怠", "身份迷茫"],
        "tension_combination": {
            "labels": ["躺平/低欲望", "内卷/奋斗"],
            "narrative_explanation": "她白天在公司努力表现争取晋升，晚上回家却只想躺平刷剧。这种矛盾源于她对'成功'定义的困惑——既渴望社会认可，又怀疑这种认可的真正价值。",
        },
        "secret_motivation": "表面上说买洗碗机是为了节省时间，真实动机是想通过拥有'精致生活'的符号来缓解同辈压力",
        "defense_mechanism": "合理化——把非必要消费解释为'投资自己的生活品质'",
    }


def _layer4_response() -> dict[str, Any]:
    return {
        "daily_routine": "早8点起床，地铁通勤40分钟，晚7点到家，周末探店或宅家追剧",
        "purchase_trigger": "被小红书'提升幸福感的小家电'种草，叠加双11促销刺激",
        "stress_response": "焦虑时刷购物APP加购，但经常冷静后删除，形成'加购-删除'循环",
        "social_behavior": "朋友圈极少发消费内容，但在私域社群活跃，经常分享购物攻略",
    }


def _auxiliary_response() -> dict[str, Any]:
    return {
        "language_samples": [
            "这个洗碗机真的好用吗？我看网上评价褒贬不一，有点纠结要不要入手。",
            "价格倒是其次，主要是怕买了之后厨房放不下，放着积灰就浪费了。",
            "如果真能省出每天洗碗的时间，我觉得多花点钱也值得考虑一下吧。",
        ],
        "dishwasher_context": {
            "purchase_constraints": ["厨房空间小", "租房不便安装"],
            "decision_factors": ["价格", "品牌口碑", "清洁效果", "安装便利性"],
            "ignored_factors": ["外观设计", "智能互联"],
        },
    }


def _narrative_core_response() -> dict[str, Any]:
    return {
        "mini_biography": {
            "past": "大学时跟风买奢侈品导致债务危机，形成先研究再购买的习惯。",
            "present": "工作日晚上做双十一攻略，周末逛奥特莱斯。",
            "future": "担心教育支出挤占品质生活预算。",
        },
        "scene_reactions": {
            "under_pressure": "压力大时加购但不结算",
            "friend_recommendation": "先问价格和缺点",
            "flash_sale_limited": "设闹钟但常错过",
            "found_cheaper_elsewhere": "纠结要不要退货重买",
            "product_fault_after_sales": "先小红书查攻略再联系客服",
        },
    }


def _product_context_response() -> dict[str, Any]:
    return {
        "eligibility": "latent_need",
        "reason": "租房空间小，安装不便",
        "dishwasher_context": {
            "purchase_constraints": ["厨房空间小", "租房不便安装"],
            "decision_factors": ["价格", "品牌口碑", "清洁效果", "安装便利性"],
            "ignored_factors": ["外观设计", "智能互联"],
        },
    }


def _language_samples_response() -> dict[str, Any]:
    return {
        "language_samples": [
            "这个洗碗机真的好用吗？我看网上评价褒贬不一，有点纠结要不要入手。",
            "价格倒是其次，主要是怕买了之后厨房放不下，放着积灰就浪费了。",
            "如果真能省出每天洗碗的时间，我觉得多花点钱也值得考虑一下吧。",
        ],
    }


# ---------------------------------------------------------------------------
# Tests: initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    """Tests for ProfileGenerator construction."""

    def test_uses_provided_llm_client(self, mock_llm_client):
        """Should store the provided LLM client."""
        gen = ProfileGenerator(llm_client=mock_llm_client)
        assert gen._llm is mock_llm_client

    def test_loads_default_template(self, mock_llm_client):
        """Should load the default prompt template from disk."""
        gen = ProfileGenerator(llm_client=mock_llm_client)
        assert "{{life_stage}}" in gen._template
        assert "{{anxieties}}" in gen._template

    def test_raises_on_missing_template(self, mock_llm_client):
        """Should raise ProfileGenerationError when template file is missing."""
        with pytest.raises(ProfileGenerationError):
            ProfileGenerator(
                llm_client=mock_llm_client,
                prompt_template_path="/nonexistent/path/template.txt",
            )


# ---------------------------------------------------------------------------
# Tests: normal generation flow
# ---------------------------------------------------------------------------


class TestNormalGeneration:
    """Tests for the happy-path layer-by-layer generation."""

    def test_generates_complete_profile(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """All layers + auxiliary should produce a valid PersonaProfile."""
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-001", seed_config)

        assert isinstance(result, PersonaProfile)
        assert result.persona_id == "persona-test-001"
        assert result.segment == "初入职场单身-新一线城市"
        assert result.layer1_demographics.age == "26-30岁"
        assert (
            result.layer2_behavior.decision_style
            == "口碑党+参数党混合，购买前必看测评和用户真实反馈"
        )
        assert result.layer3_psychology.secret_motivation != ""
        assert result.layer4_scenarios.daily_routine != ""
        assert len(result.language_samples) == 3
        assert result.dishwasher_context.purchase_constraints == ["厨房空间小", "租房不便安装"]
        assert result.generation_metadata.cost_cny > 0

    def test_layer_context_passed_sequentially(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """Each layer prompt should include previously generated layer data."""
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        profile_generator.generate("persona-test-002", seed_config)

        calls = profile_generator._llm.generate.call_args_list
        # Layer 2 prompt should reference Layer 1 data
        layer2_prompt = calls[1].kwargs["messages"][1]["content"]
        assert "26-30岁" in layer2_prompt or "杭州" in layer2_prompt

        # Layer 3 prompt should reference Layer 1 and Layer 2 data
        layer3_prompt = calls[2].kwargs["messages"][1]["content"]
        assert "口碑党" in layer3_prompt or "参数党" in layer3_prompt or "26-30岁" in layer3_prompt

        # Layer 4 prompt should reference all previous layers
        layer4_prompt = calls[3].kwargs["messages"][1]["content"]
        assert "躺平" in layer4_prompt or "内卷" in layer4_prompt or "同辈压力" in layer4_prompt

    def test_json_mode_enabled_for_all_calls(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """Every LLM call should request JSON mode."""
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        profile_generator.generate("persona-test-003", seed_config)

        for call in profile_generator._llm.generate.call_args_list:
            assert call.kwargs.get("json_mode") is True


# ---------------------------------------------------------------------------
# Tests: fallback / error handling
# ---------------------------------------------------------------------------


class TestFallbackHandling:
    """Tests for per-layer fallback when LLM or parsing fails."""

    def test_uses_fallback_on_llm_failure(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """If LLM raises an exception for a layer, fallback defaults should be used."""
        profile_generator._llm.generate.side_effect = [
            RuntimeError("LLM API error"),  # Layer 1 fails
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-004", seed_config)

        # Layer 1 should use fallback
        assert result.layer1_demographics.age == _LAYER_FALLBACKS[1]["age"]
        # Other layers should be normal
        assert result.layer2_behavior.decision_style == _layer2_response()["decision_style"]

    def test_uses_fallback_on_json_parse_error(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """If LLM returns invalid JSON, fallback defaults should be used."""
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory("not valid json {["),  # Layer 2 bad JSON
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-005", seed_config)

        assert result.layer1_demographics.age == "26-30岁"
        assert result.layer2_behavior.decision_style == _LAYER_FALLBACKS[2]["decision_style"]
        assert result.layer3_psychology.secret_motivation == _layer3_response()["secret_motivation"]

    def test_uses_fallback_on_missing_fields(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """If LLM JSON is missing required fields, fallback should fill them."""
        incomplete_layer1 = {"age": "26-30岁", "gender": "女"}  # Missing most fields
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(incomplete_layer1),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-006", seed_config)

        assert result.layer1_demographics.age == "26-30岁"
        assert result.layer1_demographics.gender == "女"
        # Missing fields should come from fallback
        assert result.layer1_demographics.occupation == _LAYER_FALLBACKS[1]["occupation"]
        assert result.layer1_demographics.education == _LAYER_FALLBACKS[1]["education"]

    def test_generation_continues_after_single_layer_failure(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """A failure in one layer should not abort the entire generation."""
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            RuntimeError("Layer 2 failed"),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-007", seed_config)

        assert isinstance(result, PersonaProfile)
        assert result.layer1_demographics is not None
        assert result.layer3_psychology is not None
        assert result.layer4_scenarios is not None

    def test_auxiliary_fallback_on_failure(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """If post-layer generation fails, defaults are used for those components."""
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            RuntimeError("Narrative core failed"),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-008", seed_config)

        assert len(result.language_samples) == 3
        assert all(20 <= len(s) <= 60 for s in result.language_samples)
        assert isinstance(result.dishwasher_context, DishwasherContext)
        assert len(result.dishwasher_context.decision_factors) > 0


# ---------------------------------------------------------------------------
# Tests: prompt construction
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    """Tests for the internal prompt builder."""

    def test_prompt_contains_seed_info(self, profile_generator, seed_config):
        """Prompt should include seed config values."""
        prompt = profile_generator._build_prompt(1, seed_config, {})
        assert seed_config.life_stage in prompt
        assert seed_config.income_bracket in prompt
        assert seed_config.city_tier in prompt
        assert seed_config.anxieties[0] in prompt

    def test_prompt_contains_json_schema(self, profile_generator, seed_config):
        """Prompt should include the JSON schema for the target layer."""
        for layer_num in range(1, 5):
            prompt = profile_generator._build_prompt(layer_num, seed_config, {})
            assert (
                "age" in prompt
                or "price_sensitivity" in prompt
                or "core_values" in prompt
                or "daily_routine" in prompt
            )

    def test_prompt_contains_previous_layers(self, profile_generator, seed_config):
        """Prompt for layer N should include layers 1..N-1."""
        previous = {
            1: {"age": "30岁", "gender": "男"},
            2: {"decision_style": "冲动型"},
        }
        prompt = profile_generator._build_prompt(3, seed_config, previous)
        assert "30岁" in prompt
        assert "冲动型" in prompt

    def test_prompt_contains_tension_pairs(self, profile_generator, seed_config):
        """Prompt should include tension pair narratives."""
        prompt = profile_generator._build_prompt(1, seed_config, {})
        assert "躺平/低欲望" in prompt
        assert "内卷/奋斗" in prompt
        assert "45度青年" in prompt


# ---------------------------------------------------------------------------
# Tests: output validation
# ---------------------------------------------------------------------------


class TestOutputValidation:
    """Tests for validating generated PersonaProfile structure."""

    def test_language_samples_length_validation(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """Language samples must be exactly 3 items and 20-60 chars each."""
        bad_aux = {
            "language_samples": ["短", "也短", "还是短"],
            "dishwasher_context": _auxiliary_response()["dishwasher_context"],
        }
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(bad_aux),
        ]

        result = profile_generator.generate("persona-test-009", seed_config)

        # Should fall back to defaults because samples are too short
        assert len(result.language_samples) == 3
        assert all(20 <= len(s) <= 60 for s in result.language_samples)

    def test_profile_is_serializable(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """Generated profile should be convertible to a dict."""
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-010", seed_config)
        d = result.to_dict()

        assert d["persona_id"] == "persona-test-010"
        assert "layer1_demographics" in d
        assert "layer2_behavior" in d
        assert "layer3_psychology" in d
        assert "layer4_scenarios" in d
        assert "language_samples" in d
        assert "dishwasher_context" in d

    def test_authenticity_score_default(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """Authenticity score should be None until explicitly scored."""
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-011", seed_config)
        assert result.authenticity_score is None

    def test_bias_audit_status_default(
        self, profile_generator, seed_config, mock_llm_response_factory
    ):
        """Bias audit status should default to PENDING."""
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-012", seed_config)
        assert result.bias_audit_status == "PENDING"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_tension_pairs(self, profile_generator, mock_llm_response_factory):
        """Seed with no tension pairs should still generate successfully."""
        seed = SeedConfig(
            life_stage="学生",
            anxieties=["同辈压力"],
            income_bracket="3万元以下",
            city_tier="二线城市",
            tension_score=0.0,
            tension_pairs=[],
        )
        profile_generator._llm.generate.side_effect = [
            mock_llm_response_factory(_layer1_response()),
            mock_llm_response_factory(_layer2_response()),
            mock_llm_response_factory(_layer3_response()),
            mock_llm_response_factory(_layer4_response()),
            mock_llm_response_factory(_narrative_core_response()),
            mock_llm_response_factory(_product_context_response()),
            mock_llm_response_factory(_language_samples_response()),
        ]

        result = profile_generator.generate("persona-test-013", seed)
        assert isinstance(result, PersonaProfile)

    def test_all_layers_fallback(self, profile_generator, seed_config):
        """If all LLM calls fail, the profile should still be generated with all fallbacks."""
        profile_generator._llm.generate.side_effect = RuntimeError("Total failure")

        result = profile_generator.generate("persona-test-014", seed_config)

        assert isinstance(result, PersonaProfile)
        assert result.layer1_demographics.age == _LAYER_FALLBACKS[1]["age"]
        assert result.layer2_behavior.decision_style == _LAYER_FALLBACKS[2]["decision_style"]
        assert (
            result.layer3_psychology.secret_motivation == _LAYER_FALLBACKS[3]["secret_motivation"]
        )
        assert result.layer4_scenarios.daily_routine == _LAYER_FALLBACKS[4]["daily_routine"]
        assert len(result.language_samples) == 3
        assert isinstance(result.dishwasher_context, DishwasherContext)
