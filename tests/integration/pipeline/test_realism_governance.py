"""Integration test for realism governance end-to-end."""

from unittest.mock import MagicMock

import pytest

from aicbc.core.models.seed_config import SeedConfig
from aicbc.core.validators.plausibility_validator import PlausibilityValidator
from aicbc.core.validators.product_context_deriver import ProductContextDeriver
from aicbc.generators.profile_generator import ProfileGenerator

pytestmark = pytest.mark.integration


def test_student_dorm_profile_is_marked_not_applicable() -> None:
    """A student in a dorm must result in not_applicable dishwasher context."""
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
        # Language samples (product context short-circuits for dorm)
        '{"language_samples": ["洗碗机真的好用吗？我没研究过这些东西。", "宿舍那么小，装了也没地方放吧，真的不现实。", '
        '"要是毕业后自己租房，我可能会认真考虑买一个。"]}',
    ]

    call_iter = iter(responses)

    def _fake_generate(*args, **kwargs):
        resp = MagicMock()
        resp.content = next(call_iter)
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
    profile = gen.generate("persona-integration-0001", seed)

    # ProfileGenerator should derive not_applicable for student in dorm.
    assert profile.dishwasher_context.purchase_constraints == ["无独立厨房，无法安装"]

    validator = PlausibilityValidator()
    derived = ProductContextDeriver(llm_client=mock_llm).derive(profile)
    assert derived.eligibility == "not_applicable"
    result = validator.validate(profile, derived)
    assert result.hard_failed is False
    assert result.passed is True
