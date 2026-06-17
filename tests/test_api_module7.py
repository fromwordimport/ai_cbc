"""Tests for Module 7 endpoints: NL scenario parser, report, visualisation, latent class."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aicbc.analysis.models import (
    AnalysisResultResponse,
    ConvergenceDiagnostics,
    ImportanceResponse,
    ImportanceStats,
    LatentClassResponse,
    MarketSimResponse,
    PriceCoefficientSummary,
    ScenarioShare,
    WTPAttribute,
    WTPComparison,
    WTPResponse,
)
from aicbc.analysis.store import areset_analysis_store, get_analysis_store
from aicbc.config.settings import get_settings
from aicbc.core.store import get_questionnaire_store
from aicbc.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
async def _clean_stores():
    """Reset all in-memory stores before and after each test."""
    settings = get_settings()
    original_debug = settings.debug
    settings.debug = True
    app.state.debug = True
    get_questionnaire_store().clear()
    await areset_analysis_store()
    yield
    get_questionnaire_store().clear()
    await areset_analysis_store()
    settings.debug = original_debug
    app.state.debug = original_debug


@pytest.fixture
def study_id() -> str:
    """Create a default dishwasher study and return its ID."""
    response = client.post(
        "/api/v1/studies",
        json={
            "study_id": "dw-m7-001",
            "product_category": "洗碗机",
            "research_goal": "模块 7 测试",
        },
    )
    assert response.status_code == 201
    return "dw-m7-001"


@pytest.fixture
def mock_analysis(study_id: str) -> str:
    """Store a fake completed analysis result with derived artefacts."""
    analysis_id = "ar-m7-001"
    store = get_analysis_store()
    store.save_result(
        AnalysisResultResponse(
            analysis_id=analysis_id,
            study_id=study_id,
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
            population_params={"mu": {"price": -0.5}, "sigma": {"price": 0.1}},
            individual_utilities={
                "p1": {"price": -0.4, "brand_0": 0.1},
                "p2": {"price": -0.6, "brand_0": 0.2},
            },
            importance={"price": 0.4},
            wtp={},
            processing_time_seconds=12.34,
            completed_at=datetime.now(UTC),
        )
    )
    store.save_importance(
        analysis_id,
        ImportanceResponse(
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
        ),
    )
    store.save_wtp(
        analysis_id,
        WTPResponse(
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
        ),
    )
    store.save_market_sim(
        analysis_id,
        "sim-1",
        MarketSimResponse(
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
        ),
    )
    return analysis_id


class TestParseScenario:
    """Tests for POST /studies/{study_id}/parse-scenario."""

    def test_parse_full_description(self, study_id: str) -> None:
        response = client.post(
            f"/api/v1/studies/{study_id}/parse-scenario",
            json={"text": "美的 2999 元嵌入式 14 套"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "美的 2999 元嵌入式 14 套"
        attrs = data["attributes"]
        assert attrs.get("price") == 2999.0
        assert attrs.get("installation") == "installation_1"
        assert attrs.get("capacity") == "capacity_2"
        assert attrs.get("brand") == "brand_2"

    def test_parse_unknown_study(self) -> None:
        response = client.post(
            "/api/v1/studies/nonexistent/parse-scenario",
            json={"text": "西门子 3999 元"},
        )
        assert response.status_code == 404


class TestReportEndpoint:
    """Tests for GET /studies/{study_id}/analysis/{analysis_id}/report."""

    def test_report_markdown(self, study_id: str, mock_analysis: str) -> None:
        response = client.get(
            f"/api/v1/studies/{study_id}/analysis/{mock_analysis}/report?format=markdown"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        text = response.text
        assert "CBC 分析报告" in text
        assert "属性重要性" in text
        assert "支付意愿 (WTP)" in text
        assert "市场份额模拟" in text

    def test_report_html(self, study_id: str, mock_analysis: str) -> None:
        response = client.get(
            f"/api/v1/studies/{study_id}/analysis/{mock_analysis}/report?format=html"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "<html" in response.text
        assert "</table>" in response.text


class TestVisualizationEndpoint:
    """Tests for GET /studies/{study_id}/analysis/{analysis_id}/visualization."""

    def test_importance_bar_chart(self, study_id: str, mock_analysis: str) -> None:
        response = client.get(
            f"/api/v1/studies/{study_id}/analysis/{mock_analysis}/visualization?chart=importance_bar"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["series"][0]["type"] == "bar"

    def test_utility_distribution_chart(self, study_id: str, mock_analysis: str) -> None:
        response = client.get(
            f"/api/v1/studies/{study_id}/analysis/{mock_analysis}/visualization?chart=utility_distribution"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["series"][0]["type"] == "boxplot"

    def test_market_share_chart(self, study_id: str, mock_analysis: str) -> None:
        response = client.get(
            f"/api/v1/studies/{study_id}/analysis/{mock_analysis}/visualization?chart=market_share"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["series"][0]["type"] == "bar"
        assert data["xAxis"]["data"] == ["产品 A", "产品 B"]

    def test_invalid_chart(self, study_id: str, mock_analysis: str) -> None:
        response = client.get(
            f"/api/v1/studies/{study_id}/analysis/{mock_analysis}/visualization?chart=invalid"
        )
        assert response.status_code == 422


class TestLatentClassEndpoint:
    """Tests for latent class endpoints."""

    def test_get_latent_class_result(self, study_id: str) -> None:
        analysis_id = "lc-m7-001"
        store = get_analysis_store()
        store.save_latent_class_result(
            analysis_id,
            LatentClassResponse(
                analysis_id=analysis_id,
                study_id=study_id,
                n_classes=2,
                converged=True,
                rhat_max=1.05,
                ess_bulk_min=500,
                ess_tail_min=500,
                class_probs={"class_0": 0.5, "class_1": 0.5},
                class_utilities={
                    "class_0": {"price": -0.001},
                    "class_1": {"price": -0.002},
                },
                individual_class_probs={"p1": {"class_0": 0.9, "class_1": 0.1}},
                assigned_class={"p1": "class_0"},
                processing_time_seconds=60.0,
                completed_at=datetime.now(UTC),
            ).model_dump(mode="json"),
        )
        response = client.get(f"/api/v1/studies/{study_id}/analysis/{analysis_id}/latent-class")
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_id"] == analysis_id
        assert data["n_classes"] == 2
        assert data["assigned_class"]["p1"] == "class_0"

    def test_get_latent_class_wrong_study(self, study_id: str) -> None:
        analysis_id = "lc-m7-002"
        store = get_analysis_store()
        store.save_latent_class_result(
            analysis_id,
            LatentClassResponse(
                analysis_id=analysis_id,
                study_id="other-study",
                n_classes=2,
                converged=True,
                rhat_max=1.05,
                ess_bulk_min=500,
                ess_tail_min=500,
                class_probs={"class_0": 1.0},
                class_utilities={"class_0": {"price": -0.001}},
                individual_class_probs={},
                assigned_class={},
                processing_time_seconds=1.0,
                completed_at=datetime.now(UTC),
            ).model_dump(mode="json"),
        )
        response = client.get(f"/api/v1/studies/{study_id}/analysis/{analysis_id}/latent-class")
        assert response.status_code == 404

    def test_post_latent_class_enqueues_job(self, study_id: str) -> None:
        """POST should queue a latent class job without running sampling."""
        mock_result = MagicMock()
        mock_result.id = "fake-celery-id"
        with patch("aicbc.analysis.routes.run_latent_class_task") as mock_task:
            mock_task.delay.return_value = mock_result
            response = client.post(
                f"/api/v1/studies/{study_id}/analysis/latent-class",
                json={"n_classes": 2, "n_draws": 100, "n_tune": 100},
            )
        assert response.status_code == 202
        data = response.json()
        assert data["model_type"] == "latent_class"
        assert data["status"] == "QUEUED"
        assert "analysis_id" in data
        mock_task.delay.assert_called_once()
