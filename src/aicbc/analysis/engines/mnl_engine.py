"""Multinomial Logit (MNL) / Conditional Logit baseline model.

Implements the aggregate-level conditional logit model using statsmodels.
This serves as a fast baseline before running the more expensive HB model.

Reference: cbc-analysis-system/03-模型实现指南.md Section 2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class MNLResult:
    """Results from MNL model fitting."""

    converged: bool
    population_mu: dict[str, float]
    population_sigma: dict[str, float]  # MNL: standard errors
    individual_utilities: dict[str, dict[str, float]]  # MNL: all respondents share mu
    log_likelihood: float
    null_log_likelihood: float
    mc_fadden_r2: float
    aic: float
    bic: float
    n_obs: int
    n_params: int
    coef_table: pd.DataFrame | None = None


class MNLEngine:
    """Multinomial Logit (Conditional Logit) baseline engine.

    Uses statsmodels' ConditionalLogit for aggregate-level estimation.
    Much faster than HB (seconds vs minutes) but no individual-level
    heterogeneity.
    """

    def __init__(self) -> None:
        self.model: Any = None
        self.results: Any = None
        self._feature_cols: list[str] | None = None

    def fit(
        self,
        data: pd.DataFrame,
        feature_cols: list[str],
        resp_id_col: str = "resp_id",
        task_id_col: str = "task_id",
        choice_col: str = "chosen",
    ) -> MNLResult:
        """Fit the MNL model.

        Args:
            data: Long-format DataFrame (one row per alternative).
            feature_cols: List of feature column names.
            resp_id_col: Respondent ID column.
            task_id_col: Task/choice set ID column.
            choice_col: Choice indicator column (0/1).

        Returns:
            MNLResult with coefficient estimates and fit statistics.
        """
        import statsmodels.api as sm

        self._feature_cols = feature_cols

        X = data[feature_cols].values.astype(np.float64)
        y = data[choice_col].values.astype(np.int32)

        # Build group index: each (resp, task) pair is one choice set
        groups = data.groupby([resp_id_col, task_id_col], sort=False).ngroup().values

        # Store n_alternatives per choice set for null-model computation
        self._n_alternatives = int(data.groupby([resp_id_col, task_id_col]).size().iloc[0])

        self.model = sm.ConditionalLogit(endog=y, exog=X, groups=groups)
        self.results = self.model.fit(disp=False)

        # Extract coefficients
        params = self.results.params
        bse = self.results.bse

        # Handle both Series and ndarray
        param_vals = params.values if hasattr(params, "values") else params
        bse_vals = bse.values if hasattr(bse, "values") else bse
        tvals = (
            self.results.tvalues.values
            if hasattr(self.results.tvalues, "values")
            else self.results.tvalues
        )
        pvals = (
            self.results.pvalues.values
            if hasattr(self.results.pvalues, "values")
            else self.results.pvalues
        )

        population_mu = {col: float(param_vals[i]) for i, col in enumerate(feature_cols)}
        population_sigma = {col: float(bse_vals[i]) for i, col in enumerate(feature_cols)}

        # Build coefficient table
        conf_int = self.results.conf_int()
        ci_lower = conf_int[:, 0] if hasattr(conf_int, "shape") else conf_int.iloc[:, 0].values
        ci_upper = conf_int[:, 1] if hasattr(conf_int, "shape") else conf_int.iloc[:, 1].values
        coef_table = pd.DataFrame(
            {
                "parameter": feature_cols,
                "coef": param_vals,
                "std_err": bse_vals,
                "z": tvals,
                "p_value": pvals,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
                "significant": pvals < 0.05,
            }
        )

        # MNL has no individual heterogeneity: all respondents get population mu
        resp_ids = data[resp_id_col].unique()
        individual_utilities: dict[str, dict[str, float]] = {
            resp_id: dict(population_mu) for resp_id in resp_ids
        }

        # Compute fit statistics manually since ConditionalResults lacks some attrs
        llf = float(self.results.llf)
        n_obs = int(self.results.nobs)
        n_params = len(self.results.params)

        # Null log-likelihood: each choice set has equal probability
        # Count unique groups to get number of choice sets
        n_choice_sets = len(np.unique(groups))
        n_alts_per_set = len(data) // n_choice_sets if n_choice_sets > 0 else 1
        llnull = n_choice_sets * np.log(1.0 / n_alts_per_set)

        # McFadden R²
        mc_fadden_r2 = 1.0 - (llf / llnull) if llnull != 0 else 0.0

        # AIC and BIC
        aic = -2 * llf + 2 * n_params
        bic = -2 * llf + n_params * np.log(n_obs)

        # Convergence: statsmodels ConditionalLogit exposes 'converged'
        # on the results object when the optimizer finished successfully.
        converged = bool(getattr(self.results, "converged", True))

        return MNLResult(
            converged=converged,
            population_mu=population_mu,
            population_sigma=population_sigma,
            individual_utilities=individual_utilities,
            log_likelihood=llf,
            null_log_likelihood=llnull,
            mc_fadden_r2=mc_fadden_r2,
            aic=aic,
            bic=bic,
            n_obs=n_obs,
            n_params=n_params,
            coef_table=coef_table,
        )

    def predict_probabilities(
        self,
        data: pd.DataFrame | None = None,
        feature_cols: list[str] | None = None,
        resp_id_col: str = "resp_id",
        task_id_col: str = "task_id",
    ) -> pd.Series:
        """Predict choice probabilities.

        Args:
            data: DataFrame to predict on. If None, uses training data.
            feature_cols: Feature columns. If None, uses training features.

        Returns:
            Series of predicted probabilities.
        """
        if self.results is None:
            raise RuntimeError("Model must be fit before prediction")

        if data is None:
            raise ValueError("data required for prediction")

        cols = feature_cols or self._feature_cols
        if cols is None:
            raise ValueError("feature_cols must be provided")

        X = data[cols].values
        # ConditionalLogit.predict() raises NotImplementedError in statsmodels
        # Compute probabilities manually: P = exp(X @ beta) / sum(exp(X @ beta)) per group
        beta = self.results.params
        beta_vals = beta.values if hasattr(beta, "values") else beta

        utilities = X @ beta_vals
        # Need groups for normalization; reconstruct from data
        groups = data.groupby([resp_id_col, task_id_col], sort=False).ngroup().values

        probs = np.zeros(len(utilities))
        for g in np.unique(groups):
            mask = groups == g
            u = utilities[mask]
            u_max = np.max(u)
            exp_u = np.exp(u - u_max)
            probs[mask] = exp_u / exp_u.sum()

        return pd.Series(probs, index=data.index)

    def get_model_fit(self) -> dict[str, Any]:
        """Return model fit statistics."""
        if self.results is None:
            raise RuntimeError("Model must be fit first")

        llf = float(self.results.llf)
        n_obs = int(self.results.nobs)
        n_params = len(self.results.params)

        # McFadden R²: 1 - LL_model / LL_null
        # Null model: equal probability for all alternatives in each choice set.
        # n_obs = n_choice_sets × n_alts, and we stored n_alts in fit().
        n_alts = getattr(self, "_n_alternatives", 3)
        n_choice_sets = n_obs // n_alts if n_obs >= n_alts else 1
        llnull = n_choice_sets * np.log(1.0 / n_alts)
        mc_fadden_r2 = 1.0 - (llf / llnull) if llnull != 0 else 0.0

        return {
            "log_likelihood": llf,
            "n_obs": n_obs,
            "n_params": n_params,
            "converged": bool(getattr(self.results, "converged", True)),
            "mc_fadden_r2": mc_fadden_r2,
            "aic": -2 * llf + 2 * n_params,
            "bic": -2 * llf + n_params * np.log(n_obs),
        }
