"""ISS-004: HB engine convergence and parameter recovery validation.

Validates the HB model engine across:
  - Parameter recovery (population mu, individual ranking)
  - Convergence diagnostics (R-hat, ESS)
  - Edge conditions (homogeneous, sparse, missing, large parameter space)
  - MNL vs HB consistency on homogeneous data
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.slow]

import time

import numpy as np
import pandas as pd
import pytest

from aicbc.analysis.engines.hb_engine import HBConfig, HBEngine
from aicbc.analysis.engines.mnl_engine import MNLEngine
from aicbc.questionnaire.models import Attribute, AttributeLevel, AttributeType


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
        person_betas[f"p{pid}"] = {c: float(b) for c, b in zip(feat_cols, beta, strict=False)}

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
                        **{c: float(v) for c, v in zip(feat_cols, x, strict=False)},
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

    pop_mu_dict = {c: float(v) for c, v in zip(feat_cols, mu, strict=False)}
    return df, pop_mu_dict, person_betas


# ---------------------------------------------------------------------------
# Parameter recovery tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
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

        tau, _ = _kendall_tau(list(true_ranks.values()), list(est_ranks.values()))
        assert tau > 0.2, f"Kendall tau={tau:.3f} too low"


# ---------------------------------------------------------------------------
# Convergence diagnostics
# ---------------------------------------------------------------------------


class TestConvergenceDiagnostics:
    """Verify convergence diagnostic correctness."""

    pytestmark = pytest.mark.slow

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


# ---------------------------------------------------------------------------
# Edge conditions
# ---------------------------------------------------------------------------


class TestEdgeConditions:
    """Verify HB engine handles edge conditions gracefully."""

    pytestmark = pytest.mark.slow

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


@pytest.mark.slow
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

    pytestmark = pytest.mark.slow

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
        assert agreement_rate >= 0.5, (
            f"MNL-HB sign agreement rate {agreement_rate:.1%}, expected >= 50%"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kendall_tau(a: list, b: list) -> tuple[float, int]:
    n = len(a)
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            da = a[i] - a[j]
            db = b[i] - b[j]
            if da * db > 0:
                concordant += 1
            elif da * db < 0:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return 0.0, 0
    return (concordant - discordant) / total, total
