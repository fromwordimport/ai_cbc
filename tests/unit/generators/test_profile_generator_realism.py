"""Tests for ProfileGenerator realism integration."""

from unittest.mock import MagicMock

import pytest

from aicbc.core.models.seed_config import SeedConfig
from aicbc.generators.profile_generator import ProfileGenerator

pytestmark = pytest.mark.unit


def test_profile_has_narrative_core_and_derived_context() -> None:
    """ProfileGenerator should populate mini_biography, scene_reactions, and dishwasher_context."""
    responses = [
        # Layer 1
        '{"age": "20岁", "gender": "男", "city": "二线城市", "income": "3-8万元", '
        '"occupation": "大学生", "education": "本科", "marital_status": "未婚", "living_type": "学校宿舍"}',
        # Layer 2
        '{"price_sensitivity": "高敏感", "purchase_channels": ["拼多多"], "decision_style": "拖延比较型", '
        '"brand_loyalty": "低", "information_source": ["同学推荐"]}',
        # Layer 3
        '{"core_values": ["省钱"], "core_anxieties": ["同辈压力"], '
        '"tension_combination": {"labels": ["省钱", "想偷懒"], "narrative_explanation": "他生活费有限，但经常因为想偷懒而点外卖，事后又后悔花钱。这种矛盾让他对能省力的家电既渴望又觉得不配。"}, '
        '"secret_motivation": "", "defense_mechanism": ""}',
        # Layer 4
        '{"daily_routine": "早8点上课", "purchase_trigger": "", "stress_response": "", "social_behavior": ""}',
        # Narrative core
        '{"mini_biography": {"past": "小学时看到母亲放弃洗碗机", "present": "现在食堂吃饭", "future": "毕业后考虑"}, '
        '"scene_reactions": {"under_pressure": "", "friend_recommendation": "", "flash_sale_limited": "", '
        '"found_cheaper_elsewhere": "", "product_fault_after_sales": ""}}',
        # Product context (not reached for dorm; kept for completeness)
        '{"eligibility": "not_applicable", "reason": "宿舍", "dishwasher_context": {"purchase_constraints": [], '
        '"decision_factors": [], "ignored_factors": []}}',
        # Language samples
        '{"language_samples": ["洗碗机真的好用吗？我没研究过这些东西。", "宿舍那么小，装了也没地方放吧，真的不现实。", '
        '"要是毕业后自己租房，我可能会认真考虑买一个。"]}',
    ]

    response_iter = iter(responses)

    def _fake_generate(*args, **kwargs):
        resp = MagicMock()
        resp.content = next(response_iter)
        resp.estimated_cost_usd = 0.0
        resp.model = "mock"
        return resp

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = _fake_generate

    gen = ProfileGenerator(llm_client=mock_llm)
    seed = SeedConfig(
        life_stage="学生",
        anxieties=["同辈压力"],
        income_bracket="3-8万元",
        city_tier="二线城市",
        tension_score=0.5,
        tension_pairs=[],
        extra_tags={},
    )
    profile = gen.generate("persona-study-0001", seed)

    assert profile.mini_biography is not None
    assert profile.mini_biography.past
    assert profile.scene_reactions is not None
    assert len(profile.language_samples) == 3
    assert profile.dishwasher_context is not None
