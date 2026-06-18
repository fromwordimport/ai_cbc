"""Tests for effects coding utilities."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import numpy as np
import pytest

from aicbc.questionnaire.design.effects_coding import (
    effects_encode_categorical,
    encode_design_matrix,
    encode_profile,
    n_parameters,
)
from aicbc.questionnaire.models import Attribute, AttributeLevel, AttributeType


def _make_attr(id: str, levels: list[str]) -> Attribute:
    return Attribute(
        id=id,
        name=id,
        type=AttributeType.CATEGORICAL,
        levels=[AttributeLevel(value=v, label=v) for v in levels],
    )


class TestEffectsEncodeCategorical:
    """Tests for effects coding of categorical attributes."""

    def test_three_levels(self) -> None:
        attr = _make_attr("brand", ["A", "B", "C"])

        a = effects_encode_categorical("A", attr)
        np.testing.assert_array_equal(a, [1.0, 0.0])

        b = effects_encode_categorical("B", attr)
        np.testing.assert_array_equal(b, [0.0, 1.0])

        c = effects_encode_categorical("C", attr)
        np.testing.assert_array_equal(c, [-1.0, -1.0])

    def test_two_levels(self) -> None:
        attr = _make_attr("size", ["S", "L"])

        small = effects_encode_categorical("S", attr)
        np.testing.assert_array_equal(small, [1.0])

        large = effects_encode_categorical("L", attr)
        np.testing.assert_array_equal(large, [-1.0])

    def test_parameters_sum_to_zero(self) -> None:
        """The effects coding convention: all level parameters sum to 0."""
        attr = _make_attr("brand", ["A", "B", "C"])
        encodings = [effects_encode_categorical(v, attr) for v in ["A", "B", "C"]]
        total = np.sum(encodings, axis=0)
        np.testing.assert_array_almost_equal(total, [0.0, 0.0])

    def test_invalid_value_raises(self) -> None:
        attr = _make_attr("brand", ["A", "B"])
        with pytest.raises(ValueError, match="not found"):
            effects_encode_categorical("Z", attr)

    def test_single_level_raises(self) -> None:
        """Effects coding requires at least 2 levels."""
        attr = Attribute.model_construct(
            id="x",
            name="x",
            type=AttributeType.CATEGORICAL,
            levels=[AttributeLevel(value="A", label="A")],
        )
        with pytest.raises(ValueError, match="at least 2"):
            effects_encode_categorical("A", attr)


class TestEncodeProfile:
    """Tests for full profile encoding."""

    def test_two_attributes(self) -> None:
        brand = _make_attr("brand", ["A", "B", "C"])  # 2 params
        price = Attribute(
            id="price",
            name="price",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value=100, label="100"),
                AttributeLevel(value=200, label="200"),
            ],
        )
        profile = {"brand": "A", "price": 150.0}
        encoded = encode_profile(profile, [brand, price])

        assert encoded.shape == (3,)
        np.testing.assert_array_equal(encoded[:2], [1.0, 0.0])
        # Price is standardised: mean=150, std=50, so 150 -> 0.0
        assert encoded[2] == 0.0

    def test_missing_attribute_raises(self) -> None:
        attr = _make_attr("brand", ["A", "B"])
        with pytest.raises(ValueError, match="missing"):
            encode_profile({}, [attr])


class TestEncodeDesignMatrix:
    """Tests for design matrix encoding."""

    def test_multiple_profiles(self) -> None:
        brand = _make_attr("brand", ["A", "B", "C"])  # 2 params
        attrs = [brand]
        profiles = [{"brand": "A"}, {"brand": "B"}, {"brand": "C"}]
        design_matrix = encode_design_matrix(profiles, attrs)

        assert design_matrix.shape == (3, 2)
        np.testing.assert_array_equal(design_matrix[0], [1.0, 0.0])
        np.testing.assert_array_equal(design_matrix[1], [0.0, 1.0])
        np.testing.assert_array_equal(design_matrix[2], [-1.0, -1.0])

    def test_empty_profiles(self) -> None:
        design_matrix = encode_design_matrix([], [])
        assert design_matrix.shape == (0,)


class TestNParameters:
    """Tests for parameter count calculation."""

    def test_categorical(self) -> None:
        attr = _make_attr("x", ["A", "B", "C"])  # 3 levels -> 2 params
        assert n_parameters([attr]) == 2

    def test_price(self) -> None:
        attr = Attribute(
            id="price",
            name="price",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value=100, label="100"),
                AttributeLevel(value=200, label="200"),
            ],
        )
        assert n_parameters([attr]) == 1

    def test_mixed(self) -> None:
        cat = _make_attr("brand", ["A", "B", "C"])  # 2
        price = Attribute(
            id="price",
            name="price",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value=100, label="100"),
                AttributeLevel(value=200, label="200"),
            ],
        )  # 1
        assert n_parameters([cat, price]) == 3
