"""Tests for AuthenticityScorer realism dimensions."""

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
from aicbc.core.scoring.authenticity_scorer import AuthenticityScorer
from aicbc.core.validators.narrative_consistency_checker import NarrativeConsistencyResult
from aicbc.core.validators.plausibility_models import PlausibilityFinding, PlausibilityResult

pytestmark = pytest.mark.unit


def _make_persona() -> PersonaProfile:
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
            defense_mechanism="",
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


def test_plausibility_dimension_zero_on_hard_failure() -> None:
    """Plausibility dimension should be 0 when hard rule fails."""
    persona = _make_persona()
    scorer = AuthenticityScorer()
    plausibility = PlausibilityResult(
        passed=False,
        hard_failed=True,
        findings=[PlausibilityFinding(rule_id="PLA-001", severity="hard", message="")],
    )
    result = scorer.score(persona, plausibility_result=plausibility)
    dim = next(d for d in result.dimensions if d.name == "情境合理性")
    assert dim.score == 0


def test_narrative_depth_dimension_two_when_mini_bio_present() -> None:
    """Narrative depth should be 2 when mini-biography has all three parts."""
    persona = _make_persona()
    scorer = AuthenticityScorer()
    result = scorer.score(persona)
    dim = next(d for d in result.dimensions if d.name == "叙事深度")
    assert dim.score == 2


def test_narrative_depth_zero_when_mini_bio_missing() -> None:
    """Narrative depth should be 0 when mini-biography is missing."""
    persona = _make_persona()
    persona.mini_biography = None
    scorer = AuthenticityScorer()
    result = scorer.score(persona)
    dim = next(d for d in result.dimensions if d.name == "叙事深度")
    assert dim.score == 0


def test_scorer_accepts_narrative_consistency_result() -> None:
    """Scorer should accept an optional NarrativeConsistencyResult without error."""
    persona = _make_persona()
    scorer = AuthenticityScorer()
    consistency = NarrativeConsistencyResult(
        unexplained_tags=["理性比较型"],
        contradiction_score=0.25,
    )
    result = scorer.score(persona, narrative_consistency_result=consistency)
    assert len(result.dimensions) == 9
