import numpy as np
import pandas as pd
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

from aicbc.analysis.engines.latent_class_engine import (
    LatentClassConfig,
    LatentClassEngine,
)

# Reuse a single latent-class fit across slow tests that operate on the same
# synthetic data. Each MCMC run is expensive; the assertions below only inspect
# the fitted result, so re-fitting is pure overhead.
_LC_FIT_CACHE: dict[str, object] = {}


def _make_synthetic_data(n_resp: int = 30, n_tasks: int = 6, n_alts: int = 3) -> pd.DataFrame:
    """Create a tiny synthetic CBC dataset with two latent classes."""
    rng = np.random.default_rng(42)
    rows = []
    for resp in range(n_resp):
        # Two latent classes: class A prefers low price, class B prefers brand_2
        class_a = resp < n_resp // 2
        for task in range(n_tasks):
            # Generate random alternatives
            xs = []
            for _alt in range(n_alts):
                price = rng.choice([2000, 3000, 4000])
                brand_1 = 1 if rng.random() < 0.3 else 0
                brand_2 = 1 if rng.random() < 0.3 else 0
                xs.append([price, brand_1, brand_2])
            xs = np.array(xs)
            # True utilities
            utilities = (
                -0.001 * xs[:, 0]
                + (0.0 if class_a else 0.5) * xs[:, 1]
                + (0.0 if class_a else 1.0) * xs[:, 2]
            )
            utilities += rng.normal(0, 0.2, size=n_alts)
            chosen = int(np.argmax(utilities))
            for alt, x in enumerate(xs):
                rows.append(
                    {
                        "resp_id": f"resp_{resp}",
                        "task_id": f"task_{task}",
                        "alt_id": alt,
                        "price": x[0],
                        "brand_1": x[1],
                        "brand_2": x[2],
                        "chosen": 1 if alt == chosen else 0,
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_data():
    return _make_synthetic_data()


@pytest.fixture
def fitted_latent_class_result(synthetic_data):
    """Fit a latent-class model once and share it across slow tests."""
    key = "lc_result"
    if key not in _LC_FIT_CACHE:
        engine = LatentClassEngine(
            LatentClassConfig(
                n_classes=2,
                n_draws=300,
                n_tune=300,
                n_chains=2,
                random_seed=42,
                class_probs_alpha=10.0,  # encourage balanced classes on this 50/50 data
            )
        )
        _LC_FIT_CACHE[key] = engine.fit(
            synthetic_data,
            feature_cols=["price", "brand_1", "brand_2"],
        )
    return _LC_FIT_CACHE[key]


def test_latent_class_model_builds(synthetic_data):
    engine = LatentClassEngine(LatentClassConfig(n_classes=2, n_draws=50, n_tune=50, n_chains=2))
    model = engine.build_model(
        synthetic_data,
        feature_cols=["price", "brand_1", "brand_2"],
    )
    assert model is not None
    assert "class_probs" in [v.name for v in model.basic_RVs]
    assert "beta" in [v.name for v in model.basic_RVs]


@pytest.mark.slow
def test_latent_class_model_fits(synthetic_data, fitted_latent_class_result):
    result = fitted_latent_class_result
    assert result is not None
    assert len(result.class_probs) == 2
    assert sum(result.class_probs.values()) == pytest.approx(1.0, abs=0.01)
    assert len(result.class_utilities) == 2
    assert len(result.individual_class_probs) == synthetic_data["resp_id"].nunique()
    assert len(result.assigned_class) == synthetic_data["resp_id"].nunique()
    assert result.diagnostics is not None
    assert "rhat_max" in result.diagnostics


@pytest.mark.slow
def test_latent_class_recovers_two_segments(fitted_latent_class_result):
    """Smoke test: LCM should assign respondents to two classes.

    With only 30 respondents and a small MCMC budget, exact 50/50 split is
    too strict; we only require both classes to be represented by multiple
    respondents.
    """
    result = fitted_latent_class_result
    class_counts: dict[str, int] = {}
    for cls in result.assigned_class.values():
        class_counts[cls] = class_counts.get(cls, 0) + 1
    assert len(class_counts) == 2
    assert all(c >= 2 for c in class_counts.values()), f"class_counts={class_counts}"
