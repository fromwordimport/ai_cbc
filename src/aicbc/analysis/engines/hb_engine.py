"""Hierarchical Bayes (HB) model engine using PyMC.

Implements the core Mixed Logit model with individual-level heterogeneity
distributed as multivariate normal. Uses NUTS sampler for posterior inference.

Design follows the specification in:
    - cbc-analysis-system/03-模型实现指南.md (Section 3.2)
    - docs/建模管线与API设计.md (Section 3.2)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class HBConfig:
    """Configuration for HB model fitting."""

    n_draws: int = 1000
    n_tune: int = 1000
    n_chains: int = 4
    n_cores: int | None = None  # PyMC default = min(chains, 4); set to 1 to limit memory
    target_accept: float = 0.8  # 0.8 sufficient for Mixed Logit; saves 2-3x sampling time vs 0.9
    mu_prior_mean: float = 0.0
    mu_prior_sigma: float = 10.0
    sigma_prior: str = "half_normal"
    lkj_eta: float = 2.0
    random_seed: int | None = 42
    max_draws: int | None = None  # Hard cap on small-sample auto-boosting


@dataclass
class HBResult:
    """Results from HB model fitting."""

    converged: bool
    rhat_max: float
    ess_bulk_min: int
    ess_tail_min: int
    population_mu: dict[str, float]
    population_sigma: dict[str, float]
    individual_utilities: dict[str, dict[str, float]]
    trace: Any | None = None  # arviz.InferenceData
    diagnostics: dict[str, Any] | None = None


class HBEngine:
    """Hierarchical Bayes Mixed Logit model engine using PyMC.

    The model specification:

        Individual level:
            U_ij = βᵢ' X_ij + ε_ij
            βᵢ ~ N(μ, Σ)

        Population level (hyperparameters):
            μ ~ N(μ₀, A)
            Σ = chol @ chol.T  via LKJCholeskyCov

        Choice probability:
            P(i|C, βᵢ) = exp(βᵢ'Xᵢ) / Σⱼ exp(βᵢ'Xⱼ)

    Uses non-centered parameterization for better sampling efficiency:
        z ~ N(0, 1)
        β = μ + (chol @ z.T).T
    """

    def __init__(self, config: HBConfig | None = None) -> None:
        self.config = config or HBConfig()
        self.model: Any = None
        self.trace: Any = None
        self._resp_ids: np.ndarray | None = None
        self._resp_map: dict[str, int] | None = None
        self._feature_cols: list[str] | None = None
        self._tasks: list[dict] | None = None

    def _preprocess(
        self,
        data: pd.DataFrame,
        feature_cols: list[str],
        resp_id_col: str,
        task_id_col: str,
        choice_col: str,
    ) -> None:
        """Build task-level data structures for efficient likelihood evaluation."""
        self._resp_ids = data[resp_id_col].unique()
        self._resp_map = {rid: i for i, rid in enumerate(self._resp_ids)}
        self._feature_cols = feature_cols

        self._tasks = []
        for (resp, _task), group in data.groupby([resp_id_col, task_id_col], sort=False):
            X_task = group[feature_cols].values.astype(np.float64)
            chosen_mask = group[choice_col].values == 1
            if not chosen_mask.any():
                continue
            chosen_idx = int(np.argmax(chosen_mask))
            resp_idx = self._resp_map[resp]

            self._tasks.append(
                {
                    "X": X_task,
                    "y": chosen_idx,
                    "resp_idx": resp_idx,
                }
            )

    def build_model(
        self,
        data: pd.DataFrame,
        feature_cols: list[str],
        resp_id_col: str = "resp_id",
        task_id_col: str = "task_id",
        choice_col: str = "chosen",
    ) -> Any:
        """Build the PyMC model.

        Args:
            data: Long-format DataFrame (one row per alternative).
            feature_cols: List of feature column names (design matrix columns).
            resp_id_col: Respondent ID column.
            task_id_col: Task/choice set ID column.
            choice_col: Choice indicator column (0/1).

        Returns:
            pm.Model instance.
        """
        import pymc as pm
        import pytensor.tensor as pt

        self._preprocess(data, feature_cols, resp_id_col, task_id_col, choice_col)
        assert self._resp_ids is not None
        assert self._tasks is not None

        n_resp = len(self._resp_ids)
        n_features = len(feature_cols)

        # Stack task tensors for vectorized likelihood (assumes constant n_alts)
        X_all = np.stack([task["X"] for task in self._tasks])
        resp_indices = np.array([task["resp_idx"] for task in self._tasks], dtype=int)
        chosen_indices = np.array([task["y"] for task in self._tasks], dtype=int)
        n_tasks = len(self._tasks)

        self.model = pm.Model()

        with self.model:
            # ── Population hyperparameters ──
            mu = pm.Normal(
                "mu",
                mu=self.config.mu_prior_mean,
                sigma=self.config.mu_prior_sigma,
                shape=n_features,
                initval=np.zeros(n_features),
            )

            # Standard deviations prior for LKJCholeskyCov
            if self.config.sigma_prior == "half_normal":
                sd_dist = pm.HalfNormal.dist(sigma=2, shape=n_features)
            else:
                sd_dist = pm.Exponential.dist(lam=1, shape=n_features)

            # Correlation matrix via LKJ Cholesky decomposition
            chol, _, stds = pm.LKJCholeskyCov(
                "chol",
                n=n_features,
                eta=self.config.lkj_eta,
                sd_dist=sd_dist,
                compute_corr=True,
            )

            # Covariance matrix (for reference)
            pm.Deterministic("cov", chol @ chol.T)
            pm.Deterministic("sigma", stds)

            # ── Individual coefficients (non-centered parameterization) ──
            z = pm.Normal("z", mu=0, sigma=1, shape=(n_resp, n_features))
            beta = pm.Deterministic("beta", mu + (chol @ z.T).T)

            # ── Likelihood (vectorized across tasks) ──
            # X_all: (n_tasks, n_alts, n_features)
            # beta_per_task: (n_tasks, n_features)
            # utilities: (n_tasks, n_alts)
            beta_per_task = beta[resp_indices]
            utilities = pt.sum(X_all * beta_per_task[:, None, :], axis=2)
            log_probs = utilities - pt.logsumexp(utilities, axis=-1, keepdims=True)
            chosen_log_probs = log_probs[pt.arange(n_tasks), chosen_indices]
            pm.Potential("log_likelihood", chosen_log_probs.sum())

        return self.model

    def fit(
        self,
        data: pd.DataFrame,
        feature_cols: list[str],
        resp_id_col: str = "resp_id",
        task_id_col: str = "task_id",
        choice_col: str = "chosen",
    ) -> HBResult:
        """Fit the HB model and return results.

        Args:
            data: Long-format DataFrame (one row per alternative).
            feature_cols: List of feature column names (design matrix columns).
            resp_id_col: Respondent ID column.
            task_id_col: Task/choice set ID column.
            choice_col: Choice indicator column (0/1).

        Returns:
            HBResult with posterior summaries and convergence diagnostics.
        """
        import pymc as pm

        self.build_model(data, feature_cols, resp_id_col, task_id_col, choice_col)
        assert self.model is not None

        # ── Data-scale adaptive sampling ──
        # Small samples (n_resp < 50) benefit from more posterior exploration,
        # but memory-constrained deployments can cap this via max_draws.
        n_resp = len(self._resp_ids) if self._resp_ids is not None else 0
        if n_resp < 50:
            boost_draws = max(self.config.n_draws, 2000)
            boost_tune = max(self.config.n_tune, 2000)
            if self.config.max_draws is not None:
                boost_draws = min(boost_draws, self.config.max_draws)
                boost_tune = min(boost_tune, self.config.max_draws)
            self.config.n_draws = boost_draws
            self.config.n_tune = boost_tune

        sample_kwargs = {
            "draws": self.config.n_draws,
            "tune": self.config.n_tune,
            "chains": self.config.n_chains,
            "target_accept": self.config.target_accept,
            "return_inferencedata": True,
            "random_seed": self.config.random_seed,
            "progressbar": False,
        }
        if self.config.n_cores is not None:
            sample_kwargs["cores"] = self.config.n_cores

        with self.model:
            self.trace = pm.sample(**sample_kwargs)

        # ── Convergence diagnostics ──
        diagnostics = self._compute_diagnostics()

        # ── Extract population parameters (posterior mean) ──
        population_mu = self._extract_population_mu()
        population_sigma = self._extract_population_sigma()

        # ── Extract individual utilities (posterior mean) ──
        individual_utilities = self._extract_individual_utilities()

        return HBResult(
            converged=diagnostics["converged"],
            rhat_max=diagnostics["rhat_max"],
            ess_bulk_min=diagnostics["ess_bulk_min"],
            ess_tail_min=diagnostics["ess_tail_min"],
            population_mu=population_mu,
            population_sigma=population_sigma,
            individual_utilities=individual_utilities,
            trace=self.trace,
            diagnostics=diagnostics,
        )

    def _compute_diagnostics(self) -> dict[str, Any]:
        """Compute MCMC convergence diagnostics using ArviZ.

        Uses az.summary() for efficient one-pass extraction of all R-hat
        and ESS values (replaces the O(n_params * n_coords) nested-loop
        pattern of per-variable rhat/ess calls).
        """
        import arviz as az

        if self.trace is None:
            raise RuntimeError("Model must be fit before computing diagnostics")

        var_names = ["mu", "sigma", "beta"]

        # One-pass extraction of all diagnostics via az.summary()
        summary = az.summary(self.trace, var_names=var_names)

        # Global convergence metrics
        rhat_max = float(summary["r_hat"].max())
        ess_bulk_min = int(summary["ess_bulk"].min())
        ess_tail_min = int(summary["ess_tail"].min())

        # Per-parameter breakdown (direct DataFrame → dict)
        rhat_by_param: dict[str, float] = {}
        ess_by_param: dict[str, float] = {}
        for param_name, row in summary.iterrows():
            rhat_by_param[param_name] = float(row["r_hat"])
            ess_by_param[param_name] = float(row["ess_bulk"])

        # Divergences and tree depth
        divergences = 0
        tree_depth_max = 0
        if hasattr(self.trace, "sample_stats"):
            ss = self.trace.sample_stats
            if "diverging" in ss.data_vars:
                divergences = int(ss.diverging.sum().values)
            if "tree_depth" in ss.data_vars:
                tree_depth_max = int(ss.tree_depth.max().values)

        converged = rhat_max < 1.1
        reliable_ess = ess_bulk_min > 400

        return {
            "rhat_max": rhat_max,
            "rhat_by_param": rhat_by_param,
            "ess_bulk_min": ess_bulk_min,
            "ess_tail_min": ess_tail_min,
            "ess_by_param": ess_by_param,
            "converged": converged,
            "reliable_ess": reliable_ess,
            "divergences": divergences,
            "tree_depth_max": tree_depth_max,
        }

    def _extract_population_mu(self) -> dict[str, float]:
        """Extract population mean (mu) posterior means."""
        if self.trace is None:
            raise RuntimeError("Model must be fit first")

        mu_posterior = self.trace.posterior["mu"]
        mu_mean = mu_posterior.mean(dim=["chain", "draw"]).values

        assert self._feature_cols is not None
        return {col: float(mu_mean[i]) for i, col in enumerate(self._feature_cols)}

    def _extract_population_sigma(self) -> dict[str, float]:
        """Extract population standard deviation (sigma) posterior means."""
        if self.trace is None:
            raise RuntimeError("Model must be fit first")

        sigma_posterior = self.trace.posterior["sigma"]
        sigma_mean = sigma_posterior.mean(dim=["chain", "draw"]).values

        assert self._feature_cols is not None
        return {col: float(sigma_mean[i]) for i, col in enumerate(self._feature_cols)}

    def _extract_individual_utilities(self) -> dict[str, dict[str, float]]:
        """Extract individual-level utility estimates (posterior means)."""
        if self.trace is None:
            raise RuntimeError("Model must be fit first")

        beta_posterior = self.trace.posterior["beta"]
        beta_mean = beta_posterior.mean(dim=["chain", "draw"]).values

        assert self._resp_ids is not None
        assert self._feature_cols is not None

        individual_utilities: dict[str, dict[str, float]] = {}
        for i, resp_id in enumerate(self._resp_ids):
            individual_utilities[resp_id] = {
                col: float(beta_mean[i, j]) for j, col in enumerate(self._feature_cols)
            }

        return individual_utilities

    def get_individual_distribution(
        self,
        resp_id: str | None = None,
    ) -> pd.DataFrame:
        """Get posterior distribution samples for a specific respondent.

        Args:
            resp_id: Respondent ID. If None, returns all respondents.

        Returns:
            DataFrame with samples stacked (chain, draw) as rows.
        """
        if self.trace is None:
            raise RuntimeError("Model must be fit first")

        beta_posterior = self.trace.posterior["beta"]

        if resp_id is not None:
            assert self._resp_map is not None
            resp_idx = self._resp_map[resp_id]
            samples = beta_posterior.isel(beta_dim_0=resp_idx)
        else:
            samples = beta_posterior

        # Stack chain and draw into a single sample dimension
        df = samples.stack(sample=("chain", "draw")).to_dataframe().reset_index()
        return df

    def predict_probabilities(
        self,
        scenarios: list[dict[str, Any]],
        resp_id: str | None = None,
    ) -> np.ndarray:
        """Predict choice probabilities for given product scenarios.

        Args:
            scenarios: List of product profile dicts with feature values.
            resp_id: Specific respondent ID, or None for population average.

        Returns:
            Array of shape (n_scenarios,) with softmax probabilities.
        """
        if self.trace is None:
            raise RuntimeError("Model must be fit first")

        beta_posterior = self.trace.posterior["beta"]

        if resp_id is not None:
            assert self._resp_map is not None
            resp_idx = self._resp_map[resp_id]
            beta_samples = beta_posterior.isel(beta_dim_0=resp_idx)
        else:
            # Population average: average across respondents
            beta_samples = beta_posterior.mean(dim="beta_dim_0")

        # Posterior mean of beta
        beta_mean = beta_samples.mean(dim=["chain", "draw"]).values

        # Build design matrix from scenarios
        assert self._feature_cols is not None
        X = np.array(
            [[s.get(col, 0.0) for col in self._feature_cols] for s in scenarios], dtype=np.float64
        )

        utilities = X @ beta_mean
        exp_utils = np.exp(utilities - np.max(utilities))  # Numerical stability
        probs = exp_utils / exp_utils.sum()

        return probs
