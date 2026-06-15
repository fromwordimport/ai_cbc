"""Latent Class Model (LCM) engine for CBC analysis.

Implements a finite mixture of multinomial logit models using PyMC.  Each
latent class has its own set of part-worth utilities, and respondents are
soft-assigned to classes via class membership probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class LatentClassConfig:
    """Configuration for the latent class model."""

    n_classes: int = 3
    n_draws: int = 1000
    n_tune: int = 1000
    n_chains: int = 4
    target_accept: float = 0.9
    mu_prior_mean: float = 0.0
    mu_prior_sigma: float = 5.0
    class_probs_alpha: float = 1.0
    random_seed: int | None = 42


@dataclass
class LatentClassResult:
    """Results from fitting a latent class model."""

    converged: bool
    rhat_max: float
    ess_bulk_min: int
    ess_tail_min: int
    class_probs: dict[str, float]
    class_utilities: dict[str, dict[str, float]]
    individual_class_probs: dict[str, dict[str, float]]
    assigned_class: dict[str, str]
    trace: Any | None = None
    diagnostics: dict[str, Any] | None = None


class LatentClassEngine:
    """Latent Class Model engine using PyMC.

    Model specification:

        class_probs ~ Dirichlet(alpha)
        beta_c ~ Normal(mu_0, sigma_0)  for each class c

        For each choice task t:
            U_{c,t,j} = X_{t,j} @ beta_c
            P(y_t = j | c) = softmax(U_{c,t})_j
            P(y_t = j) = Σ_c class_probs[c] * P(y_t = j | c)

    The likelihood is implemented via a ``Potential`` using log-sum-exp for
    numerical stability.
    """

    def __init__(self, config: LatentClassConfig | None = None) -> None:
        self.config = config or LatentClassConfig()
        self.model: Any = None
        self.trace: Any = None
        self._tasks: list[dict] | None = None
        self._feature_cols: list[str] | None = None
        self._resp_ids: np.ndarray | None = None
        self._resp_tasks: dict[str, list[int]] | None = None

    def _preprocess(
        self,
        data: pd.DataFrame,
        feature_cols: list[str],
        resp_id_col: str,
        task_id_col: str,
        choice_col: str,
    ) -> None:
        """Build task-level structures."""
        self._feature_cols = feature_cols
        self._resp_ids = data[resp_id_col].unique()
        self._resp_tasks = {rid: [] for rid in self._resp_ids}

        self._tasks = []
        for (resp, task), group in data.groupby([resp_id_col, task_id_col], sort=False):
            X_task = group[feature_cols].values.astype(np.float64)
            chosen_mask = group[choice_col].values == 1
            if not chosen_mask.any():
                continue
            chosen_idx = int(np.argmax(chosen_mask))
            task_idx = len(self._tasks)
            self._tasks.append({"X": X_task, "y": chosen_idx})
            self._resp_tasks[resp].append(task_idx)

    def build_model(
        self,
        data: pd.DataFrame,
        feature_cols: list[str],
        resp_id_col: str = "resp_id",
        task_id_col: str = "task_id",
        choice_col: str = "chosen",
    ) -> Any:
        """Build the PyMC latent class model.

        Args:
            data: Long-format DataFrame (one row per alternative).
            feature_cols: Feature/design matrix column names.
            resp_id_col: Respondent ID column.
            task_id_col: Task/choice set ID column.
            choice_col: Choice indicator column (0/1).

        Returns:
            pm.Model instance.
        """
        import pymc as pm

        self._preprocess(data, feature_cols, resp_id_col, task_id_col, choice_col)
        assert self._tasks is not None

        n_features = len(feature_cols)
        n_classes = self.config.n_classes

        self.model = pm.Model()
        with self.model:
            class_probs = pm.Dirichlet(
                "class_probs",
                a=np.full(n_classes, self.config.class_probs_alpha),
            )

            beta = pm.Normal(
                "beta",
                mu=self.config.mu_prior_mean,
                sigma=self.config.mu_prior_sigma,
                shape=(n_classes, n_features),
            )

            # Per-task log-likelihood for each class
            log_probs_per_class = []
            for task in self._tasks:
                X = task["X"]
                chosen = task["y"]
                # utilities[c, j]
                utilities = pm.math.dot(beta, X.T)
                # log_softmax over alternatives for each class
                log_prob = pm.math.log_softmax(utilities, axis=1)[:, chosen]
                log_probs_per_class.append(log_prob)

            # Stack to shape (n_tasks, n_classes)
            task_log_probs = pm.math.stack(log_probs_per_class, axis=0)

            # log P(y | class_probs, beta) = logsumexp(log(class_probs) + task_log_probs)
            log_class_probs = pm.math.log(class_probs)
            log_likelihood = pm.math.sum(
                pm.math.logsumexp(log_class_probs + task_log_probs, axis=1)
            )
            pm.Potential("log_likelihood", log_likelihood)

        return self.model

    def fit(
        self,
        data: pd.DataFrame,
        feature_cols: list[str],
        resp_id_col: str = "resp_id",
        task_id_col: str = "task_id",
        choice_col: str = "chosen",
    ) -> LatentClassResult:
        """Fit the latent class model and return results."""
        import pymc as pm
        import arviz as az

        self.build_model(data, feature_cols, resp_id_col, task_id_col, choice_col)
        assert self.model is not None

        with self.model:
            self.trace = pm.sample(
                draws=self.config.n_draws,
                tune=self.config.n_tune,
                chains=self.config.n_chains,
                target_accept=self.config.target_accept,
                return_inferencedata=True,
                random_seed=self.config.random_seed,
                progressbar=False,
            )

        diagnostics = self._compute_diagnostics()
        class_probs = self._extract_class_probs()
        class_utilities = self._extract_class_utilities()
        individual_class_probs = self._compute_individual_class_probs(data, feature_cols)
        assigned_class = {
            rid: max(probs, key=probs.get)
            for rid, probs in individual_class_probs.items()
        }

        return LatentClassResult(
            converged=diagnostics["converged"],
            rhat_max=diagnostics["rhat_max"],
            ess_bulk_min=diagnostics["ess_bulk_min"],
            ess_tail_min=diagnostics["ess_tail_min"],
            class_probs=class_probs,
            class_utilities=class_utilities,
            individual_class_probs=individual_class_probs,
            assigned_class=assigned_class,
            trace=self.trace,
            diagnostics=diagnostics,
        )

    def _compute_diagnostics(self) -> dict[str, Any]:
        """Compute MCMC convergence diagnostics."""
        import arviz as az

        if self.trace is None:
            raise RuntimeError("Model must be fit before computing diagnostics")

        summary = az.summary(self.trace, var_names=["class_probs", "beta"])
        rhat_max = float(summary["r_hat"].max())
        ess_bulk_min = int(summary["ess_bulk"].min())
        ess_tail_min = int(summary["ess_tail"].min())

        divergences = 0
        if hasattr(self.trace, "sample_stats"):
            ss = self.trace.sample_stats
            if "diverging" in ss.data_vars:
                divergences = int(ss.diverging.sum().values)

        return {
            "rhat_max": rhat_max,
            "rhat_by_param": {name: float(row["r_hat"]) for name, row in summary.iterrows()},
            "ess_bulk_min": ess_bulk_min,
            "ess_tail_min": ess_tail_min,
            "ess_by_param": {name: float(row["ess_bulk"]) for name, row in summary.iterrows()},
            "converged": rhat_max < 1.1,
            "reliable_ess": ess_bulk_min > 400,
            "divergences": divergences,
        }

    def _extract_class_probs(self) -> dict[str, float]:
        """Return posterior mean class membership probabilities."""
        if self.trace is None:
            raise RuntimeError("Model must be fit first")

        probs = self.trace.posterior["class_probs"].mean(dim=["chain", "draw"]).values
        return {f"class_{i}": float(v) for i, v in enumerate(probs)}

    def _extract_class_utilities(self) -> dict[str, dict[str, float]]:
        """Return posterior mean utilities for each latent class."""
        if self.trace is None:
            raise RuntimeError("Model must be fit first")

        beta = self.trace.posterior["beta"].mean(dim=["chain", "draw"]).values
        assert self._feature_cols is not None
        return {
            f"class_{c}": {
                col: float(beta[c, i]) for i, col in enumerate(self._feature_cols)
            }
            for c in range(beta.shape[0])
        }

    def _compute_individual_class_probs(
        self,
        data: pd.DataFrame,
        feature_cols: list[str],
        resp_id_col: str = "resp_id",
        task_id_col: str = "task_id",
        choice_col: str = "chosen",
    ) -> dict[str, dict[str, float]]:
        """Compute posterior class probabilities for each respondent."""
        if self.trace is None:
            raise RuntimeError("Model must be fit first")

        class_probs = (
            self.trace.posterior["class_probs"].mean(dim=["chain", "draw"]).values
        )
        beta = self.trace.posterior["beta"].mean(dim=["chain", "draw"]).values

        result: dict[str, dict[str, float]] = {}
        for resp in self._resp_ids if self._resp_ids is not None else []:
            resp_df = data[data[resp_id_col] == resp]
            log_lik = np.log(class_probs + 1e-12)
            for _, group in resp_df.groupby(task_id_col, sort=False):
                X = group[feature_cols].values.astype(np.float64)
                chosen = int(np.argmax(group[choice_col].values))
                utilities = X @ beta.T  # (n_alts, n_classes)
                log_softmax = utilities - np.log(np.sum(np.exp(utilities - np.max(utilities, axis=0)), axis=0)) - np.max(utilities, axis=0)
                log_lik += log_softmax[chosen, :]
            probs = np.exp(log_lik - np.max(log_lik))
            probs = probs / probs.sum()
            result[str(resp)] = {f"class_{i}": float(v) for i, v in enumerate(probs)}
        return result
