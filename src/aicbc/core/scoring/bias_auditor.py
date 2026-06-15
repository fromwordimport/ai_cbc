"""BiasAuditor — detect stereotypical correlations in generated personas.

Flags associations between protected attributes (gender, region, etc.)
and behavioural traits that may reflect model bias rather than true
population diversity.

v2.0 — Replaces 5 hardcoded keyword rules with a 24-pattern stereotype
library (stereotype_patterns.py) covering gender, age, region, occupation,
ethnicity, and income.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aicbc.core.models.persona import PersonaProfile
from aicbc.core.scoring.stereotype_patterns import STEREOTYPE_PATTERNS

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class BiasFinding:
    """A single detected bias instance."""

    rule_id: str
    category: str  # e.g. "gender", "region", "occupation-income"
    severity: str  # "critical" | "high" | "medium" | "low"
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

    @property
    def critical_severity_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")


# ---------------------------------------------------------------------------
# Legacy rule-id mapping (backward compatibility with tests)
# ---------------------------------------------------------------------------

# Categories that map to old BIAS-xxx rule IDs (for test compatibility).
# New categories (age, ethnicity, income) use the pattern's own SP-xxx id.
_CATEGORY_TO_OLD_RULE_PREFIX: dict[str, str] = {
    "gender": "BIAS-GEN",
    "region": "BIAS-REG",
    "occupation-income": "BIAS-OCC",
    "occupation": "BIAS-OCC",
    "language": "BIAS-LANG",
    "diversity": "BIAS-DIV",
}


def _make_rule_id(category: str, counter: int) -> str:
    """Generate a rule_id with backward-compatible naming."""
    prefix = _CATEGORY_TO_OLD_RULE_PREFIX.get(category)
    if prefix is not None:
        return f"{prefix}-{counter:03d}"
    # New categories use SP-xxx pattern id (handled by caller)
    return ""


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------


class BiasAuditor:
    """Audit PersonaProfile for systematic bias patterns.

    Uses a 24-pattern stereotype library loaded from stereotype_patterns.py
    plus explicit language-bias and demographic-diversity checks.
    """

    # Bias terms in language samples (should never appear)
    BIASED_TERMS: list[str] = [
        "男人就应该", "女人天生", "典型的男性", "典型的女性",
        "我们男的", "我们女的", "男的不懂", "女的不会",
        "穷人思维", "富人思维", "乡下人", "土包子",
    ]

    def __init__(self) -> None:
        self._patterns: list[dict] = STEREOTYPE_PATTERNS

    # ------------------------------------------------------------------
    # Main audit entry point
    # ------------------------------------------------------------------

    def audit(self, persona: PersonaProfile) -> BiasAuditResult:
        """Run all bias detection rules and return result."""
        findings: list[BiasFinding] = []

        findings.extend(self._check_stereotype_patterns(persona))
        findings.extend(self._check_language_bias_terms(persona))
        findings.extend(self._check_demographic_diversity(persona))

        # Determine overall status
        critical_count = sum(1 for f in findings if f.severity == "critical")
        high_count = sum(1 for f in findings if f.severity == "high")
        medium_count = sum(1 for f in findings if f.severity == "medium")

        if critical_count > 0:
            status = "FAILED"  # CRITICAL triggers 小伦 veto — batch must pause
        elif high_count > 0 or medium_count > 0:
            status = "FAILED"
        elif len(findings) > 0:
            status = "PASSED"  # Minor findings don't fail
        else:
            status = "PASSED"

        return BiasAuditResult(status=status, findings=findings)

    # ------------------------------------------------------------------
    # Unified stereotype pattern check (replaces 3 old hardcoded rules)
    # ------------------------------------------------------------------

    def _check_stereotype_patterns(
        self, persona: PersonaProfile
    ) -> list[BiasFinding]:
        """Iterate over the 24-pattern library and flag any matches.

        For each pattern:
        1. Check demographic constraints (if any)
        2. Build the relevant text corpus from persona fields
        3. Substring-match keywords against that corpus
        4. Create a BiasFinding on match

        Backward-compatible rule_ids are generated for categories that
        overlap with the old hardcoded rules.
        """
        findings: list[BiasFinding] = []
        # Per-category counters for backward-compatible rule_id generation
        cat_counters: dict[str, int] = {}

        l1 = persona.layer1_demographics
        l2 = persona.layer2_behavior
        l3 = persona.layer3_psychology
        l4 = persona.layer4_scenarios

        for pattern in self._patterns:
            # --- Step 1: demographic constraint check ---
            demo_match = pattern.get("demographic_match")
            if demo_match is not None:
                if not self._demographic_matches(persona, demo_match):
                    continue

            # --- Step 2: build text corpus based on match_fields ---
            match_fields = pattern.get("match_fields", [])
            text_corpus = self._build_text_corpus(
                persona, match_fields, pattern
            )

            # --- Step 3: keyword matching ---
            keywords = pattern.get("keywords_cn", [])
            matched = [kw for kw in keywords if kw in text_corpus]

            if not matched:
                continue

            # --- Step 4: increment counter and create finding ---
            cat = pattern["category"]
            cat_counters[cat] = cat_counters.get(cat, 0) + 1
            rule_id = self._get_or_generate_rule_id(pattern, cat_counters[cat])
            findings.append(BiasFinding(
                rule_id=rule_id,
                category=pattern["category"],
                severity=pattern["severity"],
                description=(
                    f"[{pattern['id']}] {pattern['description']}"
                    f" — 匹配关键词: {', '.join(matched[:3])}"
                ),
            ))

        return findings

    def _demographic_matches(
        self, persona: PersonaProfile, demo_match: dict
    ) -> bool:
        """Check if persona demographics satisfy the pattern's constraints."""
        l1 = persona.layer1_demographics

        # Simple exact field match
        for field, expected in demo_match.items():
            if field in ("city_keywords", "occupation_keywords", "age_keywords", "income_keywords"):
                continue  # handled below
            if field == "check_field":
                continue  # meta-field, not a demographic
            actual = getattr(l1, field, "")
            # Handle list fields (e.g. purchase_channels, information_source)
            if isinstance(actual, list):
                if not any(expected in str(item) for item in actual):
                    return False
            elif expected not in actual:
                return False

        # City keyword match
        city_kws = demo_match.get("city_keywords")
        if city_kws is not None:
            if not any(kw in l1.city for kw in city_kws):
                return False

        # Occupation keyword match
        occ_kws = demo_match.get("occupation_keywords")
        if occ_kws is not None:
            if not any(kw in l1.occupation for kw in occ_kws):
                return False

        # Age keyword match
        age_kws = demo_match.get("age_keywords")
        if age_kws is not None:
            if not any(kw in l1.age for kw in age_kws):
                return False

        # Income keyword match
        income_kws = demo_match.get("income_keywords")
        if income_kws is not None:
            if not any(kw in l1.income for kw in income_kws):
                return False

        # check_field: used to limit which field the keywords are checked against
        # (handled in _build_text_corpus — no rejection here)

        return True

    def _build_text_corpus(
        self,
        persona: PersonaProfile,
        match_fields: list[str],
        pattern: dict,
    ) -> str:
        """Build a searchable text corpus from the specified persona fields.

        match_fields values:
          - "demographics" → Layer 1 fields
          - "behavior"     → Layer 2 fields
          - "psychology"   → Layer 3 fields
          - "scenarios"    → Layer 4 fields
          - "language"     → language_samples
          - empty/None     → all text fields (comprehensive scan)
        """
        l1 = persona.layer1_demographics
        l2 = persona.layer2_behavior
        l3 = persona.layer3_psychology
        l4 = persona.layer4_scenarios

        # If the pattern uses check_field in demographic_match, narrow to
        # only that field for keyword matching.
        demo_match = pattern.get("demographic_match")
        check_field = demo_match.get("check_field") if demo_match else None

        if check_field is not None:
            # Only check the specified demographic field
            field_value = getattr(l1, check_field, "")
            return f" {field_value} ".lower()

        parts: list[str] = []

        if not match_fields:
            # Scan all fields
            match_fields = [
                "demographics", "behavior", "psychology",
                "scenarios", "language",
            ]

        for mf in match_fields:
            if mf == "demographics":
                parts.extend([
                    l1.age, l1.gender, l1.city, l1.income,
                    l1.occupation, l1.education, l1.marital_status,
                    l1.living_type,
                ])
            elif mf == "behavior":
                parts.extend([
                    l2.price_sensitivity,
                    l2.decision_style,
                    l2.brand_loyalty,
                    " ".join(l2.purchase_channels),
                    " ".join(l2.information_source),
                ])
            elif mf == "psychology":
                parts.extend([
                    " ".join(l3.core_values),
                    " ".join(l3.core_anxieties),
                    " ".join(l3.tension_combination.labels),
                    l3.tension_combination.narrative_explanation,
                    l3.secret_motivation,
                    l3.defense_mechanism,
                ])
            elif mf == "scenarios":
                parts.extend([
                    l4.daily_routine,
                    l4.purchase_trigger,
                    l4.stress_response,
                    l4.social_behavior,
                ])
            elif mf == "language":
                parts.extend(persona.language_samples)

        return (" " + " ".join(parts) + " ").lower()

    def _get_or_generate_rule_id(
        self, pattern: dict, counter: int
    ) -> str:
        """Return the rule_id for a pattern.

        Uses backward-compatible BIAS-xxx-NNN format for categories that
        overlap with old hardcoded rules.  Uses SP-xxx pattern id for new
        categories (age, ethnicity, income).
        """
        category = pattern["category"]
        prefix = _CATEGORY_TO_OLD_RULE_PREFIX.get(category)
        if prefix is not None:
            # Sequential numbering per-category (backward compat)
            return f"{prefix}-{counter:03d}"
        # New categories: use pattern id directly
        return pattern["id"]

    # ------------------------------------------------------------------
    # Language bias terms (explicit slurs — kept as dedicated check)
    # ------------------------------------------------------------------

    def _check_language_bias_terms(
        self, persona: PersonaProfile
    ) -> list[BiasFinding]:
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
    # Demographic diversity (overly-average template detection)
    # ------------------------------------------------------------------

    def _check_demographic_diversity(
        self, persona: PersonaProfile
    ) -> list[BiasFinding]:
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
                description=(
                    f"画像呈现高度'平均化'特征({average_markers}/5项)，"
                    f"可能反映模型输出集中在典型模板"
                ),
            ))

        return findings

    # ------------------------------------------------------------------
    # Batch audit helper
    # ------------------------------------------------------------------

    def audit_batch(
        self, personas: list[PersonaProfile]
    ) -> dict[str, Any]:
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
            category_counts[f.category] = (
                category_counts.get(f.category, 0) + 1
            )

        return {
            "total_audited": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total, 3) if total else 0,
            "total_findings": len(all_findings),
            "findings_by_category": category_counts,
            "critical_severity_findings": sum(
                1 for f in all_findings if f.severity == "critical"
            ),
            "high_severity_findings": sum(
                1 for f in all_findings if f.severity == "high"
            ),
        }
