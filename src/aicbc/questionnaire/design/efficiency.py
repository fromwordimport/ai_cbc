"""Efficiency metrics for experimental designs."""

from __future__ import annotations

def d_efficiency(info_matrix: np.ndarray, n_choice_sets: int | None = None) -> float:
    """Compute D-efficiency from an information matrix.

    Standard formula: det(M)^(1/p) / N, where N is the number of
    choice sets (the effective sample size per parameter).

    When *n_choice_sets* is None, falls back to the AM-GM ratio
    det^(1/p) / (trace/p), which is always in [0,1].

    Args:
        info_matrix: Information matrix X'WX (p x p).
        n_choice_sets: Number of choice sets for standard normalisation.

    Returns:
        D-efficiency. Higher is better.  Values >= 0.85 are excellent;
        values below 0.80 are unacceptable.
    """
    import numpy as np

    p = info_matrix.shape[0]
    if p == 0:
        return 0.0
    det = np.linalg.det(info_matrix)
    if det <= 0 or not np.isfinite(det):
        return 0.0
    geom_mean = float(det ** (1.0 / p))
    if n_choice_sets and n_choice_sets > 0:
        return geom_mean / n_choice_sets
    # Fallback: AM-GM normalisation (always in [0, 1])
    tr = np.trace(info_matrix)
    if tr <= 0 or not np.isfinite(tr):
        return 0.0
    return geom_mean / (tr / p)


def a_efficiency(info_matrix: np.ndarray) -> float:
    """Compute A-efficiency from an information matrix.

    Standard formula: A-efficiency = p / trace(M^(-1))

    where p = number of parameters and M^(-1) is the inverse of the
    information matrix.  Higher is better; reflects the average variance
    of the parameter estimates.

    Args:
        info_matrix: Information matrix X'WX (p x p).

    Returns:
        A-efficiency (0 to 1, higher is better).
    """
    import numpy as np

    p = info_matrix.shape[0]
    if p == 0:
        return 0.0
    try:
        inv_trace = np.trace(np.linalg.inv(info_matrix))
    except np.linalg.LinAlgError:
        return 0.0
    if inv_trace <= 0 or not np.isfinite(inv_trace):
        return 0.0
    return float(p / inv_trace)


def calculate_information_matrix(
    design_matrix: np.ndarray,
    alts_per_set: int = 3,
    beta_prior: np.ndarray | None = None,
) -> np.ndarray:
    """Approximate the information matrix for a conditional logit model.

    Computes the information matrix by choice set: for each set, the
    conditional choice probabilities are derived from the utilities of
    alternatives within that set only (not globally). This reflects the
    actual CBC data-generating process.

    Args:
        design_matrix: Encoded design matrix (n_alts x n_params).
        alts_per_set: Number of alternatives per choice set.
        beta_prior: Parameter prior (n_params,). Defaults to zeros.

    Returns:
        Information matrix (n_params x n_params).
    """
    import numpy as np

    if design_matrix.size == 0:
        return np.array([[0.0]])

    n_alts, n_params = design_matrix.shape
    n_sets = n_alts // alts_per_set
    if beta_prior is None:
        beta_prior = np.zeros(n_params)

    total_info = np.zeros((n_params, n_params))

    for s in range(n_sets):
        start = s * alts_per_set
        end = start + alts_per_set
        x_set = design_matrix[start:end]

        utilities = x_set @ beta_prior
        # Numerical stability within the choice set
        utilities = utilities - np.max(utilities)
        exp_utils = np.exp(utilities)
        probs = exp_utils / np.sum(exp_utils)

        # Conditional logit information contribution for this choice set
        w = np.diag(probs) - np.outer(probs, probs)
        total_info += x_set.T @ w @ x_set

    # Normalise by the number of choice sets so that efficiency metrics are
    # scale-invariant and bounded in [0, 1].
    return total_info / max(n_sets, 1)
