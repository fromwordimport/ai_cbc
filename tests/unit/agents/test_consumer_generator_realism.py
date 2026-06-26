"""Tests for ConsumerGeneratorAgent realism correction logic."""

import pytest

from aicbc.agents.consumer_generator import ConsumerGeneratorAgent
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
from aicbc.core.validators.plausibility_models import PlausibilityFinding

pytestmark = pytest.mark.unit


def _make_profile() -> PersonaProfile:
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
            price_sensitivity="中等敏感",
            purchase_channels=["京东"],
            decision_style="理性比较型",
            brand_loyalty="中等",
            information_source=["小红书"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["高收入", "极简主义"],
                narrative_explanation="她年收入四十万却坚持极简生活，每笔消费都要反复确认是否真的需要，这种矛盾让她在买与不买之间不断拉锯。",
            ),
            secret_motivation="",
            defense_mechanism="合理化",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早7点起床",
            purchase_trigger="",
            stress_response="",
            social_behavior="",
        ),
        mini_biography=MiniBiography(
            past="大学时的一次具体事件改变了她的消费观念",
            present="现在她每天忙于工作还要兼顾家庭责任",
            future="未来她担心大额支出会影响生活质量",
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


def test_should_correct_triggers_on_hard_plausibility_failure() -> None:
    """Hard plausibility failure must trigger correction."""
    agent = ConsumerGeneratorAgent()
    evaluation = {
        "authenticity_score": 10,
        "authenticity_passed": True,
        "has_tension": True,
        "narrative_ok": True,
        "plausibility_hard_failed": True,
        "plausibility_findings": [
            PlausibilityFinding(rule_id="PLA-001", severity="hard", message="宿舍")
        ],
        "narrative_under_explained": False,
    }
    should, feedback = agent._should_correct(evaluation)
    assert should is True
    assert "PLA-001" in feedback


def test_should_correct_triggers_on_narrative_under_explained() -> None:
    """Narrative under-explained must trigger correction."""
    agent = ConsumerGeneratorAgent()
    evaluation = {
        "authenticity_score": 10,
        "authenticity_passed": True,
        "has_tension": True,
        "narrative_ok": True,
        "plausibility_hard_failed": False,
        "plausibility_findings": [],
        "narrative_under_explained": True,
        "narrative_unexplained_tags": ["参数党", "高敏感"],
    }
    should, feedback = agent._should_correct(evaluation)
    assert should is True
    assert "参数党" in feedback


def test_should_correct_triggers_on_severe_authenticity() -> None:
    """Authenticity score below 6 must trigger correction."""
    agent = ConsumerGeneratorAgent()
    evaluation = {
        "authenticity_score": 5,
        "authenticity_passed": False,
        "has_tension": True,
        "narrative_ok": True,
        "plausibility_hard_failed": False,
        "plausibility_findings": [],
        "narrative_under_explained": False,
    }
    should, feedback = agent._should_correct(evaluation)
    assert should is True
    assert "5" in feedback


def test_should_not_correct_when_all_gates_pass() -> None:
    """No correction when all gates pass."""
    agent = ConsumerGeneratorAgent()
    evaluation = {
        "authenticity_score": 12,
        "authenticity_passed": True,
        "has_tension": True,
        "narrative_ok": True,
        "plausibility_hard_failed": False,
        "plausibility_findings": [],
        "narrative_under_explained": False,
    }
    should, feedback = agent._should_correct(evaluation)
    assert should is False
    assert feedback == ""


def test_evaluate_includes_plausibility_and_narrative_keys() -> None:
    """_evaluate should return plausibility and narrative consistency keys."""
    agent = ConsumerGeneratorAgent()
    profile = _make_profile()

    result = agent._evaluate(profile)

    assert "plausibility_hard_failed" in result
    assert "plausibility_passed" in result
    assert "narrative_under_explained" in result
    assert "narrative_unexplained_tags" in result
