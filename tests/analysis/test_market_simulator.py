"""Tests for market simulator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aicbc.analysis.simulation.market_simulator import MarketSimulator
from aicbc.questionnaire.models import Attribute, AttributeLevel, AttributeType


@pytest.fixture
def sample_utilities() -> pd.DataFrame:
    """Create sample individual utilities."""
    np.random.seed(42)
    return pd.DataFrame(
        {
            "price": np.random.normal(-0.002, 0.001, 100),
            "brand_0": np.random.normal(0.5, 0.3, 100),
            "brand_1": np.random.normal(0.3, 0.3, 100),
        },
        index=[f"resp_{i:03d}" for i in range(100)],
    )


@pytest.fixture
def sample_attributes() -> list[Attribute]:
    """Create sample attributes."""
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


class TestMarketSimulator:
    """Tests for MarketSimulator."""

    def test_shares_sum_to_one(self, sample_utilities, sample_attributes):
        """Test that shares sum to 100%."""
        sim = MarketSimulator(sample_utilities, sample_attributes)

        scenarios = [
            {"name": "产品A", "price": 2999, "brand": "美的"},
            {"name": "产品B", "price": 3999, "brand": "西门子"},
        ]

        result = sim.simulate_share(scenarios, include_none=False)
        total = result["predicted_share"].sum()

        assert pytest.approx(total, abs=0.01) == 1.0

    def test_lower_price_higher_share(self, sample_utilities, sample_attributes):
        """Test that lower price products get higher share."""
        sim = MarketSimulator(sample_utilities, sample_attributes)

        scenarios = [
            {"name": "低价", "price": 2999, "brand": "美的"},
            {"name": "高价", "price": 4999, "brand": "美的"},
        ]

        result = sim.simulate_share(scenarios, include_none=False)
        low_share = result[result["name"] == "低价"]["predicted_share"].values[0]
        high_share = result[result["name"] == "高价"]["predicted_share"].values[0]

        assert low_share > high_share

    def test_with_none_option(self, sample_utilities, sample_attributes):
        """Test market simulation with none option."""
        sim = MarketSimulator(sample_utilities, sample_attributes)

        scenarios = [
            {"name": "产品A", "price": 2999, "brand": "美的"},
        ]

        result = sim.simulate_share(scenarios, include_none=True)

        assert len(result) == 2  # Product + none
        assert "none" in result["name"].values
        total = result["predicted_share"].sum()
        assert pytest.approx(total, abs=0.01) == 1.0

    def test_confidence_intervals(self, sample_utilities, sample_attributes):
        """Test that confidence intervals are reasonable."""
        sim = MarketSimulator(sample_utilities, sample_attributes)

        scenarios = [
            {"name": "产品A", "price": 2999, "brand": "美的"},
            {"name": "产品B", "price": 3999, "brand": "西门子"},
        ]

        result = sim.simulate_share(scenarios, include_none=False)

        for _, row in result.iterrows():
            assert row["share_ci_95_lower"] <= row["predicted_share"]
            assert row["predicted_share"] <= row["share_ci_95_upper"]
