import pytest

from aicbc.analysis.models import (
    AnalysisResultResponse,
    ConvergenceDiagnostics,
    ImportanceResponse,
    ImportanceStats,
    MarketSimResponse,
    PopulationParams,
    PriceCoefficientSummary,
    ScenarioShare,
    WTPAttribute,
    WTPComparison,
    WTPResponse,
)
from aicbc.analysis.report_builder import ReportBuilder, build_report


@pytest.fixture
def sample_result():
    return AnalysisResultResponse(
        analysis_id="ar-test-001",
        study_id="dishwasher-test",
        status="COMPLETED",
        model_type="hb",
        convergence=ConvergenceDiagnostics(
            rhat_max=1.05,
            rhat_by_param={"price": 1.02},
            ess_bulk_min=200.0,
            ess_tail_min=180.0,
            ess_by_param={"price": 250.0},
            converged=True,
            reliable_ess=True,
            divergences=0,
            tree_depth_max=10,
        ),
        population_params=PopulationParams(mu={"price": -0.5}, sigma={"price": 0.1}),
        individual_utilities={"p1": {"price": -0.4}},
        importance={"price": 0.4},
        wtp={},
        processing_time_seconds=12.34,
    )


@pytest.fixture
def sample_importance():
    return ImportanceResponse(
        overall={
            "price": ImportanceStats(
                mean=0.4,
                std=0.05,
                median=0.4,
                min=0.3,
                max=0.5,
                q25=0.35,
                q75=0.45,
                ci_95_lower=0.31,
                ci_95_upper=0.49,
            ),
            "brand": ImportanceStats(
                mean=0.3,
                std=0.04,
                median=0.3,
                min=0.2,
                max=0.4,
                q25=0.27,
                q75=0.33,
                ci_95_lower=0.22,
                ci_95_upper=0.38,
            ),
        }
    )


@pytest.fixture
def sample_wtp():
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
        price_coefficient_summary=PriceCoefficientSummary(
            mean=-0.5,
            median=-0.48,
            std=0.1,
            negative_rate=0.95,
            n_positive_outliers=2,
        ),
    )


@pytest.fixture
def sample_market_sim():
    return MarketSimResponse(
        scenarios=[
            ScenarioShare(
                name="产品 A",
                predicted_share=0.6,
                share_ci_95_lower=0.55,
                share_ci_95_upper=0.65,
            ),
            ScenarioShare(
                name="产品 B",
                predicted_share=0.4,
                share_ci_95_lower=0.35,
                share_ci_95_upper=0.45,
            ),
        ]
    )


def test_markdown_report_contains_key_sections(
    sample_result, sample_importance, sample_wtp, sample_market_sim
):
    builder = ReportBuilder(sample_result, sample_importance, sample_wtp, sample_market_sim)
    md = builder.to_markdown()
    assert "# CBC 分析报告" in md
    assert "ar-test-001" in md
    assert "属性重要性" in md
    assert "支付意愿 (WTP)" in md
    assert "市场份额模拟" in md
    assert "R-hat Max" in md


def test_html_report_contains_table_tags(
    sample_result, sample_importance, sample_wtp, sample_market_sim
):
    builder = ReportBuilder(sample_result, sample_importance, sample_wtp, sample_market_sim)
    html = builder.to_html()
    assert "<html" in html
    assert "</table>" in html
    assert "产品 A" in html


def test_build_report_wrapper(sample_result, sample_importance):
    md = build_report(sample_result, sample_importance, format="markdown")
    assert "CBC 分析报告" in md
    html = build_report(sample_result, sample_importance, format="html")
    assert "<html" in html


def test_unsupported_format_raises(sample_result):
    with pytest.raises(ValueError, match="Unsupported report format"):
        build_report(sample_result, format="pdf")


def test_report_without_optional_results(sample_result):
    builder = ReportBuilder(sample_result)
    md = builder.to_markdown()
    assert "重要性结果不可用" in md
    assert "支付意愿" not in md
    assert "市场份额模拟" not in md


def test_importance_sorted_by_mean(sample_result, sample_importance):
    builder = ReportBuilder(sample_result, sample_importance)
    md = builder.to_markdown()
    price_idx = md.find("price")
    brand_idx = md.find("brand")
    assert price_idx < brand_idx
