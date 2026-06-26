"""Tests for NarrativeCoreGenerator."""

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
from aicbc.generators.narrative_core_generator import NarrativeCoreGenerator

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
            purchase_channels=["京东", "天猫"],
            decision_style="理性比较型",
            brand_loyalty="中等",
            information_source=["小红书", "知乎"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率", "品质"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["精致品质", "凑单退单"],
                narrative_explanation="她追求精致生活，却总在凑单后退掉不需要的商品，这种矛盾让她对每一笔开销都既渴望又内疚，所以她对能提升生活品质的家电总是反复权衡。",
            ),
            secret_motivation="用科技产品证明品味",
            defense_mechanism="合理化——把消费解释为投资",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早7点起床，通勤40分钟，晚7点到家",
            purchase_trigger="被小红书种草",
            stress_response="焦虑时刷购物APP",
            social_behavior="朋友圈少发",
        ),
        language_samples=["a" * 20, "b" * 20, "c" * 20],
        dishwasher_context=DishwasherContext(),
        generation_metadata=GenerationMetadata(),
    )


def test_generator_returns_mini_biography_and_scene_reactions() -> None:
    """Generator should parse LLM output into MiniBiography + SceneReactions."""
    fake_response = MagicMock()
    fake_response.content = (
        '{\n'
        '  "mini_biography": {\n'
        '    "past": "大学时跟风买奢侈品导致债务危机，形成先研究再购买的习惯。",\n'
        '    "present": "工作日晚上做双十一攻略，周末逛奥特莱斯。",\n'
        '    "future": "担心教育支出挤占品质生活预算。"\n'
        '  },\n'
        '  "scene_reactions": {\n'
        '    "under_pressure": "压力大时加购但不结算",\n'
        '    "friend_recommendation": "先问价格和缺点",\n'
        '    "flash_sale_limited": "设闹钟但常错过",\n'
        '    "found_cheaper_elsewhere": "纠结要不要退货重买",\n'
        '    "product_fault_after_sales": "先小红书查攻略再联系客服"\n'
        '  }\n'
        '}'
    )

    mock_llm = MagicMock()
    mock_llm.generate.return_value = fake_response

    gen = NarrativeCoreGenerator(llm_client=mock_llm)
    mini_bio, scenes = gen.generate(_make_persona())

    assert mini_bio.past
    assert mini_bio.present
    assert mini_bio.future
    assert scenes.under_pressure
    assert scenes.friend_recommendation
    mock_llm.generate.assert_called_once()


def test_generator_defaults_on_llm_failure() -> None:
    """Generator should return defaults when LLM call fails."""
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("API error")

    gen = NarrativeCoreGenerator(llm_client=mock_llm)
    mini_bio, scenes = gen.generate(_make_persona())

    assert mini_bio.past
    assert scenes.under_pressure
    mock_llm.generate.assert_called_once()
