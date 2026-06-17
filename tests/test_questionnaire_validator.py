"""Tests for CBC questionnaire validators."""

from __future__ import annotations

from aicbc.questionnaire.models import (
    Alternative,
    Attribute,
    AttributeLevel,
    AttributeType,
    CBCQuestionnaire,
    ChoiceSet,
    Condition,
    DesignParameters,
    ProhibitedPair,
)
from aicbc.questionnaire.validators import QuestionnaireValidator


def _make_attr(id_: str, type_: AttributeType, values: list) -> Attribute:
    return Attribute(
        id=id_,
        name=id_,
        type=type_,
        levels=[AttributeLevel(value=v, label=str(v)) for v in values],
    )


def _make_questionnaire(
    choice_sets: list[ChoiceSet],
    n_choice_sets: int | None = None,
    n_alternatives: int | None = None,
    d_efficiency: float | None = 0.9,
) -> CBCQuestionnaire:
    # Infer nalts from first non-empty choice set, default to 2, min 2
    inferred_nalts = 2
    for cs in choice_sets:
        if cs.alternatives:
            inferred_nalts = len(cs.alternatives)
            break
    nalts = max(n_alternatives or inferred_nalts, 2)
    ncs = max(n_choice_sets or 0, len(choice_sets), 3)

    # Ensure each original choice set has exactly nalts alternatives
    fixed: list[ChoiceSet] = []
    for cs in choice_sets:
        if len(cs.alternatives) == nalts:
            fixed.append(cs)
        elif len(cs.alternatives) == 0:
            fixed.append(
                ChoiceSet(
                    choice_set_id=cs.choice_set_id,
                    alternatives=[
                        Alternative(
                            alt_index=i,
                            attributes={"__dummy": f"orig{cs.choice_set_id}_{i}"},
                        )
                        for i in range(nalts)
                    ],
                )
            )
        elif len(cs.alternatives) < nalts:
            extra = [
                Alternative(
                    alt_index=i,
                    attributes={"__dummy": f"orig{cs.choice_set_id}_{i}"},
                )
                for i in range(len(cs.alternatives), nalts)
            ]
            fixed.append(
                ChoiceSet(
                    choice_set_id=cs.choice_set_id,
                    alternatives=list(cs.alternatives) + extra,
                )
            )
        else:
            fixed.append(
                ChoiceSet(
                    choice_set_id=cs.choice_set_id,
                    alternatives=cs.alternatives[:nalts],
                )
            )

    # Find template from fixed choice sets (they have correct nalts)
    template_cs = None
    for cs in fixed:
        if cs.alternatives:
            template_cs = cs
            break

    # Pad to ncs
    while len(fixed) < ncs:
        cs_id = len(fixed) + 1
        if template_cs is not None:
            new_alts = []
            for j, alt in enumerate(template_cs.alternatives):
                new_attrs: dict[str, object] = {}
                for k, v in alt.attributes.items():
                    if isinstance(v, str):
                        new_attrs[k] = v + f"__pad{cs_id}_{j}"
                    elif isinstance(v, (int, float)):
                        new_attrs[k] = v + cs_id * 10000 + j
                    else:
                        new_attrs[k] = v
                new_alts.append(Alternative(alt_index=alt.alt_index, attributes=new_attrs))
            fixed.append(ChoiceSet(choice_set_id=cs_id, alternatives=new_alts))
        else:
            new_alts = [
                Alternative(alt_index=i, attributes={"__dummy": f"val{cs_id}_{i}"})
                for i in range(nalts)
            ]
            fixed.append(ChoiceSet(choice_set_id=cs_id, alternatives=new_alts))

    dp = DesignParameters(n_choice_sets=ncs, n_alternatives=nalts)
    return CBCQuestionnaire(
        questionnaire_id="q-test",
        study_id="test",
        choice_sets=fixed,
        design_parameters=dp,
        d_efficiency=d_efficiency,
    )


class TestDominantAttribute:
    """Tests for dominant attribute detection."""

    def test_no_dominant_passes(self) -> None:
        """All attributes vary within each choice set."""
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "B", "price": 200}),
                ],
            ),
        ])
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.passed is True

    def test_dominant_attribute_fails(self) -> None:
        """All alternatives have the same brand."""
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "A", "price": 200}),
                ],
            ),
        ])
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.passed is False
        assert any("主导属性" in e for e in result.errors)

    def test_dominant_in_one_of_many_sets(self) -> None:
        """Second set has dominant price."""
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "B", "price": 200}),
                ],
            ),
            ChoiceSet(
                choice_set_id=2,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "B", "price": 100}),
                ],
            ),
        ], n_choice_sets=2)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.passed is False
        assert any("主导属性" in e for e in result.errors)

    def test_empty_choice_set_no_crash(self) -> None:
        """Empty choice sets should not crash the validator."""
        q = _make_questionnaire([
            ChoiceSet(choice_set_id=1, alternatives=[]),
        ])
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.passed is True


class TestDuplicateChoiceSets:
    """Tests for duplicate choice set detection."""

    def test_no_duplicates_passes(self) -> None:
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A"}),
                    Alternative(alt_index=1, attributes={"brand": "B"}),
                ],
            ),
            ChoiceSet(
                choice_set_id=2,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "B"}),
                    Alternative(alt_index=1, attributes={"brand": "A"}),
                ],
            ),
        ], n_choice_sets=2)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.passed is True

    def test_duplicate_sets_fails(self) -> None:
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A"}),
                    Alternative(alt_index=1, attributes={"brand": "B"}),
                ],
            ),
            ChoiceSet(
                choice_set_id=2,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A"}),
                    Alternative(alt_index=1, attributes={"brand": "B"}),
                ],
            ),
        ], n_choice_sets=2)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.passed is False
        assert any("重复选择集" in e for e in result.errors)

    def test_same_alts_different_order_not_duplicate(self) -> None:
        """Different ordering of alternatives within a set is not a duplicate."""
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A"}),
                    Alternative(alt_index=1, attributes={"brand": "B"}),
                ],
            ),
            ChoiceSet(
                choice_set_id=2,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "B"}),
                    Alternative(alt_index=1, attributes={"brand": "A"}),
                ],
            ),
        ], n_choice_sets=2)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.passed is True


class TestDEfficiencyCheck:
    """Tests for D-efficiency threshold validation."""

    def test_high_efficiency_passes(self) -> None:
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A"}),
                    Alternative(alt_index=1, attributes={"brand": "B"}),
                ],
            ),
        ], d_efficiency=0.9)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.score >= 2.0  # at least 2 out of 3

    def test_low_efficiency_fails(self) -> None:
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A"}),
                    Alternative(alt_index=1, attributes={"brand": "B"}),
                ],
            ),
        ], d_efficiency=0.3)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.passed is False
        assert any("D-efficiency" in e for e in result.errors)

    def test_none_efficiency_skips_check(self) -> None:
        """When d_efficiency is None, the check is skipped."""
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A"}),
                    Alternative(alt_index=1, attributes={"brand": "B"}),
                ],
            ),
        ], d_efficiency=None)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        # Should pass (no dominant, no duplicates, d_efficiency=None skips check)
        assert result.passed is True


class TestValidateProhibitedPairs:
    """Tests for prohibited pair violation detection."""

    def test_no_violation(self) -> None:
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "B", "price": 200}),
                ],
            ),
        ])
        pairs = [ProhibitedPair(conditions=[Condition(attribute_id="brand", level_value="C")])]
        violations = QuestionnaireValidator.validate_prohibited_pairs(q, pairs)
        assert violations == []

    def test_single_violation(self) -> None:
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "B", "price": 200}),
                ],
            ),
        ])
        pairs = [ProhibitedPair(conditions=[Condition(attribute_id="brand", level_value="A")])]
        violations = QuestionnaireValidator.validate_prohibited_pairs(q, pairs)
        assert len(violations) == 1
        assert "brand=A" in violations[0]

    def test_multiple_violations(self) -> None:
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "B", "price": 200}),
                ],
            ),
        ])
        pairs = [
            ProhibitedPair(conditions=[Condition(attribute_id="brand", level_value="A")]),
            ProhibitedPair(conditions=[Condition(attribute_id="brand", level_value="B")]),
        ]
        violations = QuestionnaireValidator.validate_prohibited_pairs(q, pairs)
        assert len(violations) == 2

    def test_across_multiple_sets(self) -> None:
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A"}),
                ],
            ),
            ChoiceSet(
                choice_set_id=2,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A"}),
                ],
            ),
        ], n_choice_sets=2, n_alternatives=1)
        pairs = [ProhibitedPair(conditions=[Condition(attribute_id="brand", level_value="A")])]
        violations = QuestionnaireValidator.validate_prohibited_pairs(q, pairs)
        assert len(violations) == 2


class TestScoreCalculation:
    """Tests for validation score calculation."""

    def test_perfect_score(self) -> None:
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "B", "price": 200}),
                ],
            ),
        ], d_efficiency=0.9)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.score == 3.0
        assert result.passed is True

    def test_partial_score(self) -> None:
        """One check fails, score should be 2.0."""
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "A", "price": 200}),
                ],
            ),
        ], d_efficiency=0.9)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.score == 2.0
        assert result.passed is False

    def test_all_failures(self) -> None:
        """All checks fail, score should be 0.0."""
        q = _make_questionnaire([
            ChoiceSet(
                choice_set_id=1,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "A", "price": 100}),
                ],
            ),
            ChoiceSet(
                choice_set_id=2,
                alternatives=[
                    Alternative(alt_index=0, attributes={"brand": "A", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "A", "price": 100}),
                ],
            ),
        ], n_choice_sets=2, d_efficiency=0.3)
        validator = QuestionnaireValidator()
        result = validator.validate(q)
        assert result.score == 0.0
        assert result.passed is False
        assert len(result.errors) == 3
