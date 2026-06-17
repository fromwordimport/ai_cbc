"""Attribute importance calculator.

Computes attribute importance from individual-level utility estimates.
Importance = attribute range / sum of all attribute ranges.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aicbc.questionnaire.models import Attribute, AttributeType


def compute_importance(
    individual_utilities: pd.DataFrame,
    attributes: list[Attribute],
    price_std: float = 1.0,
) -> pd.DataFrame:
    """Compute attribute importance for each respondent.

    Formula: Importance_attr = Range_attr / sum(Range_all_attrs)
    where Range_attr = max(level utility) - min(level utility)

    For price attributes encoded as z-score, range is corrected by
    price_std to recover original-unit importance: |beta| * range / std.

    Args:
        individual_utilities: DataFrame (n_resp x n_params) of utility estimates.
        attributes: Ordered list of attribute definitions.
        price_std: Standard deviation of price level values used in z-score
                   encoding (default 1.0 for no correction).

    Returns:
        DataFrame (n_resp x n_attributes) of importance values.
    """
    importance_by_resp = []

    import numpy as np
    import pandas as pd

    for _resp_id, util_row in individual_utilities.iterrows():
        attr_ranges: dict[str, float] = {}

        for attr in attributes:
            if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
                # Recover all level utilities from effects coding
                level_utils = _recover_level_utilities(util_row, attr)
                attr_ranges[attr.id] = float(np.max(level_utils) - np.min(level_utils))
            elif attr.type == AttributeType.PRICE:
                # Price: |coefficient| * price_range / price_std
                # Beta is on standardized units (z-score), so we divide by
                # price_std to recover original-unit importance.
                price_col = attr.id
                if price_col in util_row:
                    prices = [float(level.value) for level in attr.levels]
                    price_range = max(prices) - min(prices)
                    std = price_std if price_std > 0 else 1.0
                    attr_ranges[attr.id] = abs(float(util_row[price_col])) * price_range / std
                else:
                    attr_ranges[attr.id] = 0.0
            else:
                # Continuous: use |coefficient| * range
                col = attr.id
                if col in util_row:
                    attr_ranges[attr.id] = abs(float(util_row[col])) * 10.0
                else:
                    attr_ranges[attr.id] = 0.0

        # Normalize to sum to 1
        total_range = sum(attr_ranges.values())
        if total_range > 0:
            importance = {k: v / total_range for k, v in attr_ranges.items()}
        else:
            importance = dict.fromkeys(attr_ranges, 0.0)

        importance_by_resp.append(importance)

    return pd.DataFrame(importance_by_resp, index=individual_utilities.index)


def _recover_level_utilities(
    util_row: pd.Series,
    attribute: Attribute,
) -> np.ndarray:
    """Recover all level utilities from effects-coded parameters.

    For k levels with effects coding, we have k-1 parameters.
    The last level utility = -(sum of other level utilities).
    """
    n_levels = len(attribute.levels)
    import numpy as np

    params = []

    for i in range(n_levels - 1):
        param_name = f"{attribute.id}_{i}"
        params.append(float(util_row.get(param_name, 0.0)))

    # Last level is negative sum
    params.append(-sum(params))

    return np.array(params)


def aggregate_importance(
    importance_df: pd.DataFrame,
    confidence: float = 0.95,
) -> pd.DataFrame:
    """Aggregate individual importance to population-level statistics.

    Args:
        importance_df: DataFrame from compute_importance().
        confidence: Confidence level for intervals.

    Returns:
        DataFrame with columns: mean, std, median, min, max,
        q25, q75, ci_lower, ci_upper
    """
    alpha = 1 - confidence
    lower_q = alpha / 2
    upper_q = 1 - alpha / 2

    import pandas as pd

    return pd.DataFrame(
        {
            "mean": importance_df.mean(),
            "std": importance_df.std(),
            "median": importance_df.median(),
            "min": importance_df.min(),
            "max": importance_df.max(),
            "q25": importance_df.quantile(0.25),
            "q75": importance_df.quantile(0.75),
            f"ci_{int(confidence * 100)}_lower": importance_df.quantile(lower_q),
            f"ci_{int(confidence * 100)}_upper": importance_df.quantile(upper_q),
        }
    )
