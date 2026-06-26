"""Tests for ProductContextDeriver."""

from unittest.mock import MagicMock

import pytest

from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    PersonaProfile,
    TensionCombination,
)
from aicbc.core.validators.product_context_deriver import ProductContextDeriver
from aicbc.llm.client import LLMClient, LLMResponse, Provider

pytestmark = pytest.mark.unit


def _make_student_dorm_persona() -> PersonaProfile:
    return PersonaProfile(
        persona_id="persona-student-001",
        segment="学生-宿舍",
        layer1_demographics=Layer1Demographics(
            age="20岁",
            gender="男",
            city="二线城市",
            income="3-8万元",
            occupation="大学生",
            education="本科",
            marital_status="未婚",
            living_type="学校宿舍",
            life_stage="学生",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="高敏感",
            purchase_channels=["拼多多"],
            decision_style="拖延比较型",
            brand_loyalty="低",
            information_source=["同学推荐"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["省钱"],
            core_anxieties=["同辈压力"],
            tension_combination=TensionCombination(
                labels=["省钱", "想偷懒"],
                narrative_explanation="他生活费有限，但经常因为想偷懒而点外卖，事后又后悔花钱。这种矛盾让他对能省力的家电既渴望又觉得不配。",
            ),
            secret_motivation="",
            defense_mechanism="",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早8点上课，晚10点回宿舍",
            purchase_trigger="",
            stress_response="",
            social_behavior="",
        ),
        language_samples=["a" * 20, "b" * 20, "c" * 20],
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def _make_married_homeowner_persona() -> PersonaProfile:
    return PersonaProfile(
        persona_id="persona-family-001",
        segment="已婚-自有住房",
        layer1_demographics=Layer1Demographics(
            age="35岁",
            gender="女",
            city="一线城市",
            income="20-35万元",
            occupation="产品经理",
            education="硕士",
            marital_status="已婚有孩",
            living_type="自有住房",
            life_stage="养育幼儿",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="中敏感",
            purchase_channels=["京东", "天猫"],
            decision_style="参数党",
            brand_loyalty="中",
            information_source=["评测视频", "朋友推荐"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率", "家庭"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["效率", "省钱"],
                narrative_explanation="她希望用洗碗机这样的科技产品把家务时间省出来陪孩子，但又担心买回家吃灰，所以每次大额消费都要仔细算一笔长期账才肯安心下单。",
            ),
            secret_motivation="",
            defense_mechanism="",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="通勤上班，晚上陪孩子，周末大扫除",
            purchase_trigger="",
            stress_response="",
            social_behavior="",
        ),
        language_samples=["a" * 20, "b" * 20, "c" * 20],
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def test_student_dorm_returns_not_applicable() -> None:
    """Physical constraints should short-circuit LLM for impossible cases."""
    deriver = ProductContextDeriver()
    result = deriver.derive(_make_student_dorm_persona())

    assert result.eligibility == "not_applicable"
    assert "宿舍" in result.reason or "独立厨房" in result.reason


def test_shared_rental_without_kitchen_returns_not_applicable() -> None:
    """A shared rental without independent kitchen should be not_applicable."""
    persona = _make_student_dorm_persona()
    persona.layer1_demographics.living_type = "合租房"
    persona.layer1_demographics.life_stage = "初入职场"

    deriver = ProductContextDeriver()
    result = deriver.derive(persona)

    assert result.eligibility == "not_applicable"


def test_homeowner_uses_llm_and_parses_response() -> None:
    """For plausible cases the deriver asks the LLM and parses the JSON response."""
    mock_response = LLMResponse(
        content='{"eligibility": "actively_considering", "reason": "有独立厨房且时间宝贵", "dishwasher_context": {"purchase_constraints": ["厨房空间"], "decision_factors": ["容量", "烘干效果"], "ignored_factors": ["外观设计"]}}',
        model="deepseek-v4-flash",
        provider=Provider.DEEPSEEK,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.0,
        latency_seconds=0.5,
    )
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.generate.return_value = mock_response

    deriver = ProductContextDeriver(llm_client=mock_llm)
    result = deriver.derive(_make_married_homeowner_persona())

    assert result.eligibility == "actively_considering"
    assert "厨房" in result.dishwasher_context.purchase_constraints[0]
    mock_llm.generate.assert_called_once()


def test_llm_failure_defaults_to_not_applicable() -> None:
    """If the LLM call fails, the deriver defaults to not_applicable."""
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.generate.side_effect = RuntimeError("API error")

    deriver = ProductContextDeriver(llm_client=mock_llm)
    result = deriver.derive(_make_married_homeowner_persona())

    assert result.eligibility == "not_applicable"
    assert "推导失败" in result.reason
