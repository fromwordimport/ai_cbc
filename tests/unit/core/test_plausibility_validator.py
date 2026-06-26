"""Tests for PlausibilityValidator."""

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
from aicbc.core.validators.plausibility_validator import PlausibilityValidator
from aicbc.core.validators.product_context_models import DerivedProductContext

pytestmark = pytest.mark.unit


def _make_persona(**overrides) -> PersonaProfile:
    base = {
        "persona_id": "persona-test-001",
        "segment": "测试群体",
        "layer1_demographics": Layer1Demographics(
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
        "layer2_behavior": Layer2Behavior(
            price_sensitivity="高敏感",
            purchase_channels=["拼多多", "食堂"],
            decision_style="拖延比较型",
            brand_loyalty="低",
            information_source=["同学推荐", "小红书"],
        ),
        "layer3_psychology": Layer3Psychology(
            core_values=["省钱", "方便"],
            core_anxieties=["同辈压力"],
            tension_combination=TensionCombination(
                labels=["省钱", "想偷懒"],
                narrative_explanation="他生活费有限，但经常因为想偷懒而点外卖，事后又后悔花钱。这种矛盾让他对能省力的家电既渴望又觉得不配。",
            ),
            secret_motivation="想让室友觉得自己生活有品质",
            defense_mechanism="合理化——把非必要消费说成投资",
        ),
        "layer4_scenarios": Layer4Scenarios(
            daily_routine="早8点上课，中午食堂，晚上宿舍打游戏",
            purchase_trigger="室友推荐",
            stress_response="焦虑时刷购物APP",
            social_behavior="宿舍群活跃",
        ),
        "language_samples": [
            "洗碗机真的好用吗？我其实没研究过这些东西。",
            "宿舍那么小，装了洗碗机也没地方放吧，真的不现实。",
            "要是毕业后自己租房住，我可能会认真考虑买一个。",
        ],
        "dishwasher_context": DishwasherContext(
            purchase_constraints=["厨房空间限制"],
            decision_factors=["价格", "品牌"],
            ignored_factors=["外观设计"],
        ),
        "generation_metadata": GenerationMetadata(),
    }
    base.update(overrides)
    return PersonaProfile(**base)


def test_student_dorm_with_dishwasher_need_is_hard_failure() -> None:
    """A student in a dorm who is marked as considering a dishwasher must fail hard."""
    persona = _make_persona()
    derived = DerivedProductContext(
        eligibility="actively_considering",
        reason="roommate recommended",
        dishwasher_context=persona.dishwasher_context,
    )
    validator = PlausibilityValidator()
    result = validator.validate(persona, derived)

    assert result.hard_failed is True
    assert result.passed is False
    assert any(f.rule_id == "PLA-001" for f in result.findings)


def test_student_dorm_without_need_passes() -> None:
    """A student in a dorm with not_applicable eligibility should pass."""
    persona = _make_persona()
    derived = DerivedProductContext(
        eligibility="not_applicable",
        reason="无独立厨房，无法安装",
        dishwasher_context=persona.dishwasher_context,
    )
    validator = PlausibilityValidator()
    result = validator.validate(persona, derived)

    assert result.hard_failed is False
    assert result.passed is True


def test_low_income_active_considering_fails_hard() -> None:
    """A very low-income persona actively considering a dishwasher must fail hard."""
    persona = _make_persona(
        layer1_demographics=Layer1Demographics(
            age="22岁",
            gender="女",
            city="三线城市",
            income="3万元以下",
            occupation="兼职店员",
            education="大专",
            marital_status="未婚",
            living_type="与人合租",
            life_stage="初入职场",
        ),
    )
    derived = DerivedProductContext(
        eligibility="actively_considering",
        reason="想省力",
        dishwasher_context=persona.dishwasher_context,
    )
    validator = PlausibilityValidator()
    result = validator.validate(persona, derived)

    assert result.hard_failed is True
    assert any(f.rule_id == "PLA-002" for f in result.findings)
