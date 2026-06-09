"""Quality validators for generated CBC questionnaires."""

from __future__ import annotations

from aicbc.core.validators.validation_result import ValidationResult
from aicbc.questionnaire.models import CBCQuestionnaire, ProhibitedPair


class QuestionnaireValidator:
    """Validate a CBC questionnaire for design quality issues."""

    def validate(self, questionnaire: CBCQuestionnaire) -> ValidationResult:
        """Run all validation checks and return a composite result."""
        errors: list[str] = []
        score = 0.0
        max_score = 3.0

        # Check 1: No dominant attributes within choice sets
        if self._has_dominant_attribute(questionnaire):
            errors.append("主导属性检测失败: 某个选择集中所有选项的某个属性水平相同")
        else:
            score += 1.0

        # Check 2: No duplicate choice sets
        if self._has_duplicate_choice_sets(questionnaire):
            errors.append("重复选择集检测失败: 存在两个完全相同的选择集")
        else:
            score += 1.0

        # Check 3: D-efficiency threshold
        if questionnaire.d_efficiency is not None and questionnaire.d_efficiency < 0.5:
            errors.append(
                f"D-efficiency过低: {questionnaire.d_efficiency:.3f} (最低要求0.5)"
            )
        else:
            score += 1.0

        return ValidationResult(
            passed=len(errors) == 0,
            score=score,
            errors=errors,
            details={"max_possible_score": max_score},
        )

    @staticmethod
    def _has_dominant_attribute(questionnaire: CBCQuestionnaire) -> bool:
        """Detect if any attribute has the same level across all alternatives in a set."""
        for cs in questionnaire.choice_sets:
            if not cs.alternatives:
                continue
            # Collect all attribute IDs
            first_attrs = set(cs.alternatives[0].attributes.keys())
            for attr_id in first_attrs:
                values = [alt.attributes.get(attr_id) for alt in cs.alternatives]
                if len(set(values)) == 1:
                    return True
        return False

    @staticmethod
    def _has_duplicate_choice_sets(questionnaire: CBCQuestionnaire) -> bool:
        """Detect if two choice sets have identical alternative configurations."""
        seen: set[frozenset[tuple[str, frozenset[tuple[str, object]]]]] = set()
        for cs in questionnaire.choice_sets:
            # Represent a choice set as a frozenset of alternatives,
            # each alternative as a frozenset of (attr_id, value) pairs.
            alt_set = frozenset(
                frozenset(alt.attributes.items()) for alt in cs.alternatives
            )
            if alt_set in seen:
                return True
            seen.add(alt_set)
        return False

    @staticmethod
    def validate_prohibited_pairs(
        questionnaire: CBCQuestionnaire,
        prohibited_pairs: list[ProhibitedPair],
    ) -> list[str]:
        """Check if any prohibited pair appears in the questionnaire."""
        violations: list[str] = []
        for cs in questionnaire.choice_sets:
            for alt in cs.alternatives:
                for pair in prohibited_pairs:
                    if alt.attributes.get(pair.attribute_id) == pair.level_value:
                        violations.append(
                            f"选择集 {cs.choice_set_id} 选项 {alt.alt_index}: "
                            f"违反禁止组合 {pair.attribute_id}={pair.level_value}"
                        )
        return violations
