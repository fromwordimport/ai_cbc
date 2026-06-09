"""Tests for CBC questionnaire Pydantic models."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from aicbc.questionnaire.models import (
    Attribute,
    AttributeLevel,
    AttributeType,
    CBCStudy,
    DesignAlgorithm,
    DesignParameters,
)


def _make_attribute(**overrides: Any) -> Attribute:
    base = {
        "id": "brand",
        "name": "品牌",
        "type": AttributeType.CATEGORICAL,
        "levels": [
            AttributeLevel(value="A", label="品牌A"),
            AttributeLevel(value="B", label="品牌B"),
        ],
    }
    base.update(overrides)
    return Attribute(**base)


class TestAttributeValidation:
    """Tests for Attribute model constraints."""

    def test_valid_attribute(self) -> None:
        attr = _make_attribute()
        assert attr.id == "brand"
        assert len(attr.levels) == 2

    def test_id_must_be_alphanumeric_underscore_hyphen(self) -> None:
        with pytest.raises(ValidationError, match="id"):
            _make_attribute(id="brand@name")

    def test_levels_must_have_at_least_two(self) -> None:
        with pytest.raises(ValidationError, match="at least 2"):
            _make_attribute(levels=[AttributeLevel(value="A", label="品牌A")])


class TestDesignParametersValidation:
    """Tests for DesignParameters constraints."""

    def test_defaults(self) -> None:
        dp = DesignParameters()
        assert dp.n_choice_sets == 12
        assert dp.n_alternatives == 3
        assert dp.algorithm == DesignAlgorithm.D_OPTIMAL
        assert dp.include_none is True

    def test_n_choice_sets_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DesignParameters(n_choice_sets=2)
        with pytest.raises(ValidationError):
            DesignParameters(n_choice_sets=31)

    def test_n_alternatives_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DesignParameters(n_alternatives=1)
        with pytest.raises(ValidationError):
            DesignParameters(n_alternatives=6)


class TestCBCStudyValidation:
    """Tests for CBCStudy model constraints."""

    def test_valid_study(self) -> None:
        study = CBCStudy(
            study_id="dw-2025",
            product_category="洗碗机",
            research_goal="评估价格敏感度",
            attributes=[
                _make_attribute(id="brand", name="品牌"),
                _make_attribute(id="price", name="价格"),
            ],
        )
        assert study.study_id == "dw-2025"
        assert len(study.attributes) == 2

    def test_too_few_attributes(self) -> None:
        with pytest.raises(ValidationError, match="at least 2"):
            CBCStudy(
                study_id="dw-2025",
                product_category="洗碗机",
                research_goal="评估价格敏感度",
                attributes=[_make_attribute()],
            )

    def test_too_many_attributes(self) -> None:
        with pytest.raises(ValidationError, match="not exceed 8"):
            CBCStudy(
                study_id="dw-2025",
                product_category="洗碗机",
                research_goal="评估价格敏感度",
                attributes=[_make_attribute(id=f"attr{i}") for i in range(9)],
            )

    def test_duplicate_attribute_ids(self) -> None:
        with pytest.raises(ValidationError, match="unique"):
            CBCStudy(
                study_id="dw-2025",
                product_category="洗碗机",
                research_goal="评估价格敏感度",
                attributes=[
                    _make_attribute(id="brand"),
                    _make_attribute(id="brand"),
                ],
            )


class TestCBCQuestionnaireValidation:
    """Tests for CBCQuestionnaire model constraints."""

    def test_mismatched_choice_set_count(self) -> None:
        from aicbc.questionnaire.models import CBCQuestionnaire, ChoiceSet

        dp = DesignParameters(n_choice_sets=3, n_alternatives=2)
        with pytest.raises(ValidationError, match="expected 3 choice sets"):
            CBCQuestionnaire(
                questionnaire_id="q-test",
                study_id="test",
                choice_sets=[
                    ChoiceSet(choice_set_id=1, alternatives=[]),
                ],
                design_parameters=dp,
            )

    def test_mismatched_alternatives_count(self) -> None:
        from aicbc.questionnaire.models import Alternative, CBCQuestionnaire, ChoiceSet

        dp = DesignParameters(n_choice_sets=3, n_alternatives=2)
        with pytest.raises(ValidationError, match="expected 2 alternatives"):
            CBCQuestionnaire(
                questionnaire_id="q-test",
                study_id="test",
                choice_sets=[
                    ChoiceSet(
                        choice_set_id=1,
                        alternatives=[
                            Alternative(alt_index=0, attributes={"a": "x"}),
                            Alternative(alt_index=1, attributes={"a": "y"}),
                        ],
                    ),
                    ChoiceSet(
                        choice_set_id=2,
                        alternatives=[
                            Alternative(alt_index=0, attributes={"a": "x"}),
                            Alternative(alt_index=1, attributes={"a": "y"}),
                        ],
                    ),
                    ChoiceSet(
                        choice_set_id=3,
                        alternatives=[
                            Alternative(alt_index=0, attributes={"a": "x"}),
                            # Missing second alternative
                        ],
                    ),
                ],
                design_parameters=dp,
            )
