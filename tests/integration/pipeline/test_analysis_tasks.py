"""Tests for aicbc.analysis.tasks.

These tests mock the heavy engines and stores to exercise the task orchestration
logic without running MCMC sampling.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from aicbc.analysis.tasks import run_analysis_task, run_latent_class_task
from aicbc.questionnaire.models import Attribute, AttributeLevel, AttributeType


def _make_price_attr() -> Attribute:
    return Attribute(
        id="price",
        name="价格",
        type=AttributeType.PRICE,
        levels=[
            AttributeLevel(value="2999", label="2999"),
            AttributeLevel(value="3999", label="3999"),
        ],
    )


def _make_brand_attr() -> Attribute:
    return Attribute(
        id="brand",
        name="品牌",
        type=AttributeType.CATEGORICAL,
        levels=[
            AttributeLevel(value="A", label="A"),
            AttributeLevel(value="B", label="B"),
        ],
    )


def _make_study() -> SimpleNamespace:
    study = SimpleNamespace()
    study.study_id = "study-001"
    study.attributes = [_make_price_attr(), _make_brand_attr()]
    return study


def _make_dataset() -> SimpleNamespace:
    dataset = SimpleNamespace()
    dataset.choice_records = [
        SimpleNamespace(
            respondent_id="r1",
            segment="A",
        ),
        SimpleNamespace(
            respondent_id="r2",
            segment="B",
        ),
    ]
    return dataset


def _make_engine_result() -> SimpleNamespace:
    return SimpleNamespace(
        population_mu={"price": -0.5, "brand_0": 0.3},
        population_sigma={"price": 0.1, "brand_0": 0.1},
        individual_utilities={
            "r1": {"price": -0.5, "brand_0": 0.3},
            "r2": {"price": -0.4, "brand_0": 0.2},
        },
        converged=True,
        rhat_max=1.05,
        ess_bulk_min=100.0,
        ess_tail_min=100.0,
        diagnostics={
            "rhat_by_param": {"price": 1.01},
            "ess_by_param": {"price": 150.0},
            "reliable_ess": True,
            "divergences": 0,
            "tree_depth_max": 10,
        },
    )


def _make_latent_class_result() -> SimpleNamespace:
    return SimpleNamespace(
        converged=True,
        rhat_max=1.05,
        ess_bulk_min=100.0,
        ess_tail_min=100.0,
        diagnostics={
            "rhat_by_param": {"price": 1.01},
            "ess_by_param": {"price": 150.0},
            "reliable_ess": True,
            "divergences": 0,
            "tree_depth_max": 10,
        },
        class_probs={"class_0": 0.6, "class_1": 0.4},
        class_utilities={
            "class_0": {"price": -0.5, "brand_0": 0.3},
            "class_1": {"price": -0.3, "brand_0": 0.1},
        },
        individual_class_probs={
            "r1": {"class_0": 0.7, "class_1": 0.3},
            "r2": {"class_0": 0.4, "class_1": 0.6},
        },
        assigned_class={"r1": "class_0", "r2": "class_1"},
    )


@pytest.fixture
def mock_stores():
    """Patch stores used by analysis tasks."""
    q_store = MagicMock()
    r_store = MagicMock()
    a_store = MagicMock()

    q_store.get_study.return_value = _make_study()
    r_store.get_dataset.return_value = _make_dataset()
    a_store.update_job_status.return_value = SimpleNamespace(
        analysis_id="analysis-001",
        study_id="study-001",
        status="RUNNING",
        started_at=datetime.now(UTC),
    )

    with (
        patch("aicbc.core.store.get_questionnaire_store", return_value=q_store),
        patch("aicbc.core.store.get_response_store", return_value=r_store),
        patch("aicbc.analysis.store.get_analysis_store", return_value=a_store),
    ):
        yield q_store, r_store, a_store


@pytest.fixture
def mock_preprocessing():
    """Patch preprocessing helpers."""
    df_long = pd.DataFrame(
        {
            "respondent_id": ["r1", "r1", "r2", "r2"],
            "choice_set_id": [1, 1, 1, 1],
            "alt_index": [0, 1, 0, 1],
            "chosen": [1, 0, 1, 0],
            "price": [-1.0, 1.0, -1.0, 1.0],
            "brand_0": [1.0, -1.0, 1.0, -1.0],
        }
    )

    with (
        patch(
            "aicbc.analysis.preprocessing.validate_dataset",
            return_value={"valid": True, "errors": []},
        ),
        patch("aicbc.analysis.preprocessing.to_long_format", return_value=df_long),
        patch(
            "aicbc.analysis.preprocessing.get_feature_columns", return_value=["price", "brand_0"]
        ),
    ):
        yield


@pytest.fixture
def mock_importance():
    """Patch importance helpers."""
    importance_df = pd.DataFrame(
        {"price": [0.6, 0.5], "brand_0": [0.4, 0.5]},
        index=["r1", "r2"],
    )
    importance_agg = pd.DataFrame(
        {
            "mean": [0.55, 0.45],
            "std": [0.05, 0.05],
            "median": [0.55, 0.45],
            "min": [0.5, 0.4],
            "max": [0.6, 0.5],
            "q25": [0.52, 0.42],
            "q75": [0.58, 0.48],
        },
        index=["price", "brand_0"],
    )

    with (
        patch("aicbc.analysis.results.importance.compute_importance", return_value=importance_df),
        patch(
            "aicbc.analysis.results.importance.aggregate_importance", return_value=importance_agg
        ),
    ):
        yield


@pytest.fixture
def mock_wtp():
    """Patch WTP calculator."""
    wtp_calc = MagicMock()
    wtp_calc.compute_all_wtp.return_value = {
        "brand": {
            "comparisons": [
                {
                    "from_level": "A",
                    "to_level": "B",
                    "wtp_mean": 100.0,
                    "wtp_median": 100.0,
                    "wtp_std": 10.0,
                    "ci_95_lower": 80.0,
                    "ci_95_upper": 120.0,
                    "n_valid": 2,
                }
            ]
        }
    }
    wtp_calc.price_coefficient_summary.return_value = {
        "mean": -0.5,
        "median": -0.5,
        "std": 0.1,
        "negative_rate": 1.0,
        "n_positive_outliers": 0,
    }

    with patch("aicbc.analysis.results.wtp.WTPCalculator", return_value=wtp_calc):
        yield wtp_calc


class TestRunAnalysisTask:
    @patch("aicbc.analysis.engines.hb_engine.HBEngine")
    @patch("aicbc.analysis.engines.hb_engine.HBConfig")
    def test_hb_success(
        self,
        mock_hb_config_cls,
        mock_hb_engine_cls,
        mock_stores,
        mock_preprocessing,
        mock_importance,
        mock_wtp,
    ):
        mock_hb_engine_cls.return_value.fit.return_value = _make_engine_result()

        result = run_analysis_task(
            "study-001",
            "analysis-001",
            "hb",
            json.dumps({"n_draws": 500, "n_tune": 500, "n_chains": 2, "target_accept": 0.9}),
        )

        assert result["status"] == "COMPLETED"
        assert result["analysis_id"] == "analysis-001"

        _, _, a_store = mock_stores
        a_store.update_job_status.assert_any_call("analysis-001", "RUNNING", progress=0.0)
        a_store.update_job_status.assert_any_call("analysis-001", "COMPLETED", progress=100.0)
        a_store.save_result.assert_called_once()
        a_store.save_convergence.assert_called_once()
        a_store.save_importance.assert_called_once()
        a_store.save_wtp.assert_called_once()

    @patch("aicbc.analysis.engines.mnl_engine.MNLEngine")
    def test_mnl_success(
        self,
        mock_mnl_engine_cls,
        mock_stores,
        mock_preprocessing,
        mock_importance,
        mock_wtp,
    ):
        mock_mnl_engine_cls.return_value.fit.return_value = _make_engine_result()

        result = run_analysis_task(
            "study-001",
            "analysis-001",
            "mnl",
            json.dumps({}),
        )

        assert result["status"] == "COMPLETED"

    @patch("aicbc.analysis.engines.hb_engine.HBEngine")
    @patch("aicbc.analysis.engines.hb_engine.HBConfig")
    def test_latent_class_fallback_to_hb(
        self,
        mock_hb_config_cls,
        mock_hb_engine_cls,
        mock_stores,
        mock_preprocessing,
        mock_importance,
        mock_wtp,
    ):
        mock_hb_engine_cls.return_value.fit.return_value = _make_engine_result()

        result = run_analysis_task(
            "study-001",
            "analysis-001",
            "latent_class",
            json.dumps({}),
        )

        assert result["status"] == "COMPLETED"

    def test_missing_study_raises(self, mock_stores, mock_preprocessing):
        q_store, _, a_store = mock_stores
        q_store.get_study.return_value = None

        with pytest.raises(ValueError, match="Study"):
            run_analysis_task("study-001", "analysis-001", "hb", json.dumps({}))

        a_store.update_job_status.assert_any_call("analysis-001", "FAILED", progress=0.0)

    def test_missing_dataset_raises(self, mock_stores, mock_preprocessing):
        _, r_store, a_store = mock_stores
        r_store.get_dataset.return_value = None

        with pytest.raises(ValueError, match="No response dataset"):
            run_analysis_task("study-001", "analysis-001", "hb", json.dumps({}))

        a_store.update_job_status.assert_any_call("analysis-001", "FAILED", progress=0.0)

    def test_validation_failure_raises(self, mock_stores, mock_preprocessing):
        _, _, a_store = mock_stores
        with (
            patch(
                "aicbc.analysis.preprocessing.validate_dataset",
                return_value={"valid": False, "errors": ["bad data"]},
            ),
            pytest.raises(ValueError, match="Dataset validation failed"),
        ):
            run_analysis_task("study-001", "analysis-001", "hb", json.dumps({}))

        a_store.update_job_status.assert_any_call("analysis-001", "FAILED", progress=0.0)

    @patch("aicbc.analysis.engines.hb_engine.HBEngine")
    @patch("aicbc.analysis.engines.hb_engine.HBConfig")
    @patch("aicbc.core.models.db_documents.DeadLetterDocument")
    def test_dead_letter_saved_on_failure(
        self,
        mock_doc_cls,
        mock_hb_config_cls,
        mock_hb_engine_cls,
        mock_stores,
        mock_preprocessing,
    ):
        mock_hb_engine_cls.return_value.fit.side_effect = RuntimeError("boom")
        mock_doc_cls.return_value.insert = AsyncMock()

        with pytest.raises(RuntimeError):
            run_analysis_task(
                "study-001",
                "analysis-001",
                "hb",
                json.dumps({}),
            )

        mock_doc_cls.assert_called_once()
        _, kwargs = mock_doc_cls.call_args
        assert kwargs["task_name"] == "aicbc.analysis.run_analysis_task"
        assert kwargs["analysis_id"] == "analysis-001"
        assert kwargs["study_id"] == "study-001"
        assert "RuntimeError: boom" in kwargs["exception"]
        mock_doc_cls.return_value.insert.assert_awaited_once()


class TestRunLatentClassTask:
    @patch("aicbc.analysis.engines.latent_class_engine.LatentClassEngine")
    @patch("aicbc.analysis.engines.latent_class_engine.LatentClassConfig")
    def test_success(
        self,
        mock_lc_config_cls,
        mock_lc_engine_cls,
        mock_stores,
        mock_preprocessing,
    ):
        mock_lc_engine_cls.return_value.fit.return_value = _make_latent_class_result()

        result = run_latent_class_task(
            "study-001",
            "analysis-001",
            json.dumps({"n_classes": 2, "n_draws": 100, "n_tune": 100, "n_chains": 2}),
        )

        assert result["status"] == "COMPLETED"
        assert result["analysis_id"] == "analysis-001"

        _, _, a_store = mock_stores
        a_store.save_latent_class_result.assert_called_once()
        a_store.save_result.assert_called_once()
        a_store.save_convergence.assert_called_once()
        a_store.update_job_status.assert_any_call("analysis-001", "COMPLETED", progress=100.0)

    def test_missing_study_raises(self, mock_stores, mock_preprocessing):
        q_store, _, a_store = mock_stores
        q_store.get_study.return_value = None

        with pytest.raises(ValueError, match="Study"):
            run_latent_class_task("study-001", "analysis-001", json.dumps({}))

        a_store.update_job_status.assert_any_call("analysis-001", "FAILED", progress=0.0)
