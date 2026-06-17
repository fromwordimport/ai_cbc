"""Business-rule validation for CBC analysis results.

Validates analysis outputs against domain-specific business rules before
UAT sign-off.  Covers:

1. Price coefficient sign (must be negative)
2. WTP plausibility (within category-specific bounds)
3. Attribute level monotonicity (directional expectations)
4. Segment comparison & market simulation sanity checks

These validators are designed to be invoked both as pytest test cases
and as standalone scripts for CI / pre-UAT gating.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# 1.  Domain constants (dishwasher category)
# ---------------------------------------------------------------------------

# Expected monotonic directions for attribute level utilities.
# Key = attribute_id, value = list of level values in INCREASING preference order.
# A level utility that *decreases* along this list triggers a warning.
MONOTONIC_EXPECTATIONS: dict[str, list[str | float]] = {
    "capacity": ["6套", "10套", "13套"],  # larger capacity → higher utility
    "energy": ["二级", "一级", "超一级"],  # better efficiency → higher utility
    "features": ["基础", "智能", "全能"],  # more features → higher utility
}

# WTP plausibility bounds per attribute upgrade (CNY).
# Based on dishwasher category business intuition (docs/洗碗机CBC实验设计方案.md §5.1).
WTP_BOUNDS: dict[str, tuple[float, float]] = {
    "capacity": (0.0, 3000.0),  # 6套→13套 最大合理溢价
    "installation": (0.0, 1500.0),  # 台式→嵌入式/水槽式
    "features": (0.0, 2000.0),  # 基础→全能
    "brand": (0.0, 2500.0),  # 品牌升级溢价
    "energy": (0.0, 800.0),  # 能效升级
}

# Minimum acceptable negative rate for price coefficients.
PRICE_NEGATIVE_RATE_MIN = 0.95

# Maximum acceptable mean price coefficient (must be < 0).
PRICE_MEAN_MAX = 0.0


# ---------------------------------------------------------------------------
# 2.  Validation result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of a single business-rule check."""

    rule_name: str
    passed: bool
    severity: str  # "CRITICAL", "HIGH", "WARNING", "INFO"
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "details": self.details or {},
        }


# ---------------------------------------------------------------------------
# 3.  Price coefficient validator
# ---------------------------------------------------------------------------


def validate_price_coefficient(
    price_coefficients: pd.Series,
    *,
    negative_rate_min: float = PRICE_NEGATIVE_RATE_MIN,
    mean_max: float = PRICE_MEAN_MAX,
) -> ValidationResult:
    """Validate that price utility coefficients are negative.

    Args:
        price_coefficients: Series of individual price beta estimates.
        negative_rate_min: Minimum fraction that must be negative.
        mean_max: Maximum allowed mean (must be < 0).

    Returns:
        ValidationResult with CRITICAL severity if business rule is violated.
    """
    n_total = len(price_coefficients)
    n_negative = int((price_coefficients < 0).sum())
    negative_rate = n_negative / n_total if n_total > 0 else 0.0
    mean_price = float(price_coefficients.mean())

    details = {
        "n_total": n_total,
        "n_negative": n_negative,
        "negative_rate": round(negative_rate, 4),
        "mean": round(mean_price, 6),
        "n_positive_outliers": int((price_coefficients > 0).sum()),
    }

    if negative_rate < negative_rate_min:
        return ValidationResult(
            rule_name="price_coefficient_negative",
            passed=False,
            severity="CRITICAL",
            message=(
                f"Price coefficient negative rate {negative_rate:.2%} "
                f"below minimum {negative_rate_min:.0%}. "
                f"Mean={mean_price:.4f}."
            ),
            details=details,
        )

    if mean_price >= mean_max:
        return ValidationResult(
            rule_name="price_coefficient_negative",
            passed=False,
            severity="CRITICAL",
            message=(
                f"Mean price coefficient {mean_price:.4f} is not negative (threshold < {mean_max})."
            ),
            details=details,
        )

    return ValidationResult(
        rule_name="price_coefficient_negative",
        passed=True,
        severity="INFO",
        message=(f"Price coefficients OK: {negative_rate:.1%} negative, mean={mean_price:.4f}."),
        details=details,
    )


# ---------------------------------------------------------------------------
# 4.  WTP plausibility validator
# ---------------------------------------------------------------------------


def validate_wtp_plausibility(
    wtp_results: dict[str, dict],
    bounds: dict[str, tuple[float, float]] | None = None,
) -> list[ValidationResult]:
    """Validate WTP estimates are within business-plausible ranges.

    Args:
        wtp_results: Output from WTPCalculator.compute_all_wtp().
            Dict mapping attribute_id -> {"comparisons": [...]}.
        bounds: Per-attribute (lower, upper) bounds. Defaults to WTP_BOUNDS.

    Returns:
        List of ValidationResult, one per attribute comparison.
    """
    if bounds is None:
        bounds = WTP_BOUNDS

    results: list[ValidationResult] = []

    for attr_id, attr_data in wtp_results.items():
        if attr_id not in bounds:
            # Unknown attribute — skip or flag depending on policy
            continue

        lower, upper = bounds[attr_id]
        comparisons = attr_data.get("comparisons", [])

        for comp in comparisons:
            wtp_mean = comp.get("wtp_mean", 0.0)
            from_level = comp.get("from_level", "?")
            to_level = comp.get("to_level", "?")

            if wtp_mean < lower or wtp_mean > upper:
                results.append(
                    ValidationResult(
                        rule_name=f"wtp_plausibility_{attr_id}",
                        passed=False,
                        severity="HIGH",
                        message=(
                            f"WTP for {attr_id} ({from_level}→{to_level}) "
                            f"= ¥{wtp_mean:.0f} outside bounds "
                            f"[¥{lower:.0f}, ¥{upper:.0f}]."
                        ),
                        details={
                            "attribute": attr_id,
                            "from_level": from_level,
                            "to_level": to_level,
                            "wtp_mean": wtp_mean,
                            "bounds": [lower, upper],
                        },
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        rule_name=f"wtp_plausibility_{attr_id}",
                        passed=True,
                        severity="INFO",
                        message=(
                            f"WTP for {attr_id} ({from_level}→{to_level}) "
                            f"= ¥{wtp_mean:.0f} within bounds."
                        ),
                        details={
                            "attribute": attr_id,
                            "from_level": from_level,
                            "to_level": to_level,
                            "wtp_mean": wtp_mean,
                            "bounds": [lower, upper],
                        },
                    )
                )

    return results


# ---------------------------------------------------------------------------
# 5.  Attribute level monotonicity validator
# ---------------------------------------------------------------------------


def validate_level_monotonicity(
    individual_utilities: pd.DataFrame,
    attributes: list[dict[str, Any]],
    expectations: dict[str, list[str | float]] | None = None,
) -> list[ValidationResult]:
    """Check that recovered level utilities follow expected monotonic order.

    Uses effects-coding recovery (same logic as importance.py) to compute
    level utilities, then checks directional expectations.

    Args:
        individual_utilities: DataFrame (n_resp x n_params) of utility estimates.
        attributes: List of attribute spec dicts with 'id', 'type', 'levels'.
        expectations: attribute_id -> ordered level values. Defaults to
            MONOTONIC_EXPECTATIONS.

    Returns:
        List of ValidationResult per checked attribute.
    """
    if expectations is None:
        expectations = MONOTONIC_EXPECTATIONS

    results: list[ValidationResult] = []

    # Build attribute lookup
    attr_map = {a["id"]: a for a in attributes}

    for attr_id, expected_order in expectations.items():
        if attr_id not in attr_map:
            results.append(
                ValidationResult(
                    rule_name=f"level_monotonicity_{attr_id}",
                    passed=False,
                    severity="WARNING",
                    message=f"Attribute '{attr_id}' not found in study definition.",
                )
            )
            continue

        attr = attr_map[attr_id]
        levels = attr.get("levels", [])
        n_levels = len(levels)

        if n_levels < 2:
            continue

        # Check that required effect-coded parameter columns are present
        required_params = [f"{attr_id}_{i}" for i in range(n_levels - 1)]
        missing_params = [p for p in required_params if p not in individual_utilities.columns]
        if missing_params:
            results.append(
                ValidationResult(
                    rule_name=f"level_monotonicity_{attr_id}",
                    passed=False,
                    severity="WARNING",
                    message=(
                        f"Attribute '{attr_id}' is missing required utility "
                        f"parameter columns: {missing_params}."
                    ),
                    details={
                        "attribute": attr_id,
                        "missing_parameters": missing_params,
                        "expected_parameters": required_params,
                    },
                )
            )
            continue

        # Recover level utilities for each respondent
        # Same logic as _recover_level_utilities in importance.py
        level_utils_matrix = []
        for _resp_id, util_row in individual_utilities.iterrows():
            params = []
            for i in range(n_levels - 1):
                param_name = f"{attr_id}_{i}"
                params.append(float(util_row.get(param_name, 0.0)))
            params.append(-sum(params))
            level_utils_matrix.append(params)

        level_utils_df = pd.DataFrame(level_utils_matrix, columns=levels)
        mean_utils = level_utils_df.mean()

        # Check monotonicity: expected_order[0] < expected_order[1] < ...
        violations = 0
        violation_pairs: list[tuple[str, str, float, float]] = []

        for i in range(len(expected_order) - 1):
            lo = expected_order[i]
            hi = expected_order[i + 1]
            if lo not in mean_utils.index or hi not in mean_utils.index:
                continue
            if mean_utils[lo] > mean_utils[hi]:
                violations += 1
                violation_pairs.append(
                    (str(lo), str(hi), float(mean_utils[lo]), float(mean_utils[hi]))
                )

        if violations > 0:
            results.append(
                ValidationResult(
                    rule_name=f"level_monotonicity_{attr_id}",
                    passed=False,
                    severity="HIGH",
                    message=(
                        f"Attribute '{attr_id}' has {violations} monotonicity "
                        f"violations among mean level utilities."
                    ),
                    details={
                        "attribute": attr_id,
                        "expected_order": [str(v) for v in expected_order],
                        "mean_utilities": {
                            str(k): round(float(v), 4) for k, v in mean_utils.items()
                        },
                        "violations": [
                            {
                                "lower": lo,
                                "higher": hi,
                                "lower_util": round(lu, 4),
                                "higher_util": round(hu, 4),
                            }
                            for lo, hi, lu, hu in violation_pairs
                        ],
                    },
                )
            )
        else:
            results.append(
                ValidationResult(
                    rule_name=f"level_monotonicity_{attr_id}",
                    passed=True,
                    severity="INFO",
                    message=(
                        f"Attribute '{attr_id}' level utilities follow expected monotonic order."
                    ),
                    details={
                        "attribute": attr_id,
                        "expected_order": [str(v) for v in expected_order],
                        "mean_utilities": {
                            str(k): round(float(v), 4) for k, v in mean_utils.items()
                        },
                    },
                )
            )

    return results


# ---------------------------------------------------------------------------
# 6.  Segment comparison sanity validator
# ---------------------------------------------------------------------------


def validate_segment_comparison(
    comparison_result: dict[str, Any],
) -> list[ValidationResult]:
    """Sanity checks for segment comparison API output.

    Args:
        comparison_result: Dict from compare_segments() or API response.

    Returns:
        List of ValidationResult.
    """
    results: list[ValidationResult] = []

    n_a = comparison_result.get("n_a", 0)
    n_b = comparison_result.get("n_b", 0)

    # Sample size check
    if n_a < 10 or n_b < 10:
        results.append(
            ValidationResult(
                rule_name="segment_comparison_sample_size",
                passed=False,
                severity="WARNING",
                message=(
                    f"Small sample sizes: n_a={n_a}, n_b={n_b}. "
                    f"Segment comparison may be unreliable."
                ),
                details={"n_a": n_a, "n_b": n_b},
            )
        )
    else:
        results.append(
            ValidationResult(
                rule_name="segment_comparison_sample_size",
                passed=True,
                severity="INFO",
                message=f"Sample sizes adequate: n_a={n_a}, n_b={n_b}.",
                details={"n_a": n_a, "n_b": n_b},
            )
        )

    # Overall test significance consistency
    overall = comparison_result.get("overall_test", {})
    p_value = overall.get("p_value", 1.0)
    significant = overall.get("significant", False)

    if p_value < 0.05 and not significant:
        results.append(
            ValidationResult(
                rule_name="segment_comparison_significance_consistency",
                passed=False,
                severity="HIGH",
                message=(
                    f"Inconsistent significance flag: p={p_value:.4f} < 0.05 but significant=False."
                ),
                details={"p_value": p_value, "significant": significant},
            )
        )
    elif p_value >= 0.05 and significant:
        results.append(
            ValidationResult(
                rule_name="segment_comparison_significance_consistency",
                passed=False,
                severity="HIGH",
                message=(
                    f"Inconsistent significance flag: p={p_value:.4f} >= 0.05 but significant=True."
                ),
                details={"p_value": p_value, "significant": significant},
            )
        )
    else:
        results.append(
            ValidationResult(
                rule_name="segment_comparison_significance_consistency",
                passed=True,
                severity="INFO",
                message=f"Significance flag consistent with p={p_value:.4f}.",
                details={"p_value": p_value, "significant": significant},
            )
        )

    return results


# ---------------------------------------------------------------------------
# 7.  Market simulation sanity validator
# ---------------------------------------------------------------------------


def validate_market_simulation(
    market_sim_response: dict[str, Any],
) -> list[ValidationResult]:
    """Sanity checks for market simulation API output.

    Args:
        market_sim_response: Dict from MarketSimResponse or simulate_share output.
            Expected keys: "scenarios" -> list of {"name", "predicted_share", ...}.

    Returns:
        List of ValidationResult.
    """
    results: list[ValidationResult] = []
    scenarios = market_sim_response.get("scenarios", [])

    if not scenarios:
        results.append(
            ValidationResult(
                rule_name="market_simulation_non_empty",
                passed=False,
                severity="CRITICAL",
                message="Market simulation returned no scenarios.",
            )
        )
        return results

    # Shares sum to ~1.0 (allow 1% tolerance for numerical error)
    total_share = sum(s.get("predicted_share", 0.0) for s in scenarios)
    if abs(total_share - 1.0) > 0.01:
        results.append(
            ValidationResult(
                rule_name="market_simulation_share_sum",
                passed=False,
                severity="HIGH",
                message=(f"Predicted shares sum to {total_share:.4f}, expected 1.0 (±0.01)."),
                details={
                    "total_share": round(total_share, 4),
                    "n_scenarios": len(scenarios),
                    "shares": [
                        {"name": s.get("name"), "share": s.get("predicted_share")}
                        for s in scenarios
                    ],
                },
            )
        )
    else:
        results.append(
            ValidationResult(
                rule_name="market_simulation_share_sum",
                passed=True,
                severity="INFO",
                message=f"Predicted shares sum to {total_share:.4f} (OK).",
                details={"total_share": round(total_share, 4)},
            )
        )

    # No negative shares
    negative_shares = [s for s in scenarios if s.get("predicted_share", 0.0) < 0]
    if negative_shares:
        results.append(
            ValidationResult(
                rule_name="market_simulation_no_negative",
                passed=False,
                severity="CRITICAL",
                message=(f"{len(negative_shares)} scenario(s) have negative predicted shares."),
                details={
                    "negative_scenarios": [
                        {"name": s.get("name"), "share": s.get("predicted_share")}
                        for s in negative_shares
                    ]
                },
            )
        )
    else:
        results.append(
            ValidationResult(
                rule_name="market_simulation_no_negative",
                passed=True,
                severity="INFO",
                message="All predicted shares are non-negative.",
            )
        )

    # Confidence interval sanity: lower < upper
    ci_issues = []
    for s in scenarios:
        lower = s.get("share_ci_95_lower", 0.0)
        upper = s.get("share_ci_95_upper", 0.0)
        if lower >= upper:
            ci_issues.append(
                {
                    "name": s.get("name"),
                    "lower": lower,
                    "upper": upper,
                }
            )

    if ci_issues:
        results.append(
            ValidationResult(
                rule_name="market_simulation_ci_order",
                passed=False,
                severity="HIGH",
                message=(f"{len(ci_issues)} scenario(s) have invalid CI (lower >= upper)."),
                details={"issues": ci_issues},
            )
        )
    else:
        results.append(
            ValidationResult(
                rule_name="market_simulation_ci_order",
                passed=True,
                severity="INFO",
                message="All confidence intervals are valid (lower < upper).",
            )
        )

    return results


# ---------------------------------------------------------------------------
# 8.  Orchestrator: run all validations
# ---------------------------------------------------------------------------


def run_all_validations(
    individual_utilities: pd.DataFrame,
    wtp_results: dict[str, dict],
    segment_comparison: dict[str, Any] | None,
    market_simulation: dict[str, Any] | None,
    attributes: list[dict[str, Any]],
    price_col: str = "price",
) -> dict[str, list[ValidationResult]]:
    """Run the complete business-rule validation suite.

    Returns:
        Dict mapping category -> list of ValidationResult.
    """
    all_results: dict[str, list[ValidationResult]] = {
        "price_coefficient": [],
        "wtp": [],
        "level_monotonicity": [],
        "segment_comparison": [],
        "market_simulation": [],
    }

    # 1. Price coefficient
    if price_col in individual_utilities.columns:
        all_results["price_coefficient"].append(
            validate_price_coefficient(individual_utilities[price_col])
        )

    # 2. WTP
    all_results["wtp"] = validate_wtp_plausibility(wtp_results)

    # 3. Level monotonicity
    all_results["level_monotonicity"] = validate_level_monotonicity(
        individual_utilities, attributes
    )

    # 4. Segment comparison
    if segment_comparison is not None:
        all_results["segment_comparison"] = validate_segment_comparison(segment_comparison)

    # 5. Market simulation
    if market_simulation is not None:
        all_results["market_simulation"] = validate_market_simulation(market_simulation)

    return all_results


def summarize_results(
    results: dict[str, list[ValidationResult]],
) -> dict[str, Any]:
    """Summarize validation results for reporting.

    Returns:
        Dict with overall pass/fail, counts by severity, and per-rule details.
    """
    flat = []
    for category, cat_results in results.items():
        for r in cat_results:
            flat.append((category, r))

    passed = not any(not r.passed and r.severity in ("CRITICAL", "HIGH") for _, r in flat)
    critical_failures = sum(1 for _, r in flat if not r.passed and r.severity == "CRITICAL")
    high_failures = sum(1 for _, r in flat if not r.passed and r.severity == "HIGH")
    warning_failures = sum(1 for _, r in flat if not r.passed and r.severity == "WARNING")

    return {
        "overall_passed": passed,
        "critical_failures": critical_failures,
        "high_failures": high_failures,
        "warning_failures": warning_failures,
        "total_checks": len(flat),
        "passed_checks": sum(1 for _, r in flat if r.passed),
        "details": [
            {
                "category": cat,
                **r.to_dict(),
            }
            for cat, r in flat
        ],
    }
