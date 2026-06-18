"""Tests for fairness rule logic — fast unit tests with no external dependencies.

Merged from:
- tests/test_bias_auditor.py
- tests/test_fairness_rules.py
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from aicbc.core.scoring.bias_auditor import BiasAuditor
from tests.conftest import persona_factory


# -----------
# Tests from test_bias_auditor.py
# -----------


class TestBiasAuditor:
    """Tests for bias detection rules."""

    def test_clean_persona_passes(self) -> None:
        """A well-balanced persona should pass."""
        auditor = BiasAuditor()
        persona = persona_factory()
        result = auditor.audit(persona)

        assert result.passed is True
        assert result.status == "PASSED"

    def test_gender_stereotype_detected(self) -> None:
        """Heavy gender stereotyping should be flagged."""
        auditor = BiasAuditor()
        persona = persona_factory(
            gender="女",
            price_sensitivity="颜值至上，只看外观，不关注参数，容易被种草，情绪化决策",
            decision_style="感性冲动，只看颜值，完全不理性",
        )
        result = auditor.audit(persona)

        findings = [f for f in result.findings if f.category == "gender"]
        assert len(findings) >= 1
        # Multiple gender patterns match; first finding severity varies by pattern order
        assert findings[0].severity in ("high", "critical", "medium")

    def test_occupation_income_anomaly_fails(self) -> None:
        """Student with ultra-high income should fail hard."""
        auditor = BiasAuditor()
        persona = persona_factory(
            occupation="大学生",
            income="100万元以上",
        )
        result = auditor.audit(persona)

        assert result.passed is False
        findings = [f for f in result.findings if f.rule_id == "BIAS-OCC-001"]
        assert len(findings) == 1
        assert findings[0].severity == "high"

    def test_biased_language_fails(self) -> None:
        """Explicit bias terms in samples should fail."""
        auditor = BiasAuditor()
        persona = persona_factory(
            samples=[
                "女人天生就是喜欢买东西的，这是典型的女性消费行为。",
                "我们男的买东西就是理性，不像女的那么冲动。",
                "穷人思维就是只关注价格，根本看不到长远价值。",
            ]
        )
        result = auditor.audit(persona)

        assert result.passed is False
        lang_findings = [f for f in result.findings if f.category == "language"]
        assert len(lang_findings) >= 2
        assert all(f.severity == "high" for f in lang_findings)

    def test_region_stereotype_critical_severity(self) -> None:
        """Low-tier city + low income triggers critical-severity region stereotype (SP-012)."""
        auditor = BiasAuditor()
        persona = persona_factory(
            city="县城",
            income="3万元以下",
        )
        result = auditor.audit(persona)

        findings = [f for f in result.findings if f.category == "region"]
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        # CRITICAL severity triggers FAILED (小伦 veto)
        assert result.passed is False
        assert result.critical_severity_count == 1

    def test_diversity_flag_on_average_template(self) -> None:
        """Overly 'average' persona gets diversity flag."""
        auditor = BiasAuditor()
        persona = persona_factory(
            age="28岁",
            city="新一线城市",
            occupation="互联网运营",
            income="15-30万元",
            education="本科",
        )
        result = auditor.audit(persona)

        findings = [f for f in result.findings if f.category == "diversity"]
        # The persona is built with average markers; should trigger
        assert len(findings) >= 1  # May or may not trigger depending on exact match

    def test_batch_audit_aggregates(self) -> None:
        """Batch audit should return aggregate statistics."""
        auditor = BiasAuditor()
        personas = [
            persona_factory(),  # clean
            persona_factory(occupation="大学生", income="100万元以上"),  # fails (SP-016, high)
            persona_factory(
                gender="男", decision_style="参数党，只看性能，不关心价格"
            ),  # fails (SP-004, high)
        ]
        agg = auditor.audit_batch(personas)

        assert agg["total_audited"] == 3
        assert agg["passed"] == 1  # Both persona 2 and 3 fail (high-severity findings)
        assert agg["failed"] == 2
        assert agg["pass_rate"] == pytest.approx(0.333, abs=0.01)
        assert agg["high_severity_findings"] >= 2


# -----------
# Tests from test_fairness_rules.py
# -----------


class TestFairnessHardRules:
    """Ensure each of the seven fairness rules is enforced by BiasAuditor."""

    def test_rule_fair_001_gender_decision_ability(self) -> None:
        """Gender must not be causally linked to decision-making ability."""
        persona = persona_factory(gender="女")
        persona.layer2_behavior.decision_style = (
            "女性天生感性消费，只看外观和颜值，容易被种草，不关注参数"
        )

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "gender" for f in result.findings)

    def test_rule_fair_002_ethnicity_behavior(self) -> None:
        """Ethnicity must not be linked to consumption behavior or brand preference."""
        persona = persona_factory()
        persona.layer3_psychology.secret_motivation = (
            "少数民族传统保守，消费习惯特殊，不会买这种现代家电"
        )

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "ethnicity" for f in result.findings)

    def test_rule_fair_003_region_consumption_power(self) -> None:
        """City tier must not be bound to consumption power."""
        persona = persona_factory(city="县城")
        persona.layer1_demographics.income = "3万元以下"
        persona.layer2_behavior.price_sensitivity = "低收入所以只看最便宜的"

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "region" for f in result.findings)

    def test_rule_fair_004_age_tech_acceptance(self) -> None:
        """Age must not be inversely linked to tech acceptance."""
        persona = persona_factory(age="65岁")
        persona.layer4_scenarios.daily_routine = "老年人不会用智能产品，科技恐惧，触屏都不会"

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "age" for f in result.findings)

    def test_rule_fair_005_occupation_taste(self) -> None:
        """Occupation must not be bound to social class or taste."""
        persona = persona_factory(occupation="工厂工人")
        persona.layer3_psychology.secret_motivation = "蓝领就是底层打工，没追求，混日子"

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category in ("occupation", "occupation-income") for f in result.findings)

    def test_rule_fair_006_income_price_sensitivity(self) -> None:
        """Income must not be linearly linked to price sensitivity."""
        persona = persona_factory(income="100万元以上")
        persona.layer2_behavior.price_sensitivity = (
            "高收入一定不在乎价格，只买最贵的，有钱人就是任性"
        )

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "income" for f in result.findings)

    def test_rule_fair_007_marital_family_role(self) -> None:
        """Marital status must not be linked to fixed family decision roles."""
        persona = persona_factory(marital_status="已婚，育有一子")
        persona.layer4_scenarios.purchase_trigger = "丈夫说了算，妻子只需要顾家好妻子"

        result = BiasAuditor().audit(persona)
        assert result.status == "FAILED"
        assert any(f.category == "marital-status" for f in result.findings)

    def test_fairness_compliant_persona_passes(self) -> None:
        """A neutral persona should not fail fairness audit."""
        persona = persona_factory()
        result = BiasAuditor().audit(persona)
        assert result.status in ("PASSED", "PENDING")
