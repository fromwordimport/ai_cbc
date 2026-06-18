"""Unit tests for the HB (Hierarchical Bayes) engine.

Tests cover:
- Model building and structure
- MCMC sampling with small synthetic data
- Convergence diagnostics
- Population and individual parameter extraction
- Effects coding compatibility
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.slow]

import numpy as np
import pandas as pd
import pytest

from aicbc.analysis.engines.hb_engine import HBConfig, HBEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_choice_data() -> pd.DataFrame:
    """Create a small synthetic CBC dataset for testing.

    20 respondents, 4 choice sets each, 3 alternatives per set.
    2 attributes: price (continuous) and brand (3 levels -> 2 params).
    Total parameters: 3.
    """
    rng = np.random.default_rng(42)
    n_resp = 20
    n_tasks = 4
    n_alts = 3

    rows = []
    for resp_idx in range(n_resp):
        resp_id = f"resp_{resp_idx:03d}"
        # True individual coefficients
        beta_price = rng.normal(-0.5, 0.2)
        beta_brand_0 = rng.normal(0.3, 0.3)
        beta_brand_1 = rng.normal(-0.2, 0.3)

        for task_idx in range(n_tasks):
            # Generate random alternatives
            utilities = []
            for alt_idx in range(n_alts):
                price = rng.choice([2999, 3999, 4999])
                brand = rng.choice([0, 1, 2])

                # Effects coding for brand
                if brand == 0:
                    brand_0, brand_1 = 1.0, 0.0
                elif brand == 1:
                    brand_0, brand_1 = 0.0, 1.0
                else:
                    brand_0, brand_1 = -1.0, -1.0

                # Standardized price (mean=3999, std~816)
                price_std = (price - 3999) / 816.0

                utility = (
                    beta_price * price_std
                    + beta_brand_0 * brand_0
                    + beta_brand_1 * brand_1
                    + rng.normal(0, 0.1)  # Gumbel noise approximation
                )
                utilities.append((alt_idx, utility, price_std, brand_0, brand_1))

            # Choose alternative with highest utility
            chosen_idx = max(range(n_alts), key=lambda i: utilities[i][1])

            for alt_idx, _, price_std, brand_0, brand_1 in utilities:
                rows.append(
                    {
                        "resp_id": resp_id,
                        "resp_index": resp_idx,
                        "task_id": task_idx,
                        "task_index": task_idx,
                        "alt_id": alt_idx,
                        "chosen": 1 if alt_idx == chosen_idx else 0,
                        "price": price_std,
                        "brand_0": brand_0,
                        "brand_1": brand_1,
                    }
                )

    return pd.DataFrame(rows)


@pytest.fixture
def small_config() -> HBConfig:
    """Small MCMC config for fast tests."""
    return HBConfig(
        n_draws=200,
        n_tune=200,
        n_chains=2,
        target_accept=0.9,
        random_seed=42,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHBEngineBuild:
    """Test model building without fitting."""

    def test_build_model_creates_pymc_model(self, synthetic_choice_data: pd.DataFrame):
        engine = HBEngine()
        model = engine.build_model(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        assert model is not None
        var_names = [v.name for v in model.value_vars]
        det_names = [v.name for v in model.deterministics]
        assert "mu" in var_names
        assert "sigma" in det_names
        assert "z" in var_names
        assert "beta" in det_names

    def test_preprocess_creates_correct_task_count(self, synthetic_choice_data: pd.DataFrame):
        engine = HBEngine()
        engine._preprocess(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
            resp_id_col="resp_id",
            task_id_col="task_id",
            choice_col="chosen",
        )
        # 20 respondents * 4 tasks = 80 tasks
        assert len(engine._tasks) == 80
        # Each task should have 3 alternatives
        for task in engine._tasks:
            assert task["X"].shape == (3, 3)  # 3 alts, 3 features


class TestHBEngineFit:
    """Test model fitting."""

    @pytest.mark.slow
    def test_fit_returns_result(self, synthetic_choice_data: pd.DataFrame, small_config: HBConfig):
        engine = HBEngine(config=small_config)
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        from aicbc.analysis.engines.hb_engine import HBResult

        assert isinstance(result, HBResult)
        assert hasattr(result, "converged")
        assert hasattr(result, "rhat_max")
        assert hasattr(result, "individual_utilities")

    @pytest.mark.slow
    def test_population_mu_has_correct_keys(
        self, synthetic_choice_data: pd.DataFrame, small_config: HBConfig
    ):
        engine = HBEngine(config=small_config)
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        assert set(result.population_mu.keys()) == {"price", "brand_0", "brand_1"}

    @pytest.mark.slow
    def test_individual_utilities_has_all_respondents(
        self, synthetic_choice_data: pd.DataFrame, small_config: HBConfig
    ):
        engine = HBEngine(config=small_config)
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        resp_ids = synthetic_choice_data["resp_id"].unique()
        assert len(result.individual_utilities) == len(resp_ids)
        for resp_id in resp_ids:
            assert resp_id in result.individual_utilities

    @pytest.mark.slow
    def test_price_coefficient_is_negative(
        self, synthetic_choice_data: pd.DataFrame, small_config: HBConfig
    ):
        """Price coefficient should be negative (higher price = lower utility)."""
        engine = HBEngine(config=small_config)
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        # Population mean should be negative
        assert result.population_mu["price"] < 0

    @pytest.mark.slow
    def test_convergence_diagnostics_structure(
        self, synthetic_choice_data: pd.DataFrame, small_config: HBConfig
    ):
        engine = HBEngine(config=small_config)
        result = engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        diag = result.diagnostics
        assert diag is not None
        assert "rhat_max" in diag
        assert "ess_bulk_min" in diag
        assert "ess_tail_min" in diag
        assert "converged" in diag
        assert "reliable_ess" in diag
        assert "divergences" in diag
        assert "tree_depth_max" in diag
        assert isinstance(diag["converged"], bool)
        assert isinstance(diag["reliable_ess"], bool)


class TestHBEngineTrace:
    """Test trace and posterior extraction."""

    @pytest.mark.slow
    def test_trace_has_posterior(self, synthetic_choice_data: pd.DataFrame, small_config: HBConfig):
        engine = HBEngine(config=small_config)
        engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        # ArviZ 1.x uses DataTree; check for posterior group
        assert hasattr(engine.trace, "posterior")
        assert "mu" in engine.trace.posterior.data_vars
        assert "beta" in engine.trace.posterior.data_vars

    @pytest.mark.slow
    def test_individual_distribution_returns_dataframe(
        self, synthetic_choice_data: pd.DataFrame, small_config: HBConfig
    ):
        engine = HBEngine(config=small_config)
        engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        df = engine.get_individual_distribution(resp_id="resp_000")
        assert isinstance(df, pd.DataFrame)
        assert "beta" in df.columns


class TestHBEngineConfig:
    """Test configuration options."""

    def test_default_config(self):
        config = HBConfig()
        assert config.n_draws == 1000
        assert config.n_tune == 1000
        assert config.n_chains == 4
        assert config.target_accept == 0.8
        assert config.lkj_eta == 2.0

    def test_custom_config(self):
        config = HBConfig(n_draws=500, n_chains=2, lkj_eta=1.0)
        assert config.n_draws == 500
        assert config.n_chains == 2
        assert config.lkj_eta == 1.0


class TestHBEnginePredict:
    """Test prediction methods."""

    @pytest.mark.slow
    def test_predict_probabilities_sum_to_one(
        self, synthetic_choice_data: pd.DataFrame, small_config: HBConfig
    ):
        engine = HBEngine(config=small_config)
        engine.fit(
            data=synthetic_choice_data,
            feature_cols=["price", "brand_0", "brand_1"],
        )
        scenarios = [
            {"price": 0.0, "brand_0": 1.0, "brand_1": 0.0},
            {"price": 0.0, "brand_0": 0.0, "brand_1": 1.0},
            {"price": 0.0, "brand_0": -1.0, "brand_1": -1.0},
        ]
        probs = engine.predict_probabilities(scenarios)
        assert len(probs) == 3
        assert np.isclose(probs.sum(), 1.0)
        assert np.all(probs >= 0)
