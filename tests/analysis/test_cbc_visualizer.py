import pytest

from aicbc.analysis.cbc_visualizer import (
    build_dashboard_option,
    build_importance_chart_option,
    build_importance_pie_option,
    build_market_share_option,
    build_utility_distribution_option,
    build_wtp_chart_option,
)
from aicbc.analysis.models import (
    ImportanceResponse,
    ImportanceStats,
    MarketSimResponse,
    ScenarioShare,
    WTPAttribute,
    WTPComparison,
    WTPResponse,
)


@pytest.fixture
def importance():
    return ImportanceResponse(
        overall={
            "price": ImportanceStats(
                mean=0.4,
                std=0.05,
                median=0.4,
                min=0.1,
                max=0.7,
                q25=0.35,
                q75=0.45,
                ci_95_lower=0.31,
                ci_95_upper=0.49,
            ),
            "brand": ImportanceStats(
                mean=0.3,
                std=0.04,
                median=0.3,
                min=0.1,
                max=0.5,
                q25=0.25,
                q75=0.35,
                ci_95_lower=0.22,
                ci_95_upper=0.38,
            ),
        }
    )


@pytest.fixture
def market_sim():
    return MarketSimResponse(
        scenarios=[
            ScenarioShare(
                name="A", predicted_share=0.6, share_ci_95_lower=0.5, share_ci_95_upper=0.7
            ),
            ScenarioShare(
                name="B", predicted_share=0.4, share_ci_95_lower=0.3, share_ci_95_upper=0.5
            ),
        ]
    )


@pytest.fixture
def wtp():
    return WTPResponse(
        wtp_values={
            "brand": WTPAttribute(
                comparisons=[
                    WTPComparison(
                        from_level="brand_0",
                        to_level="brand_1",
                        wtp_mean=500.0,
                        wtp_median=480.0,
                        wtp_std=50.0,
                        ci_95_lower=400.0,
                        ci_95_upper=600.0,
                        n_valid=100,
                    )
                ]
            )
        },
        price_coefficient_summary={
            "mean": -0.5,
            "median": -0.5,
            "std": 0.1,
            "negative_rate": 0.95,
            "n_positive_outliers": 0,
        },
    )


def test_importance_bar_option(importance):
    opt = build_importance_chart_option(importance)
    assert opt["xAxis"]["data"] == ["price", "brand"]
    assert opt["series"][0]["type"] == "bar"
    assert opt["series"][0]["data"][0]["value"] == 40.0


def test_importance_pie_option(importance):
    opt = build_importance_pie_option(importance)
    assert opt["series"][0]["type"] == "pie"
    names = [d["name"] for d in opt["series"][0]["data"]]
    assert names == ["price", "brand"]


def test_utility_distribution_option():
    utilities = {
        "p1": {"price": -0.5, "brand_0": 0.1},
        "p2": {"price": -0.3, "brand_0": 0.2},
        "p3": {"price": -0.7, "brand_0": 0.15},
    }
    opt = build_utility_distribution_option(utilities)
    assert opt["series"][0]["type"] == "boxplot"
    assert len(opt["series"][0]["data"]) == 2


def test_market_share_option(market_sim):
    opt = build_market_share_option(market_sim)
    assert opt["xAxis"]["data"] == ["A", "B"]
    assert opt["series"][0]["data"] == [60.0, 40.0]


def test_wtp_chart_option(wtp):
    opt = build_wtp_chart_option(wtp)
    assert opt["series"][0]["type"] == "bar"
    assert opt["series"][0]["data"] == [500.0]


def test_dashboard_option(importance, market_sim):
    opt = build_dashboard_option(importance, market_sim)
    assert "importance_bar" in opt
    assert "importance_pie" in opt
    assert "market_share" in opt


def test_empty_importance_returns_empty():
    assert build_importance_chart_option(ImportanceResponse(overall={})) == {}


def test_empty_market_sim_returns_empty():
    assert build_market_share_option(MarketSimResponse(scenarios=[])) == {}
