"""Unit tests for the MNL (Multinomial Logit) engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aicbc.analysis.engines.mnl_engine import MNLEngine, MNLResult


@pytest.fixture
def synthetic_choice_data() -> pd.DataFrame:
    """Create a small synthetic CBC dataset for MNL testing.

    30 respondents, 3 choice sets each, 3 alternatives per set.
    2 attributes: price (continuous) and brand (3 levels -> 2 params).
    """
    rng = np.random.default_rng(42)
    n_resp = 30
    n_tasks = 3
    n_alts = 3

    rows = []
    for resp_idx in range(n_resp):
        resp_id = f"resp_{resp_idx:03d}"

        for task_idx in range(n_tasks):
            utilities = []
            alts = []
            for alt_idx in range(n_alts):
                price = rng.choice([2999, 3999, 4999])
                brand = rng.choice([0, 1, 2])

                if brand == 0:
                    brand_0, brand_1 = 1.0, 0.0
                elif brand == 1:
                    brand_0, brand_1 = 0.0, 1.0
                else:
                    brand_0, brand_1 = -1.0, -1.0

                price_std = (price - 3999) / 816.0

                # True population coefficients: price=-0.5, brand_0=0.3, brand_1=-0.2
                utility = (
                    -0.5 * price_std
                    + 0.3 * brand_0
                    + (-0.2) * brand_1
                    + rng.normal(0, 0.1)
                )
                utilities.append(utility)
                alts.append({
                    "resp_id": resp_id,
                    "task_id": task_idx,
                    "alt_id": alt_idx,
                    "price": price_std,
                    "brand_0": brand_0,
                    "brand_1": brand_1,
                })

            chosen_idx = int(np.argmax(utilities))

            for i, alt in enumerate(alts):
                alt["chosen"] = 1 if i == chosen_idx else 0
                rows.append(alt)

    return pd.DataFrame(rows)


class TestMNLEngine:
    def test_fit_returns_result(self, synthetic_choice_data: pd.DataFrame):
        engine = MNLEngine()
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        assert isinstance(result, MNLResult)
        assert result.converged
        assert len(result.population_mu) == 3

    def test_population_mu_has_expected_signs(
        self, synthetic_choice_data: pd.DataFrame
    ):
        """Price coefficient should be negative, brand_0 positive."""
        engine = MNLEngine()
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        assert result.population_mu["price"] < 0
        assert result.population_mu["brand_0"] > 0

    def test_individual_utilities_all_same(
        self, synthetic_choice_data: pd.DataFrame
    ):
        """MNL has no heterogeneity: all respondents share same utilities."""
        engine = MNLEngine()
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        resp_ids = synthetic_choice_data["resp_id"].unique()
        assert len(result.individual_utilities) == len(resp_ids)

        # All should have the same values (population mu)
        first_util = list(result.individual_utilities.values())[0]
        for util in result.individual_utilities.values():
            assert util == first_util

    def test_model_fit_statistics(self, synthetic_choice_data: pd.DataFrame):
        engine = MNLEngine()
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        fit = engine.get_model_fit()
        assert fit["log_likelihood"] < 0
        assert fit["mc_fadden_r2"] > 0
        assert fit["mc_fadden_r2"] < 1
        assert fit["aic"] > 0
        assert fit["bic"] > 0
        assert fit["n_obs"] > 0
        assert fit["n_params"] == 3

    def test_coef_table_structure(self, synthetic_choice_data: pd.DataFrame):
        engine = MNLEngine()
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        assert result.coef_table is not None
        assert len(result.coef_table) == 3
        assert "parameter" in result.coef_table.columns
        assert "coef" in result.coef_table.columns
        assert "p_value" in result.coef_table.columns
        assert "significant" in result.coef_table.columns

    def test_predict_probabilities(self, synthetic_choice_data: pd.DataFrame):
        engine = MNLEngine()
        engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        probs = engine.predict_probabilities(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        assert len(probs) == len(synthetic_choice_data)
        assert np.all(probs >= 0)
        assert np.all(probs <= 1)

    def test_fit_before_predict_raises(self, synthetic_choice_data: pd.DataFrame):
        engine = MNLEngine()
        with pytest.raises(RuntimeError):
            engine.predict_probabilities(data=synthetic_choice_data)
