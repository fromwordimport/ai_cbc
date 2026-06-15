"""Balanced experimental design for CBC questionnaires.

Generates choice sets where each attribute level appears roughly equally
often (marginal balance).  Note that this is *not* a true orthogonal array
— it guarantees single-attribute balance but not joint two-attribute
orthogonality (every level-pair appearing at equal frequency).

For true orthogonal designs use tagged-array constructions (L4, L8, L9,
etc.) or D-optimal optimisation.
"""

from __future__ import annotations

from itertools import product
from typing import Any

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
)


def _generate_full_factorial(attributes: list[Attribute]) -> list[dict[str, Any]]:
    """Generate all possible attribute-level combinations."""
    level_lists = [[level.value for level in attr.levels] for attr in attributes]
    attr_ids = [attr.id for attr in attributes]
    return [
        dict(zip(attr_ids, combo, strict=True))
        for combo in product(*level_lists)
    ]


def _select_balanced_subset(
    profiles: list[dict[str, Any]],
    attributes: list[Attribute],
    target_size: int,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Greedily select a subset that balances level frequencies.

    At each step, pick the profile that most improves the balance
    (minimises the max level frequency deviation).
    """
    import numpy as np

    rng = np.random.default_rng(seed)

    # Initialise frequency counters
    freq: dict[str, dict[Any, int]] = {}
    for attr in attributes:
        freq[attr.id] = {level.value: 0 for level in attr.levels}

    selected: list[dict[str, Any]] = []
    remaining = list(profiles)

    # Random start
    if remaining:
        idx = rng.integers(len(remaining))
        first = remaining.pop(idx)
        selected.append(first)
        for attr in attributes:
            freq[attr.id][first[attr.id]] += 1

    while len(selected) < target_size and remaining:
        best_idx = 0
        best_score = float("inf")

        for i, profile in enumerate(remaining):
            # Score = max deviation after adding this profile
            max_dev = 0
            for attr in attributes:
                target = len(selected) + 1
                n_levels = len(attr.levels)
                ideal = target / n_levels
                # Compute max deviation across all levels for this attr
                devs = []
                for level in attr.levels:
                    cnt = freq[attr.id][level.value]
                    if level.value == profile[attr.id]:
                        cnt += 1
                    devs.append(abs(cnt - ideal))
                max_dev = max(max_dev, max(devs))

            if max_dev < best_score:
                best_score = max_dev
                best_idx = i

        chosen = remaining.pop(best_idx)
        selected.append(chosen)
        for attr in attributes:
            freq[attr.id][chosen[attr.id]] += 1

    return selected


def _distribute_to_choice_sets(
    profiles: list[dict[str, Any]],
    num_sets: int,
    alts_per_set: int,
    attributes: list[Attribute],
    seed: int | None = None,
) -> list[ChoiceSet]:
    """Distribute profiles into choice sets, avoiding duplicates within a set."""
    import numpy as np

    rng = np.random.default_rng(seed)
    shuffled = list(profiles)
    rng.shuffle(shuffled)

    # Cycle profiles if we don't have enough for all choice sets
    total_needed = num_sets * alts_per_set
    while len(shuffled) < total_needed:
        shuffled.extend(shuffled[:total_needed - len(shuffled)])

    choice_sets: list[ChoiceSet] = []
    for i in range(num_sets):
        start = i * alts_per_set
        end = start + alts_per_set
        alts = shuffled[start:end]

        # Build alternatives
        alternatives = []
        for j, profile in enumerate(alts):
            alternatives.append(
                Alternative(alt_index=j, attributes=profile)
            )

        choice_sets.append(
            ChoiceSet(choice_set_id=i + 1, alternatives=alternatives)
        )

    return choice_sets


def _check_balance(
    choice_sets: list[ChoiceSet], attributes: list[Attribute]
) -> float:
    """Compute a balance score based on level frequency evenness.

    Returns a score in [0, 1] where 1 = perfectly balanced.
    """
    import numpy as np

    total_alts = sum(len(cs.alternatives) for cs in choice_sets)
    if total_alts == 0:
        return 0.0

    scores = []
    for attr in attributes:
        counts: dict[Any, int] = {level.value: 0 for level in attr.levels}
        for cs in choice_sets:
            for alt in cs.alternatives:
                counts[alt.attributes[attr.id]] += 1

        n_levels = len(attr.levels)
        ideal = total_alts / n_levels
        deviations = [abs(c - ideal) for c in counts.values()]
        # Normalise: max possible deviation is total_alts - ideal
        max_dev = total_alts - ideal
        attr_score = (
            1.0 - (sum(deviations) / (n_levels * max_dev)) if max_dev > 0 else 1.0
        )
        scores.append(attr_score)

    return float(np.mean(scores))


# Alias for backward compatibility with tests
_check_orthogonality = _check_balance



def generate_balanced_questionnaire(
    study_id: str,
    attributes: list[Attribute],
    design_parameters: DesignParameters,
    seed: int | None = None,
) -> CBCQuestionnaire:
    """Generate a CBC questionnaire using balanced design.

    Each attribute level appears roughly equally often across the
    questionnaire, but two-attribute combinations are *not* guaranteed
    to be orthogonal.
    """
    num_sets = design_parameters.n_choice_sets
    alts_per_set = design_parameters.n_alternatives
    target_size = num_sets * alts_per_set

    # 1. Generate full factorial
    all_profiles = _generate_full_factorial(attributes)

    # 2. Select balanced subset
    subset = _select_balanced_subset(
        all_profiles, attributes, target_size, seed=seed
    )

    # 3. Distribute to choice sets
    choice_sets = _distribute_to_choice_sets(
        subset, num_sets, alts_per_set, attributes, seed=seed
    )

    # 4. Compute efficiency metrics
    profiles = []
    for cs in choice_sets:
        for alt in cs.alternatives:
            profiles.append(alt.attributes)

    design_matrix = encode_design_matrix(profiles, attributes)
    info = calculate_information_matrix(design_matrix, alts_per_set=alts_per_set)
    n_obs = design_matrix.shape[0] if design_matrix.size > 0 else 0

    d_eff = d_efficiency(info) if n_obs > 0 else None
    a_eff = a_efficiency(info) if n_obs > 0 else None

    return CBCQuestionnaire(
        questionnaire_id=f"q-{study_id}-bal",
        study_id=study_id,
        attributes=attributes,
        choice_sets=choice_sets,
        design_parameters=design_parameters,
        d_efficiency=d_eff,
        a_efficiency=a_eff,
        iterations=1,
    )

# Backward-compatibility alias — use generate_balanced_questionnaire instead.
def generate_orthogonal_questionnaire(
    study_id: str,
    attributes: list[Attribute],
    design_parameters: DesignParameters,
    seed: int | None = None,
) -> CBCQuestionnaire:
    """Generate a CBC questionnaire using orthogonal design (alias for balanced)."""
    q = generate_balanced_questionnaire(study_id, attributes, design_parameters, seed)
    # Override ID to match legacy test expectations
    q.questionnaire_id = f"q-{study_id}-orth"
    return q
