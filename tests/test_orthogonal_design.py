"""Tests for orthogonal experimental design."""

from __future__ import annotations

from aicbc.questionnaire.design.orthogonal import (
    _check_orthogonality,
    _distribute_to_choice_sets,
    _generate_full_factorial,
    _select_balanced_subset,
    generate_orthogonal_questionnaire,
)
from aicbc.questionnaire.models import (
    Alternative,
    Attribute,
    AttributeLevel,
    AttributeType,
    ChoiceSet,
    DesignAlgorithm,
    DesignParameters,
)


def _make_attrs() -> list[Attribute]:
    return [
        Attribute(
            id="brand",
            name="品牌",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="A", label="A"),
                AttributeLevel(value="B", label="B"),
            ],
        ),
        Attribute(
            id="price",
            name="价格",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value=100, label="100"),
                AttributeLevel(value=200, label="200"),
            ],
        ),
    ]


class TestGenerateFullFactorial:
    """Tests for full factorial generation."""

    def test_count(self) -> None:
        attrs = _make_attrs()
        profiles = _generate_full_factorial(attrs)
        assert len(profiles) == 4  # 2 x 2

    def test_all_combinations_present(self) -> None:
        attrs = _make_attrs()
        profiles = _generate_full_factorial(attrs)
        combos = {(p["brand"], p["price"]) for p in profiles}
        assert combos == {("A", 100), ("A", 200), ("B", 100), ("B", 200)}

    def test_three_attributes(self) -> None:
        attrs = _make_attrs() + [
            Attribute(
                id="color",
                name="颜色",
                type=AttributeType.CATEGORICAL,
                levels=[
                    AttributeLevel(value="R", label="R"),
                    AttributeLevel(value="B", label="B"),
                ],
            ),
        ]
        profiles = _generate_full_factorial(attrs)
        assert len(profiles) == 8  # 2 x 2 x 2


class TestSelectBalancedSubset:
    """Tests for balanced subset selection."""

    def test_target_size(self) -> None:
        attrs = _make_attrs()
        profiles = _generate_full_factorial(attrs)
        subset = _select_balanced_subset(profiles, attrs, target_size=3, seed=42)
        assert len(subset) == 3

    def test_all_selected_when_target_equals_pool(self) -> None:
        attrs = _make_attrs()
        profiles = _generate_full_factorial(attrs)
        subset = _select_balanced_subset(profiles, attrs, target_size=4, seed=42)
        assert len(subset) == 4

    def test_balanced_frequencies(self) -> None:
        attrs = _make_attrs()
        profiles = _generate_full_factorial(attrs)
        subset = _select_balanced_subset(profiles, attrs, target_size=4, seed=42)
        brand_counts = {"A": 0, "B": 0}
        for p in subset:
            brand_counts[p["brand"]] += 1
        # With full factorial selected, both brands should appear twice
        assert brand_counts["A"] == 2
        assert brand_counts["B"] == 2


class TestDistributeToChoiceSets:
    """Tests for choice set distribution."""

    def test_correct_number_of_sets(self) -> None:
        attrs = _make_attrs()
        profiles = _generate_full_factorial(attrs)
        sets = _distribute_to_choice_sets(
            profiles, num_sets=2, alts_per_set=2, attributes=attrs, seed=42
        )
        assert len(sets) == 2

    def test_correct_alternatives_per_set(self) -> None:
        attrs = _make_attrs()
        profiles = _generate_full_factorial(attrs)
        sets = _distribute_to_choice_sets(
            profiles, num_sets=2, alts_per_set=2, attributes=attrs, seed=42
        )
        for cs in sets:
            assert len(cs.alternatives) == 2

    def test_alternative_indices(self) -> None:
        attrs = _make_attrs()
        profiles = _generate_full_factorial(attrs)
        sets = _distribute_to_choice_sets(
            profiles, num_sets=2, alts_per_set=2, attributes=attrs, seed=42
        )
        for cs in sets:
            indices = [alt.alt_index for alt in cs.alternatives]
            assert indices == [0, 1]


class TestCheckOrthogonality:
    """Tests for orthogonality scoring."""

    def test_perfect_balance(self) -> None:
        attrs = _make_attrs()
        # Perfectly balanced: 2 of each brand, 2 of each price
        choice_sets = [
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
                    Alternative(alt_index=0, attributes={"brand": "B", "price": 100}),
                    Alternative(alt_index=1, attributes={"brand": "A", "price": 200}),
                ],
            ),
        ]
        score = _check_orthogonality(choice_sets, attrs)
        assert score == 1.0

    def test_empty_sets(self) -> None:
        assert _check_orthogonality([], _make_attrs()) == 0.0

    def test_score_range(self) -> None:
        """Score should always be in [0, 1]."""
        attrs = _make_attrs()
        profiles = _generate_full_factorial(attrs)
        sets = _distribute_to_choice_sets(
            profiles, num_sets=2, alts_per_set=2, attributes=attrs, seed=42
        )
        score = _check_orthogonality(sets, attrs)
        assert 0.0 <= score <= 1.0


class TestGenerateOrthogonalQuestionnaire:
    """End-to-end tests for orthogonal questionnaire generation."""

    def test_basic_generation(self) -> None:
        attrs = _make_attrs()
        dp = DesignParameters(
            n_choice_sets=3, n_alternatives=2, algorithm=DesignAlgorithm.BALANCED, seed=42
        )
        q = generate_orthogonal_questionnaire(
            study_id="test-orth", attributes=attrs, design_parameters=dp, seed=42
        )
        assert q.questionnaire_id == "q-test-orth-orth"
        assert q.study_id == "test-orth"
        assert len(q.choice_sets) == 3
        assert len(q.choice_sets[0].alternatives) == 2

    def test_efficiency_reported(self) -> None:
        attrs = _make_attrs()
        dp = DesignParameters(
            n_choice_sets=3, n_alternatives=2, algorithm=DesignAlgorithm.BALANCED, seed=42
        )
        q = generate_orthogonal_questionnaire(
            study_id="test-orth", attributes=attrs, design_parameters=dp, seed=42
        )
        assert q.d_efficiency is not None
        assert q.a_efficiency is not None
        assert 0.0 <= q.d_efficiency <= 1.0
        assert 0.0 <= q.a_efficiency <= 1.0

    def test_reproducibility(self) -> None:
        attrs = _make_attrs()
        dp = DesignParameters(
            n_choice_sets=3, n_alternatives=2, algorithm=DesignAlgorithm.BALANCED, seed=42
        )
        q1 = generate_orthogonal_questionnaire(
            study_id="test-orth", attributes=attrs, design_parameters=dp, seed=42
        )
        q2 = generate_orthogonal_questionnaire(
            study_id="test-orth", attributes=attrs, design_parameters=dp, seed=42
        )
        # Same seed should produce identical choice sets
        for cs1, cs2 in zip(q1.choice_sets, q2.choice_sets, strict=True):
            for a1, a2 in zip(cs1.alternatives, cs2.alternatives, strict=True):
                assert a1.attributes == a2.attributes

    def test_dishwasher_defaults(self) -> None:
        """Test with the default dishwasher 7-attribute set."""
        from aicbc.questionnaire.generator import _dishwasher_default_attributes

        attrs = _dishwasher_default_attributes()
        dp = DesignParameters(
            n_choice_sets=12, n_alternatives=3, algorithm=DesignAlgorithm.BALANCED, seed=42
        )
        q = generate_orthogonal_questionnaire(
            study_id="dw-orth", attributes=attrs, design_parameters=dp, seed=42
        )
        assert len(q.choice_sets) == 12
        assert all(len(cs.alternatives) == 3 for cs in q.choice_sets)
        # Orthogonality should be reasonably good
        score = _check_orthogonality(q.choice_sets, attrs)
        assert score >= 0.5  # At least half-decent balance
