"""D-optimal experimental design for CBC questionnaires.

Uses a candidate-set + Fedorov exchange algorithm to maximise the
determinant of the information matrix, yielding statistically efficient
choice experiments.
"""

from __future__ import annotations

from itertools import product
from typing import Any

import numpy as np

from aicbc.questionnaire.design.effects_coding import encode_design_matrix
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


def _generate_full_factorial(attributes: list[Attribute]) -> list[dict[str, Any]]:
    """Generate all possible attribute-level combinations."""
    level_lists = [[level.value for level in attr.levels] for attr in attributes]
    attr_ids = [attr.id for attr in attributes]
    return [
        dict(zip(attr_ids, combo, strict=True))
        for combo in product(*level_lists)
    ]


def _is_prohibited(profile: dict[str, Any], prohibited_pairs: list[ProhibitedPair]) -> bool:
    """Check if a profile violates any prohibited pair constraint."""
    return any(
        profile.get(pair.attribute_id) == pair.level_value for pair in prohibited_pairs
    )


def _has_duplicates_in_set(
    profiles: list[dict[str, Any]], set_start: int, set_end: int
) -> bool:
    """Check for duplicate profiles within a choice set range."""
    seen: set[tuple[tuple[str, Any], ...]] = set()
    for i in range(set_start, set_end):
        key = tuple(sorted(profiles[i].items()))
        if key in seen:
            return True
        seen.add(key)
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


def _random_initial_design(
    candidate_set: list[dict[str, Any]],
    num_sets: int,
    alts_per_set: int,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Randomly initialise a design by sampling from candidates."""
    rng = np.random.default_rng(seed)
    n_needed = num_sets * alts_per_set

    if len(candidate_set) >= n_needed:
        indices = rng.choice(len(candidate_set), size=n_needed, replace=False)
    else:
        # With replacement if candidate pool is too small
        indices = rng.choice(len(candidate_set), size=n_needed, replace=True)

    return [candidate_set[i].copy() for i in indices]


def d_optimal_design(
    attributes: list[Attribute],
    design_parameters: DesignParameters,
    prohibited_pairs: list[ProhibitedPair] | None = None,
    max_iterations: int = 1000,
    convergence_threshold: float = 1e-9,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run Fedorov exchange algorithm for D-optimal design.

    Args:
        attributes: Product attribute definitions.
        design_parameters: Design control parameters.
        prohibited_pairs: Optional prohibited attribute-level pairs.
        max_iterations: Maximum exchange iterations.
        convergence_threshold: Stop when no improvement exceeds this.
        seed: Random seed for reproducibility.

    Returns:
        Dictionary with keys: design, d_value, d_efficiency, a_efficiency, iterations.
    """
    num_sets = design_parameters.n_choice_sets
    alts_per_set = design_parameters.n_alternatives

    # 1. Generate candidate set
    candidate_set = generate_candidate_set(attributes, prohibited_pairs)
    if not candidate_set:
        raise ValueError("no legal profiles after applying prohibited pair constraints")

    # 2. Random initialise
    current_design = _random_initial_design(
        candidate_set, num_sets, alts_per_set, seed=seed
    )
    design_matrix_current = encode_design_matrix(current_design, attributes)
    info_current = calculate_information_matrix(
        design_matrix_current, alts_per_set=alts_per_set
    )
    current_d_value = float(np.linalg.det(info_current))

    iteration = 0
    improved = True

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1

        for set_idx in range(num_sets):
            for alt_idx in range(alts_per_set):
                pos = set_idx * alts_per_set + alt_idx
                best_replacement: dict[str, Any] | None = None
                best_d_value = current_d_value

                for candidate in candidate_set:
                    # Skip if identical to current
                    if candidate == current_design[pos]:
                        continue

                    # Create trial design
                    trial_design = list(current_design)
                    trial_design[pos] = candidate

                    # Check for duplicates within this choice set
                    set_start = set_idx * alts_per_set
                    set_end = set_start + alts_per_set
                    if _has_duplicates_in_set(trial_design, set_start, set_end):
                        continue

                    # Evaluate D-value
                    design_matrix_new = encode_design_matrix(trial_design, attributes)
                    info_new = calculate_information_matrix(
                        design_matrix_new, alts_per_set=alts_per_set
                    )
                    new_d_value = float(np.linalg.det(info_new))

                    if new_d_value > best_d_value + convergence_threshold:
                        best_d_value = new_d_value
                        best_replacement = candidate

                # Execute best replacement for this position
                if best_replacement is not None:
                    current_design[pos] = best_replacement
                    current_d_value = best_d_value
                    improved = True

    # Convert to choice sets
    choice_sets: list[ChoiceSet] = []
    for i in range(num_sets):
        start = i * alts_per_set
        alts = [
            Alternative(alt_index=j, attributes=current_design[start + j])
            for j in range(alts_per_set)
        ]
        choice_sets.append(ChoiceSet(choice_set_id=i + 1, alternatives=alts))

    # Final efficiency metrics
    design_matrix_final = encode_design_matrix(current_design, attributes)
    info_final = calculate_information_matrix(
        design_matrix_final, alts_per_set=alts_per_set
    )

    d_eff = d_efficiency(info_final)
    a_eff = a_efficiency(info_final)

    return {
        "design": choice_sets,
        "d_value": current_d_value,
        "d_efficiency": d_eff,
        "a_efficiency": a_eff,
        "iterations": iteration,
    }


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
        choice_sets=result["design"],
        design_parameters=design_parameters,
        d_efficiency=result["d_efficiency"],
        a_efficiency=result["a_efficiency"],
        iterations=result["iterations"],
    )
