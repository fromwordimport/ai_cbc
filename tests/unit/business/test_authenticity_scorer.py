"""Tests for AuthenticityScorer."""

from __future__ import annotations

from typing import Any

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
from aicbc.core.scoring.authenticity_scorer import AuthenticityScorer

pytestmark = pytest.mark.unit


def _make_base_persona(**overrides: Any) -> PersonaProfile:
    """Helper to build a persona with sensible defaults."""
    base = {
        "persona_id": "persona-test-001",
        "segment": "测试群体",
        "layer1_demographics": Layer1Demographics(
            age="28岁",
            gender="女",
            city="新一线城市",
            income="15-30万元",
            occupation="互联网产品经理",
            education="本科",
            marital_status="已婚无孩",
            living_type="自有住房（89㎡）",
        ),
        "layer2_behavior": Layer2Behavior(
            price_sensitivity="中等敏感",
            purchase_channels=["京东", "天猫"],
            decision_style="理性比较型",
            brand_loyalty="中等",
            information_source=["小红书", "知乎"],
        ),
        "layer3_psychology": Layer3Psychology(
            core_values=["效率", "品质"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["精致品质", "凑单退单"],
                narrative_explanation=(
                    "她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑。"
                    "小时候家境普通让她对浪费极度敏感，成年后收入提升让她有能力追求品质。"
                ),
            ),
            secret_motivation="用科技产品证明品味",
            defense_mechanism="合理化——把消费解释为投资",
        ),
        "layer4_scenarios": Layer4Scenarios(
            daily_routine="早7点起床，通勤40分钟，晚7点到家，周末打扫",
            purchase_trigger="被小红书种草",
            stress_response="焦虑时刷购物APP",
            social_behavior="朋友圈少发，私域活跃",
        ),
        "language_samples": [
            "洗碗机真的是解放双手的神器吧，不过说实话有点纠结要不要推荐给别人呢。",
            "对比了三个品牌，最后懒得再看了，反正大概差不多就选了这个，其实心里也没底。",
            "安装师傅挺专业的吧，大概半小时搞定，具体怎么装的我也不太清楚，反正能洗碗就行。",
        ],
        "dishwasher_context": DishwasherContext(
            purchase_constraints=["厨房小"],
            decision_factors=["价格", "品牌"],
            ignored_factors=["外观"],
        ),
        "generation_metadata": GenerationMetadata(),
    }
    base.update(overrides)
    return PersonaProfile(**base)


class TestAuthenticityScorer:
    """Tests for the 9-dimension authenticity scorer."""

    def test_full_score_on_good_persona(self) -> None:
        """A well-crafted persona should score highly."""
        scorer = AuthenticityScorer()
        persona = _make_base_persona()
        result = scorer.score(persona)

        assert result.total_score >= 10  # Should pass
        assert result.passed is True
        assert result.grade in ("优秀", "良好")
        assert len(result.dimensions) == 9

    def test_each_dimension_has_score(self) -> None:
        """All 9 dimensions should produce scores."""
        scorer = AuthenticityScorer()
        persona = _make_base_persona()
        result = scorer.score(persona)

        names = [d.name for d in result.dimensions]
        assert "内在一致性" in names
        assert "情境敏感性" in names
        assert "认知有限性" in names
        assert "社会摩擦感" in names
        assert "时间延续性" in names
        assert "语言自然度" in names
        assert "知识边界感" in names
        assert "情境合理性" in names
        assert "叙事深度" in names

    def test_internal_consistency_zero_on_missing_narrative(self) -> None:
        """Missing tension narrative should score 0 on internal consistency."""
        scorer = AuthenticityScorer()
        persona = _make_base_persona(
            layer3_psychology=Layer3Psychology(
                core_values=["效率"],
                core_anxieties=["时间"],
                tension_combination=TensionCombination(
                    labels=["X标签", "Y标签"],
                    narrative_explanation="这是一个与标签X和Y完全无关的叙事解释，仅仅为了满足最小长度要求而写的内容，没有任何实际的心理学意义。",
                ),
                secret_motivation="测试",
                defense_mechanism="测试",
            )
        )
        result = scorer.score(persona)
        dim = next(d for d in result.dimensions if d.name == "内在一致性")
        assert dim.score == 0

    def test_language_naturalness_zero_on_jargon(self) -> None:
        """Marketing jargon should reduce language naturalness."""
        scorer = AuthenticityScorer()
        persona = _make_base_persona(
            language_samples=[
                "这个产品的用户体验很好，痛点解决得很到位。",
                "我们做了很多垂直领域的调研，抓手很准，闭环做得很好。",
                "性价比很高，转化漏斗设计得不错，用户体验极佳。",
            ]
        )
        result = scorer.score(persona)
        dim = next(d for d in result.dimensions if d.name == "语言自然度")
        assert dim.score == 0

    def test_cognitive_limitation_zero_on_perfect_rationality(self) -> None:
        """Perfect rationality patterns should score 0."""
        scorer = AuthenticityScorer()
        persona = _make_base_persona(
            language_samples=[
                "我用Excel做了全平台比价表，还仔细计算了NPV和IRR指标。",
                "精确到小数点后三位，每个参数都进行了详细的量化分析。",
                "制作了非常详细的对比表，涵盖了所有重要的技术维度。",
            ]
        )
        result = scorer.score(persona)
        dim = next(d for d in result.dimensions if d.name == "认知有限性")
        assert dim.score == 0

    def test_knowledge_boundary_high_on_uncertainty(self) -> None:
        """Uncertainty markers should improve knowledge-boundary score."""
        scorer = AuthenticityScorer()
        persona = _make_base_persona(
            language_samples=[
                "我不太清楚这个牌子到底怎么样，之前完全没有研究过。",
                "不知道实际效果好不好，可能要买了之后才能知道吧。",
                "听说这个品牌还不错，但我不太懂这些复杂的技术参数。",
            ]
        )
        result = scorer.score(persona)
        dim = next(d for d in result.dimensions if d.name == "知识边界感")
        assert dim.score == 2

    def test_social_friction_on_hesitation_markers(self) -> None:
        """Hesitation markers should improve social-friction score."""
        scorer = AuthenticityScorer()
        persona = _make_base_persona(
            language_samples=[
                "其实吧，我有点纠结到底要不要买这个东西呢。",
                "说实话，虽然心动但是特别怕买回来之后就闲置了。",
                "不过呢，价格确实有点贵，不好意思直接跟家里人说。",
            ]
        )
        result = scorer.score(persona)
        dim = next(d for d in result.dimensions if d.name == "社会摩擦感")
        assert dim.score == 2

    def test_temporal_continuity_matches_occupation(self) -> None:
        """Routine matching occupation should score well."""
        scorer = AuthenticityScorer()
        persona = _make_base_persona(
            layer1_demographics=Layer1Demographics(
                age="22岁",
                gender="女",
                city="二线",
                income="3-8万元",
                occupation="大学生",
                education="本科",
                marital_status="未婚",
                living_type="学校宿舍",
            ),
            layer4_scenarios=Layer4Scenarios(
                daily_routine="早8点上课，下午图书馆，晚上宿舍追剧",
                purchase_trigger="同学推荐",
                stress_response="焦虑时吃零食",
                social_behavior="宿舍群活跃",
            ),
        )
        result = scorer.score(persona)
        dim = next(d for d in result.dimensions if d.name == "时间延续性")
        assert dim.score == 2

    def test_fails_on_completely_artificial_persona(self) -> None:
        """A deliberately artificial persona should fail."""
        scorer = AuthenticityScorer()
        persona = _make_base_persona(
            layer3_psychology=Layer3Psychology(
                core_values=["效率"],
                core_anxieties=["时间"],
                tension_combination=TensionCombination(
                    labels=[],
                    narrative_explanation="这是一个故意设置的没有任何实质内容的叙事解释，仅仅为了满足最小长度要求而存在，完全不包含任何有效的信息内容。",
                ),
                secret_motivation="",
                defense_mechanism="",
            ),
            language_samples=[
                "本产品的用户体验极佳，痛点解决非常精准到位。",
                "通过垂直领域深度调研，抓手精准，全面赋能消费决策。",
                "性价比表现优异，转化漏斗设计形成了完整的闭环。",
            ],
            layer4_scenarios=Layer4Scenarios(
                daily_routine="",
                purchase_trigger="",
                stress_response="",
                social_behavior="",
            ),
        )
        result = scorer.score(persona)
        assert result.passed is False
        assert result.total_score < 6
