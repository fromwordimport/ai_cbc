"""HB engine parameter recovery and convergence validation.

Validates the HB model engine across:
  - Parameter recovery (population mu, individual ranking)
  - Convergence diagnostics (R-hat, ESS)
  - Edge conditions (homogeneous, sparse, missing, large parameter space)
  - MNL vs HB consistency on homogeneous data
  - Synthetic data recovery with known ground-truth parameters
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from aicbc.analysis.engines.hb_engine import HBConfig, HBEngine
from aicbc.analysis.engines.mnl_engine import MNLEngine
from aicbc.questionnaire.models import Attribute, AttributeLevel, AttributeType

pytestmark = [pytest.mark.unit, pytest.mark.slow]


# ---------------------------------------------------------------------------
# Synthetic data generators
# ---------------------------------------------------------------------------


def _default_attributes(n_attrs: int = 5) -> list[Attribute]:
    names = [
        "brand",
        "capacity",
        "installation",
        "features",
        "energy",
        "noise",
        "material",
        "warranty",
        "display",
        "connectivity",
        "design",
        "color",
    ][:n_attrs]
    attrs = []
    for name in names:
        levels = [AttributeLevel(value=f"{name}_{i}", label=f"{name}_{i}") for i in range(3)]
        attrs.append(
            Attribute(
                id=name,
                name=name,
                type=AttributeType.CATEGORICAL,
                levels=levels,
            )
        )
    return attrs


def _feature_cols(attributes: list[Attribute]) -> list[str]:
    cols: list[str] = []
    for attr in attributes:
        n = len(attr.levels)
        if n <= 2:
            cols.append(f"{attr.id}_0")
        else:
            for i in range(n - 1):
                cols.append(f"{attr.id}_{i}")
    return cols


def _synthetic_hb_long(
    n_respondents: int = 50,
    n_attrs: int = 5,
    n_tasks: int = 12,
    n_alts: int = 3,
    population_mu: dict[str, float] | None = None,
    homogeneous: bool = False,
    missing_rate: float = 0.0,
    seed: int = 42,
) -> tuple[pd.DataFrame, dict[str, float], dict[str, dict[str, float]]]:
    rng = np.random.default_rng(seed)
    attrs = _default_attributes(n_attrs)
    feat_cols = _feature_cols(attrs)
    n_feat = len(feat_cols)

    if population_mu is not None:
        mu = np.array([population_mu.get(c, 0.0) for c in feat_cols])
    else:
        mu = rng.normal(0, 0.5, size=n_feat)

    sigma_vec = np.full(n_feat, 0.01) if homogeneous else rng.uniform(0.2, 1.0, size=n_feat)

    person_betas: dict[str, dict[str, float]] = {}
    for pid in range(n_respondents):
        beta = rng.normal(mu, sigma_vec)
        person_betas[f"p{pid}"] = {c: float(b) for c, b in zip(feat_cols, beta)}

    rows: list[dict] = []
    for pid in range(n_respondents):
        for task in range(n_tasks):
            task_id_val = pid * n_tasks + task
            for alt in range(n_alts):
                x = rng.normal(0, 1, size=n_feat)
                u = float(
                    np.dot(x, [person_betas[f"p{pid}"][c] for c in feat_cols]) + rng.gumbel(0, 1)
                )
                rows.append(
                    {
                        "resp_id": f"p{pid}",
                        "task_id": task_id_val,
                        "alt_id": alt,
                        "chosen": False,
                        "utility": u,
                        **{c: float(v) for c, v in zip(feat_cols, x)},
                    }
                )

    df = pd.DataFrame(rows)

    for (_respondent, _task), idx in df.groupby(["resp_id", "task_id"]).groups.items():
        best = df.loc[idx, "utility"].idxmax()
        df.loc[best, "chosen"] = True

    if missing_rate > 0:
        task_ids = df["task_id"].unique()
        n_drop = int(len(task_ids) * missing_rate)
        drop_tasks = rng.choice(task_ids, size=n_drop, replace=False)
        df = df[~df["task_id"].isin(drop_tasks)]

    pop_mu_dict = {c: float(v) for c, v in zip(feat_cols, mu)}
    return df, pop_mu_dict, person_betas


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
    """Heterogeneous synthetic data for HB recovery (20 resp x 8 tasks)."""
    return make_synthetic_data(n_resp=20, n_tasks=8, n_alts=3, homogeneous=False)


@pytest.fixture
def synthetic_mnl_data():
    """Homogeneous synthetic data for MNL recovery (30 resp x 5 tasks)."""
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
        max_draws=1500,  # cap small-sample auto-boost to keep nightly runtime reasonable
    )


@pytest.fixture(scope="session")
def timing_report():
    records: list[dict] = []
    yield records
    print("\n--- HB Performance Benchmark Summary ---")
    for r in records:
        print(
            f"  N={r['n']:>4}  attrs={r['n_attrs']}  time={r['time_s']:>6.1f}s  "
            f"rhat={r['rhat']:.3f}  ess={r['ess']}  converged={r['converged']}"
        )


# ---------------------------------------------------------------------------
# Parameter recovery tests
# ---------------------------------------------------------------------------


class TestParameterRecovery:
    """Verify HB engine recovers known population parameters."""

    def test_population_mu_recovery_n50(self):
        df, true_mu, _ = _synthetic_hb_long(n_respondents=50, n_attrs=4)
        attrs = _default_attributes(4)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=300, n_tune=300, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        for key in feat_cols:
            estimated = result.population_mu[key]
            true_val = true_mu[key]
            assert abs(estimated - true_val) < 1.5, (
                f"{key}: est={estimated:.3f} true={true_val:.3f} (diff={abs(estimated - true_val):.3f})"
            )

    def test_population_mu_recovery_n200(self):
        df, true_mu, _ = _synthetic_hb_long(n_respondents=200, n_attrs=4)
        attrs = _default_attributes(4)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=500, n_tune=500, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        for key in feat_cols:
            estimated = result.population_mu[key]
            true_val = true_mu[key]
            assert abs(estimated - true_val) < 1.0, (
                f"{key}: est={estimated:.3f} true={true_val:.3f}"
            )

    def test_individual_ranking_correlation(self):
        df, _, true_betas = _synthetic_hb_long(n_respondents=30, n_attrs=4, homogeneous=False)
        attrs = _default_attributes(4)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=500, n_tune=500, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        true_ranks: dict[str, int] = {}
        est_ranks: dict[str, int] = {}
        for pid in true_betas:
            tv = np.mean(list(true_betas[pid].values()))
            true_ranks[pid] = int(np.sign(tv))
            ev = np.mean([result.individual_utilities.get(pid, {}).get(c, 0) for c in feat_cols])
            est_ranks[pid] = int(np.sign(ev))

        tau, _ = stats.kendalltau(list(true_ranks.values()), list(est_ranks.values()))
        assert tau > 0.2, f"Kendall tau={tau:.3f} too low"

    def test_population_mu_recovery_synthetic(self, synthetic_hb_data, tiny_hb_config):
        """Population mean mu recovered within relaxed tolerance.

        The synthetic dataset has only 20 respondents; the engine auto-boosts
        draws to 2000 for small samples, but posterior uncertainty remains high.
        This test primarily guards against divergence/catastrophic estimates.
        """
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
            assert rel_err < 0.55, (
                f"{col}: recovered={recovered:.3f}, true={true_val:.3f}, rel_err={rel_err:.3f}"
            )

    def test_individual_beta_rank_recovery_synthetic(self, synthetic_hb_data, tiny_hb_config):
        """Per-parameter respondent ranking shows positive correlation with truth.

        With only 20 respondents and auto-boosted 2000 draws, individual-level
        recovery is noisy; this test guards against entirely uncorrelated estimates.
        """
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
        assert mean_tau > 0.20, f"Mean per-parameter Kendall tau = {mean_tau:.3f}"


# ---------------------------------------------------------------------------
# Convergence diagnostics
# ---------------------------------------------------------------------------


class TestConvergenceDiagnostics:
    """Verify convergence diagnostic correctness."""

    def test_rhat_threshold(self):
        df, _, _ = _synthetic_hb_long(n_respondents=50, n_attrs=4)
        attrs = _default_attributes(4)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=500, n_tune=500, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        assert result.rhat_max > 0, "R-hat should be positive"
        assert result.rhat_max < 3.0, f"R-hat={result.rhat_max:.3f} unreasonably high"
        assert result.converged == (result.rhat_max < 1.1)

    def test_ess_threshold(self):
        df, _, _ = _synthetic_hb_long(n_respondents=50, n_attrs=4)
        attrs = _default_attributes(4)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=500, n_tune=500, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        assert result.ess_bulk_min > 0, "ESS should be positive"
        assert isinstance(result.ess_bulk_min, int), "ESS should be integer type"

    def test_diagnostic_structure(self):
        df, _, _ = _synthetic_hb_long(n_respondents=10, n_attrs=3)
        attrs = _default_attributes(3)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=200, n_tune=200, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        assert isinstance(result.population_mu, dict)
        assert isinstance(result.population_sigma, dict)
        assert isinstance(result.individual_utilities, dict)
        assert all(c in result.population_mu for c in feat_cols)

    def test_rhat_below_threshold_synthetic(self, synthetic_hb_data, tiny_hb_config):
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

    @pytest.mark.xfail(
        reason="PyMC NUTS converges even with tiny data; non-convergence is hard to trigger deterministically without model misspecification"
    )
    def test_hb_engine_warns_on_non_convergence(self):
        """Tiny config with very few samples should trigger R-hat > 1.1.

        We use extremely small data (3 respondents, 4 tasks, 2 alternatives)
        and minimal MCMC settings to force poor mixing / non-convergence.
        The engine auto-scales draws/tune for n_resp < 50, so we monkeypatch
        the config after build_model to keep draws tiny and force divergence.
        """
        rng = np.random.default_rng(99)
        feature_cols = ["price", "brand_0"]
        rows = []
        for resp in range(3):
            for task in range(4):
                for alt in range(2):
                    price = rng.choice([2999, 3999])
                    price_std = (price - 3999) / 816.0
                    brand_0 = 1.0 if alt == 0 else -1.0
                    chosen = 1 if alt == 0 else 0
                    rows.append({
                        "resp_id": f"r{resp}",
                        "task_id": task,
                        "alt_id": alt,
                        "chosen": chosen,
                        "price": price_std,
                        "brand_0": brand_0,
                    })
        df = pd.DataFrame(rows)

        # Minimal MCMC — should not converge with tiny data and few iterations
        config = HBConfig(n_draws=50, n_tune=50, n_chains=2, target_accept=0.8, random_seed=99)
        engine = HBEngine(config)
        engine.build_model(df, feature_cols)
        # Override auto-scaling so draws stay tiny
        engine.config.n_draws = 50
        engine.config.n_tune = 50
        result = engine.fit(df, feature_cols)

        # Assert non-convergence via diagnostics flag
        assert result.converged is False, (
            f"Expected non-convergence, but rhat_max={result.rhat_max:.3f}"
        )
        assert result.rhat_max >= 1.1, (
            f"Expected R-hat >= 1.1, got {result.rhat_max:.3f}"
        )
        assert result.diagnostics is not None
        assert result.diagnostics["converged"] is False


# ---------------------------------------------------------------------------
# Edge conditions
# ---------------------------------------------------------------------------


class TestEdgeConditions:
    """Verify HB engine handles edge conditions gracefully."""

    def test_homogeneous_preferences(self):
        df, _, _ = _synthetic_hb_long(n_respondents=30, n_attrs=4, homogeneous=True)
        attrs = _default_attributes(4)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=300, n_tune=300, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        assert result.population_mu is not None
        assert result.individual_utilities is not None

    def test_large_parameter_space(self):
        df, _, _ = _synthetic_hb_long(n_respondents=30, n_attrs=8)
        attrs = _default_attributes(8)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=300, n_tune=300, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        assert len(result.population_mu) == len(feat_cols)

    def test_missing_responses(self):
        df, _, _ = _synthetic_hb_long(n_respondents=40, n_attrs=4, missing_rate=0.15)
        attrs = _default_attributes(4)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=300, n_tune=300, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        assert result.population_mu is not None

    def test_single_respondent(self):
        df, _, _ = _synthetic_hb_long(n_respondents=1, n_attrs=4, n_tasks=20)
        attrs = _default_attributes(4)
        feat_cols = _feature_cols(attrs)

        config = HBConfig(n_draws=200, n_tune=200, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        result = engine.fit(df, feat_cols)

        assert len(result.individual_utilities) == 1


# ---------------------------------------------------------------------------
# Performance benchmarks
# ---------------------------------------------------------------------------


class TestPerformanceBenchmarks:
    """Collect timing data at various sizes."""

    def test_benchmark_n50(self, timing_report):
        df, _, _ = _synthetic_hb_long(n_respondents=50, n_attrs=4)
        feat_cols = _feature_cols(_default_attributes(4))

        config = HBConfig(n_draws=300, n_tune=300, n_chains=2, target_accept=0.85, random_seed=42)
        engine = HBEngine(config)
        t0 = time.perf_counter()
        result = engine.fit(df, feat_cols)
        elapsed = time.perf_counter() - t0

        timing_report.append(
            {
                "n": 50,
                "n_attrs": 4,
                "time_s": elapsed,
                "rhat": result.rhat_max,
                "ess": result.ess_bulk_min,
                "converged": result.converged,
            }
        )
        assert elapsed < 600, f"HB fit took {elapsed:.1f}s, probable infinite loop or hang"


# ---------------------------------------------------------------------------
# MNL vs HB consistency
# ---------------------------------------------------------------------------


class TestMNLvsHBConsistency:
    """Verify MNL and HB agree on direction for homogeneous data."""

    def test_mnl_hb_sign_agreement(self):
        df, true_mu, _ = _synthetic_hb_long(n_respondents=100, n_attrs=4, homogeneous=True)
        attrs = _default_attributes(4)
        feat_cols = _feature_cols(attrs)

        hb_config = HBConfig(
            n_draws=500, n_tune=500, n_chains=2, target_accept=0.85, random_seed=42
        )
        hb_engine = HBEngine(hb_config)
        hb_result = hb_engine.fit(df, feat_cols)

        mnl_engine = MNLEngine()
        mnl_result = mnl_engine.fit(df, feat_cols)

        sign_agreements = 0
        for key in feat_cols:
            hb_sign = np.sign(hb_result.population_mu[key])
            mnl_sign = np.sign(mnl_result.population_mu.get(key, 0))
            if hb_sign == mnl_sign:
                sign_agreements += 1

        agreement_rate = sign_agreements / len(feat_cols)
        assert agreement_rate >= 0.75, (
            f"MNL-HB sign agreement rate {agreement_rate:.1%}, expected >= 75%"
        )


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------