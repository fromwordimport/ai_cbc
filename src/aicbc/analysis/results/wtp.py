"""Willingness-to-Pay (WTP) calculator.

WTP = -beta_feature / beta_price

Handles edge cases like positive price coefficients and extreme values.
"""

from __future__ import annotations

import pandas as pd

from aicbc.questionnaire.models import Attribute, AttributeType


class WTPCalculator:
    """Calculate WTP from individual utility estimates.

    Price is effects-coded as z-score: (price - μ) / σ.  The estimated
    β_price therefore operates on *standardised* units.  To recover
    CNY-denominated WTP we multiply by σ_price after computing the ratio.
    """

    def __init__(
        self,
        individual_utilities: pd.DataFrame,
        price_col: str = "price",
        price_std: float = 1.0,
    ) -> None:
        self.util = individual_utilities
        self.price_col = price_col
        self.price_std = price_std

        if price_col not in individual_utilities.columns:
            raise ValueError(f"Price column '{price_col}' not found")

    def compute_wtp(
        self,
        feature_col: str,
        feature_type: str = "continuous",
        level_diff: float | None = None,
    ) -> pd.Series:
        """Compute WTP for a single feature.

        Args:
            feature_col: Feature coefficient column name.
            feature_type: "continuous" or "categorical".
            level_diff: For categorical, the utility difference between levels.

        Returns:
            Series of WTP values (one per respondent).
        """
        beta_price = self.util[self.price_col]
        beta_feature = self.util[feature_col]

        # Check for positive price coefficients
        n_positive = (beta_price > 0).sum()
        if n_positive > 0:
            # Filter out positive price coefficients
            valid = beta_price < 0
            beta_price = beta_price[valid]
            beta_feature = beta_feature[valid]

        if feature_type == "continuous":
            wtp = -beta_feature / beta_price * self.price_std
        else:
            if level_diff is None:
                raise ValueError("level_diff required for categorical WTP")
            wtp = -level_diff / beta_price * self.price_std

        # Filter extreme values (beyond 99th percentile)
        q99 = wtp.quantile(0.99)
        q01 = wtp.quantile(0.01)
        wtp = wtp[(wtp >= q01) & (wtp <= q99)]

        return wtp

    def compute_all_wtp(
        self,
        attributes: list[Attribute],
    ) -> dict[str, dict]:
        """Compute WTP for all non-price attributes.

        Args:
            attributes: Ordered list of attribute definitions.

        Returns:
            Dict mapping attribute_id -> WTP statistics.
        """
        results: dict[str, dict] = {}

        for attr in attributes:
            if attr.id == self.price_col:
                continue

            if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
                # Compute WTP for moving from reference level to each other level.
                # In effects coding, beta_0..beta_{k-2} are level utilities and
                # beta_{k-1} = -(sum of others).  Level difference = beta_j - beta_i.
                n_levels = len(attr.levels)
                comparisons = []

                for i in range(1, n_levels):
                    from_level = str(attr.levels[0].value)
                    to_level = str(attr.levels[i].value)

                    # Build level difference across all respondents: beta_i - beta_0
                    # beta_0 is at column f"{attr.id}_0"
                    # beta_i (i < k-1) is at column f"{attr.id}_{i}"
                    # beta_{k-1} is -(sum of beta_0..beta_{k-2})
                    col_0 = f"{attr.id}_0"
                    if i < n_levels - 1:
                        col_i = f"{attr.id}_{i}"
                        if col_0 in self.util.columns and col_i in self.util.columns:
                            level_diff = self.util[col_i] - self.util[col_0]
                        else:
                            continue
                    else:
                        # Last level: beta_{k-1} = -sum(beta_0..beta_{k-2})
                        ref_cols = [
                            f"{attr.id}_{j}"
                            for j in range(n_levels - 1)
                            if f"{attr.id}_{j}" in self.util.columns
                        ]
                        if col_0 in self.util.columns and ref_cols:
                            last_level_util = -self.util[ref_cols].sum(axis=1)
                            level_diff = last_level_util - self.util[col_0]
                        else:
                            continue

                    # WTP = level_diff / (-beta_price) * price_std
                    wtp = self._compute_wtp_from_diff(level_diff)
                    if len(wtp) > 0:
                        comparisons.append(
                            {
                                "from_level": from_level,
                                "to_level": to_level,
                                "wtp_mean": float(wtp.mean()),
                                "wtp_median": float(wtp.median()),
                                "wtp_std": float(wtp.std()),
                                "ci_95_lower": float(wtp.quantile(0.025)),
                                "ci_95_upper": float(wtp.quantile(0.975)),
                                "n_valid": len(wtp),
                            }
                        )

                results[attr.id] = {"comparisons": comparisons}
            else:
                # Continuous attribute
                wtp = self.compute_wtp(attr.id, "continuous")
                results[attr.id] = {
                    "comparisons": [
                        {
                            "from_level": "baseline",
                            "to_level": "+1 unit",
                            "wtp_mean": float(wtp.mean()),
                            "wtp_median": float(wtp.median()),
                            "wtp_std": float(wtp.std()),
                            "ci_95_lower": float(wtp.quantile(0.025)),
                            "ci_95_upper": float(wtp.quantile(0.975)),
                            "n_valid": len(wtp),
                        }
                    ]
                }

        return results

    def _compute_wtp_from_diff(self, level_diff: pd.Series) -> pd.Series:
        """Compute WTP from a pre-computed level-difference series.

        WTP = level_diff / (-beta_price) * price_std
        Filters positive price coefficients and extreme values.
        """
        beta_price = self.util[self.price_col]
        valid = beta_price < 0
        beta_price_valid = beta_price[valid]
        diff_valid = level_diff[valid]

        wtp = diff_valid / (-beta_price_valid) * self.price_std

        # Filter extreme values (1st-99th percentile)
        q99 = wtp.quantile(0.99)
        q01 = wtp.quantile(0.01)
        return wtp[(wtp >= q01) & (wtp <= q99)]

    def price_coefficient_summary(self) -> dict[str, float]:
        """Summary statistics for price coefficient distribution."""
        beta_price = self.util[self.price_col]

        return {
            "mean": float(beta_price.mean()),
            "median": float(beta_price.median()),
            "std": float(beta_price.std()),
            "negative_rate": float((beta_price < 0).mean()),
            "n_positive_outliers": int((beta_price > 0).sum()),
        }
