"""Tests for LanguageSampleGenerator."""

from unittest.mock import MagicMock

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
from aicbc.generators.language_sample_generator import LanguageSampleGenerator

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
            decision_style="拖延比较型",
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
            daily_routine="",
            purchase_trigger="",
            stress_response="",
            social_behavior="",
        ),
        mini_biography=MiniBiography(
            past="大学时跟风买奢侈品导致债务危机。",
            present="现在做攻略再购买。",
            future="未来想减少冲动消费。",
        ),
        scene_reactions=SceneReactions(
            under_pressure="压力大时加购但不结算",
            friend_recommendation="先问缺点",
            flash_sale_limited="设闹钟但常错过",
            found_cheaper_elsewhere="后悔想退换",
            product_fault_after_sales="先查攻略再联系售后",
        ),
        language_samples=[
            "洗碗机真的能省时间吗？我没仔细研究过这些东西。",
            "对比了三个品牌，感觉都差不多，懒得再看了。",
            "安装师傅说大概半小时，具体怎么装我也不太清楚。",
        ],
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def test_generator_returns_three_samples() -> None:
    """Generator should return exactly 3 samples parsed from LLM JSON."""
    fake_response = MagicMock()
    fake_response.content = (
        '{\n'
        '  "language_samples": [\n'
        '    "洗碗机真的能省时间吗？我没仔细研究过。",\n'
        '    "对比了三个品牌，感觉都差不多，懒得再看了。",\n'
        '    "安装师傅说大概半小时，具体怎么装我也不太清楚。"\n'
        '  ]\n'
        '}'
    )

    mock_llm = MagicMock()
    mock_llm.generate.return_value = fake_response

    gen = LanguageSampleGenerator(llm_client=mock_llm)
    samples = gen.generate(_make_persona())

    assert len(samples) == 3
    assert all(20 <= len(s) <= 60 for s in samples)


def test_generator_falls_back_on_llm_failure() -> None:
    """Generator returns defaults when LLM fails."""
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("API error")

    gen = LanguageSampleGenerator(llm_client=mock_llm)
    samples = gen.generate(_make_persona())

    assert len(samples) == 3
    assert all(20 <= len(s) <= 60 for s in samples)


def test_generator_falls_back_on_invalid_count() -> None:
    """Generator returns defaults when LLM returns wrong number of samples."""
    fake_response = MagicMock()
    fake_response.content = '{"language_samples": ["只有一条"]}'

    mock_llm = MagicMock()
    mock_llm.generate.return_value = fake_response

    gen = LanguageSampleGenerator(llm_client=mock_llm)
    samples = gen.generate(_make_persona())

    assert len(samples) == 3
    assert all(20 <= len(s) <= 60 for s in samples)
