"""Tests for D-optimal experimental design."""

from __future__ import annotations

from aicbc.questionnaire.design.d_optimal import (
    d_optimal_design,
    generate_candidate_set,
    generate_d_optimal_questionnaire,
)
from aicbc.questionnaire.models import (
    Attribute,
    AttributeLevel,
    AttributeType,
    Condition,
    DesignAlgorithm,
    DesignParameters,
    ProhibitedPair,
)


def _make_attr(id: str, levels: list[str]) -> Attribute:
    return Attribute(
        id=id,
        name=id,
        type=AttributeType.CATEGORICAL,
        levels=[AttributeLevel(value=v, label=v) for v in levels],
    )


def _dishwasher_attrs() -> list[Attribute]:
    """Return a simplified 3-attribute set for testing."""
    return [
        _make_attr("brand", ["美的", "西门子", "方太"]),
        _make_attr("capacity", ["6套", "10套", "13套"]),
        _make_attr("install", ["台式", "嵌入式", "水槽式"]),
    ]


class TestCandidateSet:
    """Tests for candidate set generation."""

    def test_full_factorial_size(self) -> None:
        attrs = _dishwasher_attrs()
        candidates = generate_candidate_set(attrs)
        # 3^3 = 27
        assert len(candidates) == 27

    def test_prohibited_pairs_filter(self) -> None:
        attrs = _dishwasher_attrs()
        prohibited = [ProhibitedPair(conditions=[Condition(attribute_id="brand", level_value="美的")])]
        candidates = generate_candidate_set(attrs, prohibited)
        # Remove all profiles where brand == "美的" (3*3 = 9)
        assert len(candidates) == 18
        for c in candidates:
            assert c["brand"] != "美的"


class TestDoptimalDesign:
    """Tests for D-optimal design algorithm."""

    def test_generates_correct_number_of_choice_sets(self) -> None:
        attrs = _dishwasher_attrs()
        dp = DesignParameters(n_choice_sets=6, n_alternatives=3, algorithm=DesignAlgorithm.D_OPTIMAL)
        result = d_optimal_design(attrs, dp, seed=42)

        assert len(result["design"]) == 6
        for cs in result["design"]:
            assert len(cs.alternatives) == 3

    def test_no_duplicates_within_choice_set(self) -> None:
        attrs = _dishwasher_attrs()
        dp = DesignParameters(n_choice_sets=6, n_alternatives=3, algorithm=DesignAlgorithm.D_OPTIMAL)
        result = d_optimal_design(attrs, dp, seed=42)

        for cs in result["design"]:
            profiles = [tuple(sorted(a.attributes.items())) for a in cs.alternatives]
            assert len(profiles) == len(set(profiles)), f"Duplicates in choice set {cs.choice_set_id}"

    def test_d_efficiency_is_positive(self) -> None:
        attrs = _dishwasher_attrs()
        dp = DesignParameters(n_choice_sets=8, n_alternatives=3, algorithm=DesignAlgorithm.D_OPTIMAL)
        result = d_optimal_design(attrs, dp, seed=42)

        assert result["d_efficiency"] is not None
        assert result["d_efficiency"] > 0
        assert result["d_efficiency"] <= 1.0

    def test_converges_within_iterations(self) -> None:
        attrs = _dishwasher_attrs()
        dp = DesignParameters(n_choice_sets=6, n_alternatives=3, algorithm=DesignAlgorithm.D_OPTIMAL)
        result = d_optimal_design(attrs, dp, seed=42, max_iterations=200)

        assert result["iterations"] <= 200
        assert result["iterations"] > 0

    def test_questionnaire_model(self) -> None:
        attrs = _dishwasher_attrs()
        dp = DesignParameters(n_choice_sets=4, n_alternatives=2, algorithm=DesignAlgorithm.D_OPTIMAL)
        q = generate_d_optimal_questionnaire("test-study", attrs, dp, seed=42)

        assert q.questionnaire_id.startswith("q-test-study")
        assert q.study_id == "test-study"
        assert len(q.choice_sets) == 4
        assert q.d_efficiency is not None

    def test_reproducibility_with_seed(self) -> None:
        attrs = _dishwasher_attrs()
        dp = DesignParameters(n_choice_sets=4, n_alternatives=2, algorithm=DesignAlgorithm.D_OPTIMAL)

        q1 = generate_d_optimal_questionnaire("s1", attrs, dp, seed=123)
        q2 = generate_d_optimal_questionnaire("s2", attrs, dp, seed=123)

        # Same seed should produce same designs (ignoring questionnaire_id)
        for cs1, cs2 in zip(q1.choice_sets, q2.choice_sets, strict=True):
            for a1, a2 in zip(cs1.alternatives, cs2.alternatives, strict=True):
                assert a1.attributes == a2.attributes

    def test_larger_design_efficiency(self) -> None:
        """D-optimal should achieve reasonable efficiency for a realistic design."""
        attrs = [
            _make_attr("brand", ["美的", "西门子", "方太"]),
            _make_attr("capacity", ["6套", "10套", "13套"]),
            _make_attr("install", ["台式", "嵌入式", "水槽式"]),
            _make_attr("features", ["基础", "智能", "全能"]),
        ]
        dp = DesignParameters(n_choice_sets=12, n_alternatives=3, algorithm=DesignAlgorithm.D_OPTIMAL)
        result = d_optimal_design(attrs, dp, seed=42)

        assert result["d_efficiency"] is not None
        # For this moderate size, expect at least some efficiency
        assert result["d_efficiency"] > 0.1
