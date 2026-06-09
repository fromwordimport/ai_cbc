"""LogicValidator — cross-field business rule validation for PersonaProfile."""

from aicbc.core.models.persona import PersonaProfile
from aicbc.core.validators.validation_result import ValidationResult


class LogicValidator:
    """Validate PersonaProfile against business logic rules.

    Rules:
      RULE-001: tension_combination.narrative_explanation >= 50 chars
      RULE-002: Income tier must be consistent with city tier
      RULE-003: Behavior-demographics linkage (e.g. student + high income)
      RULE-004: Psychology-behavior consistency (e.g. extreme frugality + impulse buying)
      RULE-005: Each language sample must be 20-60 characters
      RULE-006: Forbidden terms must not appear in language samples
    """

    FORBIDDEN_TERMS = ["AI", "算法", "模型", "神经网络", "深度学习", "大模型", "LLM"]

    # City tier mapping for RULE-002
    CITY_TIERS: dict[str, int] = {
        "一线城市": 1,
        "新一线": 2,
        "二线": 3,
        "三线": 4,
        "四线": 5,
    }

    # Income tier mapping (lower number = higher income)
    INCOME_TIERS: dict[str, int] = {
        "月收入<5K": 5,
        "月收入5K-10K": 4,
        "月收入10K-20K": 3,
        "月收入20K-30K": 2,
        "月收入30K+": 1,
    }

    def validate(self, persona: PersonaProfile) -> ValidationResult:
        """Run all logic validations and return a scored ValidationResult."""
        result = ValidationResult()
        rule_scores: dict[str, float] = {}

        # RULE-001
        score = self._rule_001(persona, result)
        rule_scores["RULE-001"] = score

        # RULE-002
        score = self._rule_002(persona, result)
        rule_scores["RULE-002"] = score

        # RULE-003
        score = self._rule_003(persona, result)
        rule_scores["RULE-003"] = score

        # RULE-004
        score = self._rule_004(persona, result)
        rule_scores["RULE-004"] = score

        # RULE-005
        score = self._rule_005(persona, result)
        rule_scores["RULE-005"] = score

        # RULE-006
        score = self._rule_006(persona, result)
        rule_scores["RULE-006"] = score

        total_score = sum(rule_scores.values())
        result.score = total_score
        result.details["rule_scores"] = rule_scores
        result.details["max_possible_score"] = 6.0

        return result

    def _rule_001(self, persona: PersonaProfile, result: ValidationResult) -> float:
        """Tension combination must have narrative explanation >= 50 characters."""
        narrative = persona.layer3_psychology.tension_combination.narrative_explanation
        length = len(narrative.strip()) if narrative else 0
        if length < 50:
            result.add_error(
                f"RULE-001: tension_combination.narrative_explanation must be >= 50 chars, got {length}"
            )
            return 0.0
        return 1.0

    def _rule_002(self, persona: PersonaProfile, result: ValidationResult) -> float:
        """Income tier must be logically consistent with city tier.

        Tier-1 cities should not have very low income (<5K).
        """
        city = persona.layer1_demographics.city
        income = persona.layer1_demographics.income

        city_tier = self.CITY_TIERS.get(city)
        income_tier = self.INCOME_TIERS.get(income)

        if city_tier is None or income_tier is None:
            # Unknown values — skip check (cannot validate does not mean invalid)
            return 1.0

        # Tier-1 or 新一线 with lowest income is suspicious
        if city_tier <= 2 and income_tier >= 5:
            result.add_error(
                f"RULE-002: City '{city}' (tier {city_tier}) with income '{income}' "
                f"is logically inconsistent — high-tier cities rarely have <5K income"
            )
            return 0.0

        return 1.0

    def _rule_003(self, persona: PersonaProfile, result: ValidationResult) -> float:
        """Behavior-demographics linkage anomalies.

        E.g. "学生" + "月收入30K+" should be flagged.
        """
        occupation = persona.layer1_demographics.occupation
        income = persona.layer1_demographics.income
        income_tier = self.INCOME_TIERS.get(income)

        anomalies: list[str] = []

        if occupation == "学生" and income_tier is not None and income_tier <= 2:
            anomalies.append(f"学生 with income '{income}' is unusual")

        if occupation == "退休" and income_tier is not None and income_tier <= 2:
            anomalies.append(f"退休 with income '{income}' is unusual")

        if anomalies:
            for msg in anomalies:
                result.add_error(f"RULE-003: {msg}")
            return 0.0

        return 1.0

    def _rule_004(self, persona: PersonaProfile, result: ValidationResult) -> float:
        """Psychology-behavior consistency check.

        E.g. "极端节俭" + "冲动消费" requires explanation in narrative.
        We flag direct contradictions between price_sensitivity and decision_style.
        """
        price_sensitivity = persona.layer2_behavior.price_sensitivity
        decision_style = persona.layer2_behavior.decision_style

        contradictions: list[str] = []

        # Extreme frugality + impulse buying
        if "极端节俭" in price_sensitivity and "冲动" in decision_style:
            contradictions.append(
                f"price_sensitivity='{price_sensitivity}' vs decision_style='{decision_style}'"
            )

        # High price sensitivity + luxury seeking
        if "高" in price_sensitivity and "奢侈" in decision_style:
            contradictions.append(
                f"price_sensitivity='{price_sensitivity}' vs decision_style='{decision_style}'"
            )

        if contradictions:
            for msg in contradictions:
                result.add_error(
                    f"RULE-004: Psychology-behavior contradiction: {msg} — "
                    f"requires narrative explanation in tension_combination"
                )
            return 0.0

        return 1.0

    def _rule_005(self, persona: PersonaProfile, result: ValidationResult) -> float:
        """Each language sample must be 20-60 characters."""
        samples = persona.language_samples
        if not samples:
            result.add_error("RULE-005: language_samples is empty")
            return 0.0

        all_valid = True
        for idx, sample in enumerate(samples):
            length = len(sample.strip())
            if not (20 <= length <= 60):
                result.add_error(
                    f"RULE-005: language_samples[{idx}] must be 20-60 chars, got {length}"
                )
                all_valid = False

        return 1.0 if all_valid else 0.0

    def _rule_006(self, persona: PersonaProfile, result: ValidationResult) -> float:
        """Forbidden terms must not appear in language samples."""
        samples = persona.language_samples
        if not samples:
            result.add_error("RULE-006: language_samples is empty")
            return 0.0

        violations: list[str] = []
        for idx, sample in enumerate(samples):
            for term in self.FORBIDDEN_TERMS:
                if term in sample:
                    violations.append(f"language_samples[{idx}] contains forbidden term '{term}'")

        if violations:
            for msg in violations:
                result.add_error(f"RULE-006: {msg}")
            return 0.0

        return 1.0
