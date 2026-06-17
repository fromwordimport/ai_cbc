"""Synthetic data parameter recovery tests.

Generates CBC choice data with known ground-truth parameters and verifies
that HB and MNL engines recover them within tolerance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from aicbc.analysis.engines.hb_engine import HBConfig, HBEngine
from aicbc.analysis.engines.mnl_engine import MNLEngine

# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------


def make_synthetic_data(
    n_resp: int = 20,
    n_tasks: int = 8,
    n_alts: int = 3,
    random_seed: int = 42,
    homogeneous: bool = False,
) -> tuple[pd.DataFrame, dict[str, float], dict[str, dict[str, float]]]:
    """Generate synthetic CBC data with known parameters.

    Attributes (effects-coded):
        - brand: 3 levels (美的, 西门子, 小米) -> brand_0, brand_1
        - price: 2999, 3999, 4999 -> price_std
        - feature: 2 levels (有/无) -> feature

    True population mean:
        mu = {"brand_0": 0.8, "brand_1": -0.4, "price": -1.2, "feature": 1.5}

    If ``homogeneous`` is True, all respondents share the same beta = mu
    (useful for MNL benchmarking). Otherwise individual betas are drawn
    from N(mu, 0.3^2 * I).
    """
    rng = np.random.default_rng(random_seed)

    feature_cols = ["brand_0", "brand_1", "price", "feature"]
    true_mu = {
        "brand_0": 0.8,
        "brand_1": -0.4,
        "price": -1.2,
        "feature": 1.5,
    }
    sigma = 0.3

    rows: list[dict] = []
    true_beta: dict[str, dict[str, float]] = {}

    for resp_idx in range(n_resp):
        resp_id = f"resp_{resp_idx:03d}"
        if homogeneous:
            beta = dict(true_mu)
        else:
            beta = {col: float(rng.normal(true_mu[col], sigma)) for col in feature_cols}
        true_beta[resp_id] = beta

        for task_idx in range(n_tasks):
            task_utilities = []
            task_alts = []

            for alt_idx in range(n_alts):
                brand = rng.choice([0, 1, 2])
                price = rng.choice([2999, 3999, 4999])
                has_feature = rng.choice([0, 1])

                # Effects coding
                if brand == 0:
                    brand_0, brand_1 = 1.0, 0.0
                elif brand == 1:
                    brand_0, brand_1 = 0.0, 1.0
                else:
                    brand_0, brand_1 = -1.0, -1.0

                price_std = (price - 3999) / 816.0
                feature_val = 1.0 if has_feature else -1.0

                # Utility with Gumbel noise (Type-I extreme value)
                utility = (
                    beta["brand_0"] * brand_0
                    + beta["brand_1"] * brand_1
                    + beta["price"] * price_std
                    + beta["feature"] * feature_val
                    + rng.gumbel(0.0, 1.0)
                )

                task_utilities.append(utility)
                task_alts.append(
                    {
                        "resp_id": resp_id,
                        "task_id": task_idx,
                        "alt_id": alt_idx,
                        "brand_0": brand_0,
                        "brand_1": brand_1,
                        "price": price_std,
                        "feature": feature_val,
                    }
                )

            chosen_idx = int(np.argmax(task_utilities))
            for i, alt in enumerate(task_alts):
                alt["chosen"] = 1 if i == chosen_idx else 0
                rows.append(alt)

    df = pd.DataFrame(rows)
    return df, true_mu, true_beta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_hb_data():
    """Heterogeneous synthetic data for HB recovery (20 resp × 8 tasks)."""
    return make_synthetic_data(n_resp=20, n_tasks=8, n_alts=3, homogeneous=False)


@pytest.fixture
def synthetic_mnl_data():
    """Homogeneous synthetic data for MNL recovery (30 resp × 5 tasks)."""
    return make_synthetic_data(n_resp=30, n_tasks=5, n_alts=3, homogeneous=True)


@pytest.fixture
def tiny_hb_config() -> HBConfig:
    """Tiny MCMC config for fast tests."""
    return HBConfig(
        n_draws=400,
        n_tune=400,
        n_chains=2,
        target_accept=0.9,
        random_seed=42,
    )


# ---------------------------------------------------------------------------
# HB Recovery Tests
# ---------------------------------------------------------------------------


class TestHBParameterRecovery:
    """Verify HB engine recovers known synthetic parameters."""

    @pytest.mark.slow
    def test_population_mu_recovery(self, synthetic_hb_data, tiny_hb_config):
        """Population mean μ recovered within 10% relative error."""
        df, true_mu, _ = synthetic_hb_data
        engine = HBEngine(config=tiny_hb_config)
        result = engine.fit(
            data=df,
            feature_cols=["brand_0", "brand_1", "price", "feature"],
        )

        assert result.converged
        assert result.rhat_max < 1.1

        for col, true_val in true_mu.items():
            recovered = result.population_mu[col]
            err = abs(recovered - true_val)
            rel_err = err / (abs(true_val) + 0.5)  # guard against div-by-zero
            assert rel_err < 0.10, (
                f"{col}: recovered={recovered:.3f}, true={true_val:.3f}, rel_err={rel_err:.3f}"
            )

    @pytest.mark.slow
    def test_individual_beta_rank_recovery(self, synthetic_hb_data, tiny_hb_config):
        """Per-parameter respondent ranking correlates with truth (Kendall tau > 0.7)."""
        df, _, true_beta = synthetic_hb_data
        engine = HBEngine(config=tiny_hb_config)
        result = engine.fit(
            data=df,
            feature_cols=["brand_0", "brand_1", "price", "feature"],
        )

        taus = []
        for col in ["brand_0", "brand_1", "price", "feature"]:
            true_vals = [true_beta[resp][col] for resp in true_beta]
            rec_vals = [result.individual_utilities[resp][col] for resp in true_beta]
            tau, _ = stats.kendalltau(true_vals, rec_vals)
            taus.append(tau)

        mean_tau = float(np.mean(taus))
        assert mean_tau > 0.7, f"Mean per-parameter Kendall tau = {mean_tau:.3f}"

    @pytest.mark.slow
    def test_rhat_below_threshold(self, synthetic_hb_data, tiny_hb_config):
        """All parameters should have R-hat < 1.1."""
        df, _, _ = synthetic_hb_data
        engine = HBEngine(config=tiny_hb_config)
        result = engine.fit(
            data=df,
            feature_cols=["brand_0", "brand_1", "price", "feature"],
        )
        assert result.rhat_max < 1.1
        assert result.diagnostics is not None
        assert result.diagnostics["converged"] is True


# ---------------------------------------------------------------------------
# MNL Recovery Tests
# ---------------------------------------------------------------------------


class TestMNLParameterRecovery:
    """Verify MNL engine recovers known synthetic parameters."""

    def test_mnl_population_mu_recovery(self, synthetic_mnl_data):
        """MNL should recover population mean on homogeneous data within 15%."""
        df, true_mu, _ = synthetic_mnl_data
        engine = MNLEngine()
        result = engine.fit(
            data=df,
            feature_cols=["brand_0", "brand_1", "price", "feature"],
        )

        assert result.converged

        for col, true_val in true_mu.items():
            recovered = result.population_mu[col]
            err = abs(recovered - true_val)
            rel_err = err / (abs(true_val) + 0.5)
            assert rel_err < 0.15, (
                f"{col}: recovered={recovered:.3f}, true={true_val:.3f}, rel_err={rel_err:.3f}"
            )
