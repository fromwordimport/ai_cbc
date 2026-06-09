"""Effects coding utilities for CBC design matrices.

Effects coding (also called deviation coding) represents k levels with k-1
binary variables where the last level is coded as the negative sum of the
others. This makes parameters sum to zero, which is the convention expected
by the downstream analysis subsystem.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from aicbc.questionnaire.models import Attribute, AttributeType


def _build_level_index_map(attribute: Attribute) -> dict[Any, int]:
    """Return a mapping from level value to its 0-based index."""
    return {level.value: i for i, level in enumerate(attribute.levels)}


def effects_encode_categorical(value: Any, attribute: Attribute) -> np.ndarray:
    """Effects-code a single categorical level.

    For k levels, returns a (k-1,) vector. The i-th level (0 <= i < k-1)
    is encoded as a one-hot vector with 1 at position i. The last level
    is recovered as the negative sum of all other level parameters.

    Example (3 levels: A, B, C):
        A -> [ 1,  0]
        B -> [ 0,  1]
        C -> [-1, -1]   (recovered as -(A+B))
    """
    n_levels = len(attribute.levels)
    if n_levels < 2:
        raise ValueError("effects coding requires at least 2 levels")

    idx_map = _build_level_index_map(attribute)
    if value not in idx_map:
        raise ValueError(f"value '{value}' not found in attribute '{attribute.id}'")

    idx = idx_map[value]
    encoded = np.zeros(n_levels - 1, dtype=np.float64)
    if idx < n_levels - 1:
        encoded[idx] = 1.0
    else:
        # Last level: all -1
        encoded[:] = -1.0
    return encoded


def effects_encode_price(value: float, attribute: Attribute) -> np.ndarray:
    """Encode a price value as a standardised continuous variable.

    Standardises to mean 0, std 1 based on the attribute's level values
    so that price parameters are on a comparable scale to effects-coded
    categorical parameters.
    """
    prices = [float(level.value) for level in attribute.levels]
    mean = sum(prices) / len(prices)
    std = np.std(prices, ddof=0)
    if std == 0:
        return np.array([0.0], dtype=np.float64)
    return np.array([(float(value) - mean) / std], dtype=np.float64)


def encode_profile(
    profile: dict[str, Any], attributes: list[Attribute]
) -> np.ndarray:
    """Encode a single product profile into a design-matrix row.

    Concatenates effects-coded categorical/ordinal attributes and
    continuous/price attributes in the order of *attributes*.

    Args:
        profile: Mapping {attribute_id: level_value}.
        attributes: Ordered list of attribute definitions.

    Returns:
        1-D numpy array of encoded values.
    """
    parts: list[np.ndarray] = []
    for attr in attributes:
        if attr.id not in profile:
            raise ValueError(f"profile missing attribute '{attr.id}'")
        value = profile[attr.id]

        if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
            parts.append(effects_encode_categorical(value, attr))
        elif attr.type == AttributeType.CONTINUOUS:
            parts.append(np.array([float(value)], dtype=np.float64))
        elif attr.type == AttributeType.PRICE:
            parts.append(effects_encode_price(float(value), attr))
        else:
            raise ValueError(f"unsupported attribute type: {attr.type}")

    return np.concatenate(parts) if parts else np.array([], dtype=np.float64)


def encode_design_matrix(
    profiles: list[dict[str, Any]], attributes: list[Attribute]
) -> np.ndarray:
    """Encode a list of profiles into a design matrix X.

    Args:
        profiles: List of profile dicts, one per alternative.
        attributes: Ordered list of attribute definitions.

    Returns:
        2-D array of shape (n_profiles, n_params).
    """
    rows = [encode_profile(p, attributes) for p in profiles]
    if not rows:
        return np.array([])
    return np.vstack(rows)


def n_parameters(attributes: list[Attribute]) -> int:
    """Return the total number of parameters for effects-coded attributes.

    Categorical/ordinal with k levels -> k-1 parameters.
    Continuous/price -> 1 parameter each.
    """
    total = 0
    for attr in attributes:
        if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
            total += len(attr.levels) - 1
        else:
            total += 1
    return total
