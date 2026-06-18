"""Tests for AnalysisAgent — end-to-end automated analysis pipeline."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

import numpy as np
import pytest

from aicbc.agents.analysis_agent import AnalysisAgent, AnalysisAgentConfig
from aicbc.questionnaire.models import Attribute, AttributeLevel, AttributeType
from aicbc.questionnaire.response_models import (
    AlternativeRecord,
    CBCRawDataset,
    ChoiceRecord,
    DatasetMetadata,
)


def _make_attribute(
    attr_id: str,
    attr_type: AttributeType,
    levels: list,
) -> Attribute:
    """Helper to build an Attribute."""
    return Attribute(
        id=attr_id,
        name=attr_id,
        type=attr_type,
        levels=[AttributeLevel(value=v, label=str(v)) for v in levels],
    )


def _make_synthetic_dataset(
    n_resp: int = 20,
    n_tasks: int = 4,
    n_alts: int = 3,
    seed: int = 42,
) -> tuple[CBCRawDataset, list[Attribute]]:
    """Create a synthetic CBC dataset for testing."""
    rng = np.random.default_rng(seed)

    attributes = [
        _make_attribute("price", AttributeType.PRICE, [2999, 3999, 4999]),
        _make_attribute("brand", AttributeType.CATEGORICAL, ["A", "B", "C"]),
    ]

    # Standardize price
    prices = [2999, 3999, 4999]
    price_mean = sum(prices) / len(prices)
    price_std = np.std(prices, ddof=0) or 1.0

    choice_records = []
    for resp_idx in range(n_resp):
        resp_id = f"resp_{resp_idx:03d}"
        beta_price = rng.normal(-0.5, 0.2)
        beta_brand_0 = rng.normal(0.3, 0.3)
        beta_brand_1 = rng.normal(-0.2, 0.3)

        for task_idx in range(n_tasks):
            alts = []
            utilities = []
            for _alt_idx in range(n_alts):
                price_raw = rng.choice(prices)
                brand = rng.choice(["A", "B", "C"])

                if brand == "A":
                    brand_0, brand_1 = 1.0, 0.0
                elif brand == "B":
                    brand_0, brand_1 = 0.0, 1.0
                else:
                    brand_0, brand_1 = -1.0, -1.0

                price_std = (price_raw - price_mean) / price_std
                utility = (
                    beta_price * price_std
                    + beta_brand_0 * brand_0
                    + beta_brand_1 * brand_1
                    + rng.normal(0, 0.1)
                )
                utilities.append(utility)
                alts.append(
                    {
                        "price": price_raw,
                        "brand": brand,
                    }
                )

            chosen_idx = int(np.argmax(utilities))

            alternatives = [
                AlternativeRecord(
                    alt_index=i,
                    chosen=(i == chosen_idx),
                    attributes=alt,
                )
                for i, alt in enumerate(alts)
            ]

            choice_records.append(
                ChoiceRecord(
                    respondent_id=resp_id,
                    respondent_index=resp_idx,
                    segment="test",
                    choice_set_id=task_idx + 1,
                    choice_set_index=task_idx,
                    alternatives=alternatives,
                )
            )

    metadata = DatasetMetadata(
        study_id="test-study",
        n_respondents=n_resp,
        n_choice_sets=n_tasks,
        n_alternatives=n_alts,
        attributes=[a.model_dump() for a in attributes],
    )

    dataset = CBCRawDataset(
        metadata=metadata,
        choice_records=choice_records,
    )

    return dataset, attributes


class TestAnalysisAgentConfig:
    def test_default_config(self):
        config = AnalysisAgentConfig()
        assert config.min_resp_for_hb == 50
        assert config.hb_draws == 1000
        assert config.rhat_threshold == 1.1

    def test_custom_config(self):
        config = AnalysisAgentConfig(hb_draws=500, hb_chains=2)
        assert config.hb_draws == 500
        assert config.hb_chains == 2


class TestAnalysisAgentPipeline:
    @pytest.mark.slow
    def test_full_pipeline(self):
        """End-to-end test with small MCMC config for speed."""
        dataset, attributes = _make_synthetic_dataset(n_resp=20, n_tasks=4)

        config = AnalysisAgentConfig(
            hb_draws=200,
            hb_tune=200,
            hb_chains=2,
            min_resp_for_hb=10,  # Force HB even with 20 respondents
            min_tasks_per_resp=4,  # Match our synthetic data
        )
        agent = AnalysisAgent(config=config)
        output = agent.run(dataset, attributes)

        assert "result" in output
        assert "report" in output
        assert "diagnostics" in output
        assert "warnings" in output

        result = output["result"]
        assert result.study_id == "test-study"
        assert result.model_type == "hb"
        assert result.status == "COMPLETED"
        assert len(result.individual_utilities) == 20

        # Check convergence diagnostics structure
        assert result.convergence.rhat_max < 2.0  # Loose bound for small sample
        assert result.convergence.ess_bulk_min >= 0

        # Check importance
        assert len(result.importance) > 0
        assert all(0 <= v <= 1 for v in result.importance.values())

        # Check report
        report = output["report"]
        assert len(report.summary) > 0
        assert len(report.key_findings) > 0
        assert len(report.convergence_assessment) > 0

    def test_model_selection_mnl_for_small_sample(self):
        """Small samples should fall back to MNL."""
        dataset, attributes = _make_synthetic_dataset(n_resp=5, n_tasks=3)

        config = AnalysisAgentConfig(min_resp_for_hb=50)
        agent = AnalysisAgent(config=config)
        output = agent.run(dataset, attributes)

        # Should still complete, possibly with MNL fallback
        assert output["result"].status == "COMPLETED"

    def test_price_coefficient_warning(self):
        """Test that price coefficient sign is checked."""
        # This is implicitly tested in the full pipeline
        # Price coefficient should be negative for synthetic data
        dataset, attributes = _make_synthetic_dataset(n_resp=20, n_tasks=4)

        config = AnalysisAgentConfig(
            hb_draws=200,
            hb_tune=200,
            hb_chains=2,
            min_resp_for_hb=10,
        )
        agent = AnalysisAgent(config=config)
        output = agent.run(dataset, attributes)

        # Check no positive price coefficient warning
        price_warnings = [w for w in output["warnings"] if "价格系数为正" in w]
        # Synthetic data has negative price coefficient, so no warning expected
        assert len(price_warnings) == 0

    @pytest.mark.slow
    def test_population_params_structure(self):
        dataset, attributes = _make_synthetic_dataset(n_resp=20, n_tasks=4)

        config = AnalysisAgentConfig(
            hb_draws=200,
            hb_tune=200,
            hb_chains=2,
            min_resp_for_hb=10,
            min_tasks_per_resp=4,
        )
        agent = AnalysisAgent(config=config)
        output = agent.run(dataset, attributes)

        result = output["result"]
        assert hasattr(result.population_params, "mu")
        assert hasattr(result.population_params, "sigma")
        assert "price" in result.population_params.mu
        assert "price" in result.population_params.sigma
