"""BiasAuditor — detect stereotypical correlations in generated personas.

Flags associations between protected attributes (gender, region, etc.)
and behavioural traits that may reflect model bias rather than true
population diversity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aicbc.core.models.persona import PersonaProfile

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class BiasFinding:
    """A single detected bias instance."""

    rule_id: str
    category: str  # e.g. "gender", "region", "occupation-income"
    severity: str  # "high" | "medium" | "low"
    description: str


@dataclass
class BiasAuditResult:
    """Complete bias audit result."""

    status: str  # "PASSED" | "FAILED" | "PENDING"
    findings: list[BiasFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "PASSED"

    @property
    def high_severity_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------


class BiasAuditor:
    """Audit PersonaProfile for systematic bias patterns.

    Rules are heuristic-based and designed to catch the most common
    LLM-generation biases in Chinese consumer personas.
    """

    # Gender → behaviour stereotypes
    GENDER_BEHAVIOUR_STEREOTYPES: dict[str, list[str]] = {
        "女": [
            "感性消费", "冲动消费", "颜值至上", "只看外观",
            "不关注参数", "容易被种草", "情绪化决策",
        ],
        "男": [
            "理性消费", "参数党", "只看性能", "不关心价格",
            "技术专家", "不做功课",
        ],
    }

    # Region → income stereotypes
    REGION_INCOME_STEREOTYPES: dict[str, list[str]] = {
        "县城": ["低收入", "节俭", "3万元以下", "价格敏感"],
        "乡镇": ["低收入", "节俭", "3万元以下", "价格敏感"],
        "三四线": ["低消费", "保守", "不重视品质"],
    }

    # Occupation → unlikely high-income combinations
    OCCUPATION_UNLIKELY_HIGH_INCOME: dict[str, list[str]] = {
        "学生": ["30-50万元", "50-100万元", "100万元以上", "月收入30K+"],
        "退休": ["30-50万元", "50-100万元", "100万元以上", "月收入30K+"],
        "自由职业": ["100万元以上"],
    }

    # Bias terms in language samples (should not appear)
    BIASED_TERMS: list[str] = [
        "男人就应该", "女人天生", "典型的男性", "典型的女性",
        "我们男的", "我们女的", "男的不懂", "女的不会",
        "穷人思维", "富人思维", "乡下人", "土包子",
    ]

    def audit(self, persona: PersonaProfile) -> BiasAuditResult:
        """Run all bias detection rules and return result."""
        findings: list[BiasFinding] = []

        findings.extend(self._check_gender_stereotypes(persona))
        findings.extend(self._check_region_income_stereotypes(persona))
        findings.extend(self._check_occupation_income_anomaly(persona))
        findings.extend(self._check_language_bias_terms(persona))
        findings.extend(self._check_demographic_diversity(persona))

        # Determine overall status
        high_count = sum(1 for f in findings if f.severity == "high")
        medium_count = sum(1 for f in findings if f.severity == "medium")

        if high_count > 0 or medium_count > 1:
            status = "FAILED"
        elif len(findings) > 0:
            status = "PASSED"  # Minor findings don't fail
        else:
            status = "PASSED"

        return BiasAuditResult(status=status, findings=findings)

    # ------------------------------------------------------------------
    # Rule 1: Gender stereotypes
    # ------------------------------------------------------------------

    def _check_gender_stereotypes(self, persona: PersonaProfile) -> list[BiasFinding]:
        """Flag if gender is stereotypically correlated with behaviour."""
        findings: list[BiasFinding] = []
        gender = persona.layer1_demographics.gender
        l2 = persona.layer2_behavior
        l3 = persona.layer3_psychology

        if gender not in self.GENDER_BEHAVIOUR_STEREOTYPES:
            return findings

        stereotypes = self.GENDER_BEHAVIOUR_STEREOTYPES[gender]
        text_to_check = " ".join([
            l2.price_sensitivity,
            l2.decision_style,
            l2.brand_loyalty,
            l3.secret_motivation,
            l3.defense_mechanism,
        ]).lower()

        matched = [s for s in stereotypes if s in text_to_check]
        if len(matched) >= 3:
            findings.append(BiasFinding(
                rule_id="BIAS-GEN-001",
                category="gender",
                severity="medium",
                description=f"性别'{gender}'与{len(matched)}项刻板行为强关联: {', '.join(matched[:3])}",
            ))
        elif len(matched) >= 1:
            findings.append(BiasFinding(
                rule_id="BIAS-GEN-002",
                category="gender",
                severity="low",
                description=f"性别'{gender}'与刻板行为有关联: {', '.join(matched)}",
            ))

        return findings

    # ------------------------------------------------------------------
    # Rule 2: Region → income stereotypes
    # ------------------------------------------------------------------

    def _check_region_income_stereotypes(self, persona: PersonaProfile) -> list[BiasFinding]:
        """Flag if low-tier cities are automatically assigned low income."""
        findings: list[BiasFinding] = []
        city = persona.layer1_demographics.city
        income = persona.layer1_demographics.income

        for region_key, income_markers in self.REGION_INCOME_STEREOTYPES.items():
            if region_key in city and any(m in income for m in income_markers):
                # It's OK for low-tier cities to have low income, but flag
                # if it's *automatically* paired without nuance
                # We use a simple heuristic: if income is the very lowest bracket
                findings.append(BiasFinding(
                        rule_id="BIAS-REG-001",
                        category="region",
                        severity="low",
                        description=f"城市'{city}'自动匹配最低收入档位'{income}'，可能缺乏多样性",
                    ))

        return findings

    # ------------------------------------------------------------------
    # Rule 3: Occupation → unrealistic income
    # ------------------------------------------------------------------

    def _check_occupation_income_anomaly(self, persona: PersonaProfile) -> list[BiasFinding]:
        """Flag occupation-income combinations that are extremely unlikely."""
        findings: list[BiasFinding] = []
        occupation = persona.layer1_demographics.occupation
        income = persona.layer1_demographics.income

        for occ_key, unlikely_incomes in self.OCCUPATION_UNLIKELY_HIGH_INCOME.items():
            if occ_key in occupation and any(inc in income for inc in unlikely_incomes):
                findings.append(BiasFinding(
                        rule_id="BIAS-OCC-001",
                        category="occupation-income",
                        severity="high",
                        description=f"职业'{occupation}'与收入'{income}'组合极不常见，可能存在模型偏见",
                    ))

        return findings

    # ------------------------------------------------------------------
    # Rule 4: Biased language in samples
    # ------------------------------------------------------------------

    def _check_language_bias_terms(self, persona: PersonaProfile) -> list[BiasFinding]:
        """Flag explicit bias terms in language samples."""
        findings: list[BiasFinding] = []
        samples_text = " ".join(persona.language_samples)

        for term in self.BIASED_TERMS:
            if term in samples_text:
                findings.append(BiasFinding(
                    rule_id="BIAS-LANG-001",
                    category="language",
                    severity="high",
                    description=f"语言样本中出现偏见术语: '{term}'",
                ))

        return findings

    # ------------------------------------------------------------------
    # Rule 5: Demographic diversity
    # ------------------------------------------------------------------

    def _check_demographic_diversity(self, persona: PersonaProfile) -> list[BiasFinding]:
        """Check for overly 'average' demographics that lack diversity."""
        findings: list[BiasFinding] = []
        l1 = persona.layer1_demographics

        # Check for the 'average urban professional' template
        average_markers = 0
        if "25-34岁" in l1.age or "28岁" in l1.age:
            average_markers += 1
        if "本科" in l1.education:
            average_markers += 1
        if "互联网" in l1.occupation or "白领" in l1.occupation:
            average_markers += 1
        if "新一线" in l1.city or "一线" in l1.city:
            average_markers += 1
        if "15-30万元" in l1.income:
            average_markers += 1

        if average_markers >= 4:
            findings.append(BiasFinding(
                rule_id="BIAS-DIV-001",
                category="diversity",
                severity="low",
                description=f"画像呈现高度'平均化'特征({average_markers}/5项)，可能反映模型输出集中在典型模板",
            ))

        return findings

    # ------------------------------------------------------------------
    # Batch audit helper
    # ------------------------------------------------------------------

    def audit_batch(self, personas: list[PersonaProfile]) -> dict[str, Any]:
        """Audit a batch and report aggregate statistics."""
        results = [self.audit(p) for p in personas]

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed

        all_findings: list[BiasFinding] = []
        for r in results:
            all_findings.extend(r.findings)

        # Count by category
        category_counts: dict[str, int] = {}
        for f in all_findings:
            category_counts[f.category] = category_counts.get(f.category, 0) + 1

        return {
            "total_audited": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total, 3) if total else 0,
            "total_findings": len(all_findings),
            "findings_by_category": category_counts,
            "high_severity_findings": sum(1 for f in all_findings if f.severity == "high"),
        }
