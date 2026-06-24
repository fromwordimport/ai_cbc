"""D-optimal experimental design for CBC questionnaires.

Uses a candidate-set + Fedorov exchange algorithm to maximise the
determinant of the information matrix, yielding statistically efficient
choice experiments.

Performance optimisations:
  * Pre-encodes the full candidate set once (O(C*P)).
  * Uses the matrix determinant lemma for rank-3 delta updates,
    reducing per-candidate evaluation from O(N*P^2 + P^3) to O(P^2).
  * Uses ``np.linalg.slogdet`` to avoid numerical overflow and for speed.
"""

from __future__ import annotations

from itertools import product
from typing import Any

import numpy as np

from aicbc.questionnaire.design.effects_coding import (
    encode_design_matrix,
    encode_profile,
)
from aicbc.questionnaire.design.efficiency import (
    a_efficiency,
    calculate_information_matrix,
    d_efficiency,
)
from aicbc.questionnaire.models import (
    Alternative,
    Attribute,
    CBCQuestionnaire,
    ChoiceSet,
    DesignParameters,
    ProhibitedPair,
)

# ---------------------------------------------------------------------------
# Candidate generation (unchanged public API)
# ---------------------------------------------------------------------------


def _generate_full_factorial(attributes: list[Attribute]) -> list[dict[str, Any]]:
    """Generate all possible attribute-level combinations."""
    level_lists = [[level.value for level in attr.levels] for attr in attributes]
    attr_ids = [attr.id for attr in attributes]
    return [dict(zip(attr_ids, combo, strict=True)) for combo in product(*level_lists)]


def _is_prohibited(profile: dict[str, Any], prohibited_pairs: list[ProhibitedPair]) -> bool:
    """Check if a profile violates any prohibited-pair constraint.

    Each ``ProhibitedPair`` contains one or more ``Condition`` objects
    that are AND-ed together.  Pairs themselves are OR-ed: *any* fully
    matching pair causes rejection.
    """
    for pair in prohibited_pairs:
        if all(profile.get(cond.attribute_id) == cond.level_value for cond in pair.conditions):
            return True
    return False


def generate_candidate_set(
    attributes: list[Attribute],
    prohibited_pairs: list[ProhibitedPair] | None = None,
) -> list[dict[str, Any]]:
    """Generate all legal product profile candidates.

    Filters out profiles that violate prohibited pair constraints.
    """
    all_profiles = _generate_full_factorial(attributes)
    if not prohibited_pairs:
        return all_profiles

    legal = [p for p in all_profiles if not _is_prohibited(p, prohibited_pairs)]
    return legal


# ---------------------------------------------------------------------------
# Precomputation helpers
# ---------------------------------------------------------------------------


def _profile_key(profile: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Convert a profile dict to a hashable key for fast duplicate checking."""
    return tuple(sorted(profile.items()))


def _precompute_candidate_vectors(
    candidate_set: list[dict[str, Any]], attributes: list[Attribute]
) -> np.ndarray:
    """Pre-encode every candidate profile into a (C, P) design-matrix array.

    This is the most expensive single-call precomputation step; its result
    is reused for every position-exchange evaluation.
    """
    if not candidate_set:
        return np.empty((0, 0))
    rows = [encode_profile(c, attributes) for c in candidate_set]
    return np.vstack(rows)


def _compute_info_zeroprior(encoded_design: np.ndarray, alts_per_set: int) -> np.ndarray:
    """Information matrix for a zero-parameter prior (all utilities equal).

    When beta=0 the choice probabilities are identical (1/J) within every
    set, so the per-set contribution simplifies to::

        M_s = (1/J) * X_s^T X_s - (1/J^2) * c_s c_s^T

    where c_s is the column-sum vector of X_s.  This is substantially
    faster than the general-purpose ``calculate_information_matrix`` and
    is the canonical call path inside ``d_optimal_design``.
    """
    if encoded_design.size == 0:
        return np.array([[0.0]])

    J = alts_per_set
    N, P = encoded_design.shape
    n_sets = N // J
    M = np.zeros((P, P))

    for s in range(n_sets):
        start = s * J
        end = start + J
        X_s = encoded_design[start:end]
        c_s = X_s.sum(axis=0)  # (P,)
        M += (1.0 / J) * (X_s.T @ X_s) - (1.0 / J**2) * np.outer(c_s, c_s)

    return M


def _random_initial_design_with_indices(
    candidate_set: list[dict[str, Any]],
    num_sets: int,
    alts_per_set: int,
    rng: np.random.Generator,
) -> tuple[list[dict[str, Any]], list[int]]:
    """Random initial design returning both profiles and their candidate-set indices.

    The indices allow fast array-based lookup of pre-encoded vectors.
    """
    n_needed = num_sets * alts_per_set

    if len(candidate_set) >= n_needed:
        indices = rng.choice(len(candidate_set), size=n_needed, replace=False)
    else:
        indices = rng.choice(len(candidate_set), size=n_needed, replace=True)

    profiles = [candidate_set[int(i)].copy() for i in indices]
    return profiles, [int(i) for i in indices]


# ---------------------------------------------------------------------------
# Core D-optimal algorithm
# ---------------------------------------------------------------------------


def d_optimal_design(
    attributes: list[Attribute],
    design_parameters: DesignParameters,
    prohibited_pairs: list[ProhibitedPair] | None = None,
    max_iterations: int = 1000,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run Fedorov exchange algorithm for D-optimal design.

    Args:
        attributes: Product attribute definitions.
        design_parameters: Design control parameters.
        prohibited_pairs: Optional prohibited attribute-level pairs.
        max_iterations: Maximum exchange iterations.
        seed: Random seed for reproducibility.

    Returns:
        Dictionary with keys: design, d_value, d_efficiency, a_efficiency, iterations.
    """
    num_sets = design_parameters.n_choice_sets
    J = design_parameters.n_alternatives  # alts_per_set
    N = num_sets * J  # total alternatives in design

    # ------------------------------------------------------------------
    # 1. Generate & pre-encode candidate set (done once)
    # ------------------------------------------------------------------
    candidate_set = generate_candidate_set(attributes, prohibited_pairs)
    if not candidate_set:
        raise ValueError("no legal profiles after applying prohibited pair constraints")

    candidate_vectors = _precompute_candidate_vectors(candidate_set, attributes)
    C = len(candidate_vectors)  # number of candidates
    P = candidate_vectors.shape[1] if C > 0 else 0

    if P == 0:
        raise ValueError("design matrix has zero parameters")

    candidate_keys = [_profile_key(c) for c in candidate_set]

    # ------------------------------------------------------------------
    # 2. Random initial design
    # ------------------------------------------------------------------
    rng = np.random.default_rng(seed)
    current_design, current_indices = _random_initial_design_with_indices(
        candidate_set, num_sets, J, rng
    )

    # Encoded current design: (N, P) view into candidate_vectors
    encoded_current = candidate_vectors[np.array(current_indices)].copy()

    # Per-set column-sum vectors c_s = sum_{alt in set} x_alt
    c_s = np.empty((num_sets, P))
    for s in range(num_sets):
        start = s * J
        c_s[s] = encoded_current[start : start + J].sum(axis=0)

    # Initial information matrix & log-determinant
    info_mat = _compute_info_zeroprior(encoded_current, J)

    # Stabilise against near-singularity (possible with poor initial draws)
    sign, current_logdet = np.linalg.slogdet(info_mat)
    if sign <= 0 or not np.isfinite(current_logdet):
        info_mat += np.eye(P) * 1e-10
        sign, current_logdet = np.linalg.slogdet(info_mat)
        if sign <= 0:
            raise RuntimeError(
                "initial information matrix is not positive-definite even after regularisation"
            )

    # ------------------------------------------------------------------
    # 3. Fedorov exchange iterations
    # ------------------------------------------------------------------
    iteration = 0
    improved = True
    # Minimum log-det improvement to accept a replacement (≈ 1e-12 in
    # determinant ratio, which is safely below any meaningful improvement).
    _log_threshold = 1e-14

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1

        for pos in range(N):
            set_idx = pos // J

            old_vec = encoded_current[pos]  # (P,)
            old_idx = current_indices[pos]  # int
            old_cs = c_s[set_idx]  # (P,)

            # Constants for rank-3 determinant update (see docstring below)
            v = (1.0 / J) * old_vec - (1.0 / J**2) * old_cs  # (P,)
            alpha = (J - 1.0) / J**2  # scalar

            # Compute M^{-1} once for this position
            try:
                M_inv = np.linalg.inv(info_mat)
            except np.linalg.LinAlgError:
                info_mat_reg = info_mat + np.eye(P) * 1e-10
                M_inv = np.linalg.inv(info_mat_reg)

            # c0 = v^T @ M^{-1} @ v (constant per position)
            c0 = float(v @ M_inv @ v)

            # ---- batch-determine a_i and b_i for ALL candidates ----
            # d_i = candidate_vectors[i] - old_vec  (C x P)
            d_mat = candidate_vectors - old_vec  # (C, P)
            # z_i = M^{-1} @ d_i  ->  z = d_mat @ M_inv  (C, P)
            z_mat = d_mat @ M_inv  # (C, P)
            # a_i = v^T @ z_i = v^T @ M^{-1} @ d_i                     (C,)
            a_vals = z_mat @ v  # (C,)
            # b_i = d_i^T @ z_i = d_i^T @ M^{-1} @ d_i                 (C,)
            b_vals = np.sum(d_mat * z_mat, axis=1)  # (C,)

            # det(I + S_i) = (1+a)^2 * (1+α·b) - α·a·b·(2+a) - c0·b
            # (derived from the 3×3 determinant formula; see module doc)
            det_ratios = (
                (1.0 + a_vals) ** 2 * (1.0 + alpha * b_vals)
                - alpha * a_vals * b_vals * (2.0 + a_vals)
                - c0 * b_vals
            )

            # ---- build mask of viable candidates ----
            mask = np.ones(C, dtype=bool)
            # Skip the candidate already at this position
            mask[current_indices[pos]] = False
            # Skip candidates that would create duplicates in this set
            set_start = set_idx * J
            set_end = set_start + J
            other_keys = {
                candidate_keys[current_indices[p]] for p in range(set_start, set_end) if p != pos
            }
            for ci in range(C):
                if mask[ci] and candidate_keys[ci] in other_keys:
                    mask[ci] = False
            # Skip non-positive determinant ratios (numerically unstable)
            mask &= det_ratios > 1e-300

            if not mask.any():
                continue

            # ---- pick best candidate ----
            best_local = int(np.argmax(det_ratios[mask]))
            best_ci = int(np.where(mask)[0][best_local])
            best_ratio = float(det_ratios[best_ci])

            logdet_delta = np.log(best_ratio)

            if logdet_delta > _log_threshold:
                # Execute replacement
                new_vec = candidate_vectors[best_ci]
                d = new_vec - old_vec  # (P,)

                # Rank-3 update to info_mat:
                #   M' = M + v·d^T + d·v^T + α·d·d^T
                info_mat += np.outer(v, d) + np.outer(d, v) + alpha * np.outer(d, d)

                # Update internal state
                encoded_current[pos] = new_vec
                current_indices[pos] = best_ci
                current_design[pos] = candidate_set[best_ci]
                c_s[set_idx] = old_cs + d

                # Redetermine log-det from updated info_mat to avoid drift
                sign, current_logdet = np.linalg.slogdet(info_mat)
                if sign <= 0:
                    # Degenerate design — rollback (shouldn't happen in practice)
                    info_mat -= np.outer(v, d) + np.outer(d, v) + alpha * np.outer(d, d)
                    encoded_current[pos] = old_vec
                    current_indices[pos] = old_idx  # restore
                    current_design[pos] = candidate_set[old_idx]
                    c_s[set_idx] = old_cs
                    sign, current_logdet = np.linalg.slogdet(info_mat)
                else:
                    improved = True

        # ---- periodic full recalibration to squash accumulated drift ----
        if improved and iteration % 10 == 0:
            info_full = _compute_info_zeroprior(encoded_current, J)
            sign, current_logdet = np.linalg.slogdet(info_full)
            if sign > 0:
                info_mat = info_full

    # ------------------------------------------------------------------
    # 4. Build output
    # ------------------------------------------------------------------
    choice_sets: list[ChoiceSet] = []
    for i in range(num_sets):
        start = i * J
        alts = [Alternative(alt_index=j, attributes=current_design[start + j]) for j in range(J)]
        choice_sets.append(ChoiceSet(choice_set_id=i + 1, alternatives=alts))

    # Final efficiency metrics (use the canonical function for accuracy)
    design_matrix_final = encode_design_matrix(current_design, attributes)
    info_final = calculate_information_matrix(design_matrix_final, alts_per_set=J)

    sign_d, logabsdet = np.linalg.slogdet(info_final)
    d_value = sign_d * np.exp(min(logabsdet, 700.0)) if sign_d > 0 else 0.0

    d_eff = d_efficiency(info_final)
    a_eff = a_efficiency(info_final)

    return {
        "design": choice_sets,
        "d_value": d_value,
        "d_efficiency": d_eff,
        "a_efficiency": a_eff,
        "iterations": iteration,
    }


# ---------------------------------------------------------------------------
# High-level questionnaire generator
# ---------------------------------------------------------------------------


def generate_d_optimal_questionnaire(
    study_id: str,
    attributes: list[Attribute],
    design_parameters: DesignParameters,
    prohibited_pairs: list[ProhibitedPair] | None = None,
    seed: int | None = None,
) -> CBCQuestionnaire:
    """Generate a CBC questionnaire using D-optimal design.

    Args:
        study_id: Parent study identifier.
        attributes: Product attributes with levels.
        design_parameters: Design control parameters.
        prohibited_pairs: Optional prohibited pairs.
        seed: Random seed for reproducibility.

    Returns:
        Generated CBC questionnaire with D-efficiency metrics.
    """
    result = d_optimal_design(
        attributes=attributes,
        design_parameters=design_parameters,
        prohibited_pairs=prohibited_pairs,
        seed=seed,
    )

    return CBCQuestionnaire(
        questionnaire_id=f"q-{study_id}-dopt",
        study_id=study_id,
        attributes=attributes,
        choice_sets=result["design"],
        design_parameters=design_parameters,
        d_efficiency=result["d_efficiency"],
        a_efficiency=result["a_efficiency"],
        iterations=result["iterations"],
    )
