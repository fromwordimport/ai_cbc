"""Efficiency metrics for experimental designs."""

from __future__ import annotations

import numpy as np


def d_efficiency(info_matrix: np.ndarray) -> float:
    """Compute D-efficiency from an information matrix.

    Uses the ratio of the geometric mean to the arithmetic mean of
    the eigenvalues (equivalently: det^(1/p) / (trace/p)).

    By the AM-GM inequality this is always in [0, 1], with 1.0
    achieved when all eigenvalues are equal (perfectly balanced design).

    Args:
        info_matrix: Information matrix X'WX (p x p).

    Returns:
        D-efficiency in [0, 1]. Higher is better.
    """
    p = info_matrix.shape[0]
    if p == 0:
        return 0.0
    det = np.linalg.det(info_matrix)
    tr = np.trace(info_matrix)
    if det <= 0 or tr <= 0 or not np.isfinite(det) or not np.isfinite(tr):
        return 0.0
    return float((det ** (1.0 / p)) / (tr / p))


def a_efficiency(info_matrix: np.ndarray) -> float:
    """Compute A-efficiency from an information matrix.

    A-efficiency = p / trace(X'WX)

    where p = number of parameters. Higher is better.

    Args:
        info_matrix: Information matrix X'WX (p x p).

    Returns:
        A-efficiency in [0, 1].
    """
    tr = np.trace(info_matrix)
    if tr <= 0 or not np.isfinite(tr):
        return 0.0
    p = info_matrix.shape[0]
    return float(p / tr)


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

    return total_info
