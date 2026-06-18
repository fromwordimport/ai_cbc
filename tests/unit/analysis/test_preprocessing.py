"""Tests for analysis preprocessing module."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from aicbc.analysis.preprocessing import get_feature_columns, to_long_format, validate_dataset
from aicbc.questionnaire.models import Attribute, AttributeLevel, AttributeType
from aicbc.questionnaire.response_models import (
    AlternativeRecord,
    CBCRawDataset,
    ChoiceRecord,
    DatasetMetadata,
)


@pytest.fixture
def sample_attributes() -> list[Attribute]:
    """Create sample attributes for testing."""
    return [
        Attribute(
            id="price",
            name="价格",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value=2999, label="2999元"),
                AttributeLevel(value=3999, label="3999元"),
                AttributeLevel(value=4999, label="4999元"),
            ],
        ),
        Attribute(
            id="brand",
            name="品牌",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="美的", label="美的"),
                AttributeLevel(value="西门子", label="西门子"),
                AttributeLevel(value="小米", label="小米"),
            ],
        ),
    ]


@pytest.fixture
def sample_dataset() -> CBCRawDataset:
    """Create a minimal CBCRawDataset for testing."""
    return CBCRawDataset(
        metadata=DatasetMetadata(
            study_id="test-study",
            n_respondents=2,
            n_choice_sets=2,
            n_alternatives=2,
        ),
        choice_records=[
            ChoiceRecord(
                respondent_id="r1",
                respondent_index=0,
                segment="test",
                choice_set_id=1,
                choice_set_index=0,
                alternatives=[
                    AlternativeRecord(
                        alt_index=0,
                        chosen=True,
                        attributes={"price": 2999, "brand": "美的"},
                    ),
                    AlternativeRecord(
                        alt_index=1,
                        chosen=False,
                        attributes={"price": 3999, "brand": "西门子"},
                    ),
                ],
            ),
            ChoiceRecord(
                respondent_id="r1",
                respondent_index=0,
                segment="test",
                choice_set_id=2,
                choice_set_index=1,
                alternatives=[
                    AlternativeRecord(
                        alt_index=0,
                        chosen=False,
                        attributes={"price": 4999, "brand": "小米"},
                    ),
                    AlternativeRecord(
                        alt_index=1,
                        chosen=True,
                        attributes={"price": 2999, "brand": "西门子"},
                    ),
                ],
            ),
        ],
    )


class TestToLongFormat:
    """Tests for to_long_format function."""

    def test_basic_conversion(self, sample_dataset, sample_attributes):
        """Test basic long format conversion."""
        df = to_long_format(sample_dataset, sample_attributes)

        assert len(df) == 4  # 2 respondents * 2 tasks * 2 alternatives
        assert "resp_id" in df.columns
        assert "chosen" in df.columns
        assert "price" in df.columns
        assert "brand_0" in df.columns
        assert "brand_1" in df.columns

    def test_choice_values(self, sample_dataset, sample_attributes):
        """Test that chosen values are 0/1."""
        df = to_long_format(sample_dataset, sample_attributes)

        assert set(df["chosen"].unique()).issubset({0, 1})
        # Each task should have exactly one chosen=1
        for (_resp, _task), group in df.groupby(["resp_id", "task_id"]):
            assert group["chosen"].sum() == 1

    def test_effects_coding(self, sample_dataset, sample_attributes):
        """Test that categorical attributes are effects-coded."""
        df = to_long_format(sample_dataset, sample_attributes)

        # For 3-level brand, we should have 2 columns
        assert "brand_0" in df.columns
        assert "brand_1" in df.columns

        # Check that effects coding values are correct
        brand_0_values = set(df["brand_0"].unique())
        assert brand_0_values.issubset({-1.0, 0.0, 1.0})


class TestGetFeatureColumns:
    """Tests for get_feature_columns function."""

    def test_feature_columns(self, sample_attributes):
        """Test feature column names."""
        cols = get_feature_columns(sample_attributes)

        assert cols == ["price", "brand_0", "brand_1"]


class TestValidateDataset:
    """Tests for validate_dataset function."""

    def test_valid_dataset(self, sample_dataset, sample_attributes):
        """Test validation of a valid dataset."""
        report = validate_dataset(sample_dataset, sample_attributes)

        assert report["valid"] is True
        assert len(report["errors"]) == 0

    def test_insufficient_sample_size(self, sample_attributes):
        """Test warning for small sample size."""
        # Create a tiny dataset
        tiny_dataset = CBCRawDataset(
            metadata=DatasetMetadata(
                study_id="tiny",
                n_respondents=1,
                n_choice_sets=2,
                n_alternatives=2,
            ),
            choice_records=[
                ChoiceRecord(
                    respondent_id="r1",
                    respondent_index=0,
                    segment="test",
                    choice_set_id=1,
                    choice_set_index=0,
                    alternatives=[
                        AlternativeRecord(
                            alt_index=0,
                            chosen=True,
                            attributes={"price": 2999, "brand": "美的"},
                        ),
                        AlternativeRecord(
                            alt_index=1,
                            chosen=False,
                            attributes={"price": 3999, "brand": "西门子"},
                        ),
                    ],
                ),
            ],
        )

        report = validate_dataset(tiny_dataset, sample_attributes)

        assert len(report["warnings"]) > 0
        assert any("insufficient" in w.lower() or "样本" in w for w in report["warnings"])
