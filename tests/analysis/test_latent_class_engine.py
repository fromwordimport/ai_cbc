import numpy as np
import pandas as pd
import pytest

from aicbc.analysis.engines.latent_class_engine import (
    LatentClassConfig,
    LatentClassEngine,
)


def _make_synthetic_data(n_resp: int = 30, n_tasks: int = 6, n_alts: int = 3) -> pd.DataFrame:
    """Create a tiny synthetic CBC dataset with two latent classes."""
    rng = np.random.default_rng(42)
    feature_cols = ["price", "brand_1", "brand_2"]
    rows = []
    for resp in range(n_resp):
        # Two latent classes: class A prefers low price, class B prefers brand_2
        class_a = resp < n_resp // 2
        for task in range(n_tasks):
            # Generate random alternatives
            Xs = []
            for alt in range(n_alts):
                price = rng.choice([2000, 3000, 4000])
                brand_1 = 1 if rng.random() < 0.3 else 0
                brand_2 = 1 if rng.random() < 0.3 else 0
                Xs.append([price, brand_1, brand_2])
            Xs = np.array(Xs)
            # True utilities
            utilities = (
                -0.001 * Xs[:, 0]
                + (0.0 if class_a else 0.5) * Xs[:, 1]
                + (0.0 if class_a else 1.0) * Xs[:, 2]
            )
            utilities += rng.normal(0, 0.2, size=n_alts)
            chosen = int(np.argmax(utilities))
            for alt, x in enumerate(Xs):
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
def test_latent_class_model_fits(synthetic_data):
    engine = LatentClassEngine(
        LatentClassConfig(n_classes=2, n_draws=200, n_tune=200, n_chains=2)
    )
    result = engine.fit(
        synthetic_data,
        feature_cols=["price", "brand_1", "brand_2"],
    )
    assert result is not None
    assert len(result.class_probs) == 2
    assert sum(result.class_probs.values()) == pytest.approx(1.0, abs=0.01)
    assert len(result.class_utilities) == 2
    assert len(result.individual_class_probs) == synthetic_data["resp_id"].nunique()
    assert len(result.assigned_class) == synthetic_data["resp_id"].nunique()
    assert result.diagnostics is not None
    assert "rhat_max" in result.diagnostics


@pytest.mark.slow
def test_latent_class_recovers_two_segments(synthetic_data):
    """Smoke test: LCM should assign respondents to two classes roughly 50/50."""
    engine = LatentClassEngine(
        LatentClassConfig(n_classes=2, n_draws=300, n_tune=300, n_chains=2)
    )
    result = engine.fit(
        synthetic_data,
        feature_cols=["price", "brand_1", "brand_2"],
    )
    class_counts: dict[str, int] = {}
    for cls in result.assigned_class.values():
        class_counts[cls] = class_counts.get(cls, 0) + 1
    # With 30 respondents generated from two equal classes, expect both present
    assert len(class_counts) == 2
    assert all(c >= 5 for c in class_counts.values())
