"""Tests for the seven fairness hard rules (RULE-FAIR-001 ~ RULE-FAIR-007).

Each rule is embedded in the persona generation prompt and must be detectable
by BiasAuditor. A persona that violates any rule must receive a FAILED status.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

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
from aicbc.core.scoring.bias_auditor import BiasAuditor


def _make_base_persona(
    gender: str = "女",
    age: str = "28岁",
    city: str = "二线城市",
    income: str = "8-15万元",
    occupation: str = "教师",
    marital_status: str = "未婚",
) -> PersonaProfile:
    return PersonaProfile(
        persona_id="persona-fairness-001",
        segment="test",
        layer1_demographics=Layer1Demographics(
            age=age,
            gender=gender,
            city=city,
            income=income,
            occupation=occupation,
            education="本科",
            marital_status=marital_status,
            living_type="租房独居",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="中等敏感",
            purchase_channels=["电商平台", "线下商超"],
            decision_style="理性比较型",
            brand_loyalty="中等忠诚度",
            information_source=["社交媒体", "朋友推荐"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["家庭", "健康"],
            core_anxieties=["同辈压力"],
            tension_combination=TensionCombination(
                labels=["精打细算", "偶尔犒劳自己"],
                narrative_explanation="她平时习惯精打细算，把每一笔开支都记录在册，"
                "但遇到真正认同的事物时，也会允许自己偶尔犒劳一下。"
                "这种矛盾来自她对安全感的需要和对生活小确幸的渴望。",
            ),
            secret_motivation="希望通过消费获得社会认同",
            defense_mechanism="合理化——将非必要消费解释为对自己的奖励",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="工作日朝九晚六，周末居家休息",
            purchase_trigger="社交媒体种草或朋友推荐",
            stress_response="先列清单再做决定",
            social_behavior="线上活跃，线下选择性社交",
        ),
        language_samples=[
            "这个洗碗机真的好用吗？我看网上评价褒贬不一。",
            "价格倒是其次，主要是担心买回家后长辈操作起来不习惯。",
            "如果真能省出每天洗碗的时间，我觉得多花点钱也值得。",
        ],
        dishwasher_context=DishwasherContext(
            purchase_constraints=["厨房空间限制"],
            decision_factors=["价格", "品牌口碑"],
            ignored_factors=["外观设计"],
        ),
        generation_metadata=GenerationMetadata(),
    )


class TestFairnessHardRules:
    """Ensure each of the seven fairness rules is enforced by BiasAuditor."""

    def test_rule_fair_001_gender_decision_ability(self) -> None:
        """Gender must not be causally linked to decision-making ability."""
        persona = _make_base_persona(gender="女")
        persona.layer2_behavior.decision_style = (
            "女性天生感性消费，只看外观和颜值，容易被种草，不关注参数"
        )

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "gender" for f in result.findings)

    def test_rule_fair_002_ethnicity_behavior(self) -> None:
        """Ethnicity must not be linked to consumption behavior or brand preference."""
        persona = _make_base_persona()
        persona.layer3_psychology.secret_motivation = (
            "少数民族传统保守，消费习惯特殊，不会买这种现代家电"
        )

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "ethnicity" for f in result.findings)

    def test_rule_fair_003_region_consumption_power(self) -> None:
        """City tier must not be bound to consumption power."""
        persona = _make_base_persona(city="县城")
        persona.layer1_demographics.income = "3万元以下"
        persona.layer2_behavior.price_sensitivity = "低收入所以只看最便宜的"

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "region" for f in result.findings)

    def test_rule_fair_004_age_tech_acceptance(self) -> None:
        """Age must not be inversely linked to tech acceptance."""
        persona = _make_base_persona(age="65岁")
        persona.layer4_scenarios.daily_routine = "老年人不会用智能产品，科技恐惧，触屏都不会"

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "age" for f in result.findings)

    def test_rule_fair_005_occupation_taste(self) -> None:
        """Occupation must not be bound to social class or taste."""
        persona = _make_base_persona(occupation="工厂工人")
        persona.layer3_psychology.secret_motivation = "蓝领就是底层打工，没追求，混日子"

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category in ("occupation", "occupation-income") for f in result.findings)

    def test_rule_fair_006_income_price_sensitivity(self) -> None:
        """Income must not be linearly linked to price sensitivity."""
        persona = _make_base_persona(income="100万元以上")
        persona.layer2_behavior.price_sensitivity = (
            "高收入一定不在乎价格，只买最贵的，有钱人就是任性"
        )

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "income" for f in result.findings)

    def test_rule_fair_007_marital_family_role(self) -> None:
        """Marital status must not be linked to fixed family decision roles."""
        persona = _make_base_persona(marital_status="已婚，育有一子")
        persona.layer4_scenarios.purchase_trigger = "丈夫说了算，妻子只需要顾家好妻子"

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "marital-status" for f in result.findings)

    def test_fairness_compliant_persona_passes(self) -> None:
        """A neutral persona should not fail fairness audit."""
        persona = _make_base_persona()
        result = BiasAuditor().audit(persona)
        assert result.status in ("PASSED", "PENDING")
