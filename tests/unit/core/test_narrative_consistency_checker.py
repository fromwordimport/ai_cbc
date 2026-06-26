"""Tests for NarrativeConsistencyChecker."""

import pytest

from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    MiniBiography,
    PersonaProfile,
    SceneReactions,
    TensionCombination,
)
from aicbc.core.validators.narrative_consistency_checker import NarrativeConsistencyChecker

pytestmark = pytest.mark.unit


def _make_persona(mini_bio_past: str = "") -> PersonaProfile:
    return PersonaProfile(
        persona_id="persona-test-001",
        segment="测试群体",
        layer1_demographics=Layer1Demographics(
            age="28岁",
            gender="女",
            city="新一线城市",
            income="15-30万元",
            occupation="互联网产品经理",
            education="本科",
            marital_status="已婚无孩",
            living_type="自有住房（89㎡）",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="高敏感",
            purchase_channels=["京东"],
            decision_style="参数党",
            brand_loyalty="中等",
            information_source=["知乎"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["高收入", "极简主义"],
                narrative_explanation="她年收入四十万却坚持极简生活，每笔消费都要反复确认是否真的需要，这种矛盾让她在买与不买之间不断拉锯。",
            ),
            secret_motivation="",
            defense_mechanism="",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="",
            purchase_trigger="",
            stress_response="",
            social_behavior="",
        ),
        mini_biography=MiniBiography(
            past=mini_bio_past or "大学时一次具体事件改变了她的消费观。",
            present="现在经常研究参数再购买。",
            future="未来想减少冲动消费。",
        ),
        scene_reactions=SceneReactions(
            under_pressure="",
            friend_recommendation="",
            flash_sale_limited="",
            found_cheaper_elsewhere="",
            product_fault_after_sales="",
        ),
        language_samples=["a" * 20, "b" * 20, "c" * 20],
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def test_unexplained_decision_style_is_flagged() -> None:
    """If '参数党' is not explained in the biography, it should be flagged."""
    persona = _make_persona(mini_bio_past="她从小就喜欢买东西，从不研究参数。")
    checker = NarrativeConsistencyChecker()
    result = checker.check(persona)

    assert "参数党" in result.unexplained_tags or result.contradiction_score > 0


def test_explained_decision_style_passes() -> None:
    """If all key tags appear in the biography, nothing is unexplained."""
    persona = _make_persona(
        mini_bio_past=(
            "大学时她开始研究参数再买东西，从此成了参数党，"
            "她对价格一直保持高敏感，加上自己高收入却坚持极简主义，"
            "每笔消费都要反复权衡。"
        ),
    )
    checker = NarrativeConsistencyChecker()
    result = checker.check(persona)

    assert "参数党" not in result.unexplained_tags
    assert result.contradiction_score == 0.0


def test_missing_biography_returns_full_contradiction() -> None:
    """If mini_biography is None, the checker reports a missing biography."""
    persona = _make_persona()
    persona.mini_biography = None
    checker = NarrativeConsistencyChecker()
    result = checker.check(persona)

    assert result.contradiction_score == 1.0
    assert "mini_biography_missing" in result.unexplained_tags
