"""Segment comparison statistical tests.

Implements Hotelling's T², Welch's t-test, and permutation test
for comparing preference differences between consumer segments.
"""

from __future__ import annotations

from scipy import stats


def hotellings_t2(
    group_a: pd.DataFrame,
    group_b: pd.DataFrame,
) -> dict[str, object]:
    """Hotelling's T² test for multivariate mean difference.

    Args:
        group_a: Utility matrix for segment A (n_a x n_features).
        group_b: Utility matrix for segment B (n_b x n_features).

    Returns:
        Dict with statistic, p_value, significant flag.
    """
    import numpy as np

    n_a, p = group_a.shape
    n_b, _ = group_b.shape

    # Sample-size pre-check: covariance matrix singular when n < p
    if n_a < p or n_b < p:
        return {
            "method": "Hotelling's T²",
            "statistic": float('nan'),
            "p_value": float('nan'),
            "significant": False,
            "error": (
                f"Insufficient samples: n_a={n_a}, n_b={n_b}, "
                f"need at least p={p} per group"
            ),
        }

    mean_a = group_a.mean(axis=0).values
    mean_b = group_b.mean(axis=0).values

    # Pooled covariance
    cov_a = np.cov(group_a.T, ddof=1)
    cov_b = np.cov(group_b.T, ddof=1)
    pooled_cov = ((n_a - 1) * cov_a + (n_b - 1) * cov_b) / (n_a + n_b - 2)

    # T² statistic
    diff = mean_a - mean_b
    try:
        inv_cov = np.linalg.inv(pooled_cov)
        t2 = (n_a * n_b / (n_a + n_b)) * diff.T @ inv_cov @ diff

        # Convert to F statistic
        f_stat = (n_a + n_b - p - 1) / ((n_a + n_b - 2) * p) * t2
        df1 = p
        df2 = n_a + n_b - p - 1
        p_value = 1 - stats.f.cdf(f_stat, df1, df2)

        return {
            "method": "Hotelling's T²",
            "statistic": float(t2),
            "f_statistic": float(f_stat),
            "p_value": float(p_value),
            "significant": p_value < 0.05,
            "df1": int(df1),
            "df2": int(df2),
        }
    except np.linalg.LinAlgError:
        # Singular covariance matrix
        return {
            "method": "Hotelling's T²",
            "statistic": float('nan'),
            "p_value": float('nan'),
            "significant": False,
            "error": "Singular covariance matrix",
        }


def welch_ttest(
    group_a: pd.Series,
    group_b: pd.Series,
) -> dict[str, object]:
    """Welch's t-test (does not assume equal variances).

    Args:
        group_a: Single feature values for segment A.
        group_b: Single feature values for segment B.

    Returns:
        Dict with t_statistic, p_value, cohens_d, etc.
    """
    mean_a = float(group_a.mean())
    mean_b = float(group_b.mean())
    std_a = float(group_a.std(ddof=1))
    std_b = float(group_b.std(ddof=1))
    n_a = len(group_a)
    n_b = len(group_b)

    # Welch's t-test
    t_stat, p_value = stats.ttest_ind(group_a, group_b, equal_var=False)

    import numpy as np

    # Cohen's d (pooled std)
    pooled_std = np.sqrt(((n_a - 1) * std_a**2 + (n_b - 1) * std_b**2) / (n_a + n_b - 2))
    cohens_d = (mean_a - mean_b) / pooled_std if pooled_std > 0 else 0.0

    # Effect size interpretation
    abs_d = abs(cohens_d)
    if abs_d < 0.2:
        effect_size = "negligible"
    elif abs_d < 0.5:
        effect_size = "small"
    elif abs_d < 0.8:
        effect_size = "medium"
    else:
        effect_size = "large"

    return {
        "method": "Welch's t-test",
        "t_statistic": float(t_stat),
        "p_value": float(p_value),
        "significant": p_value < 0.05,
        "cohens_d": float(cohens_d),
        "effect_size": effect_size,
        "mean_a": mean_a,
        "mean_b": mean_b,
    }


def permutation_test(
    group_a: pd.DataFrame,
    group_b: pd.DataFrame,
    n_permutations: int = 1000,
) -> dict[str, object]:
    """Permutation test for multivariate difference (non-parametric).

    Args:
        group_a: Utility matrix for segment A.
        group_b: Utility matrix for segment B.
        n_permutations: Number of permutations.

    Returns:
        Dict with p_value and significant flag.
    """
    import numpy as np

    n_a = len(group_a)
    combined = np.vstack([group_a.values, group_b.values])

    # Observed statistic: Euclidean distance between means
    obs_mean_a = group_a.mean(axis=0).values
    obs_mean_b = group_b.mean(axis=0).values
    obs_stat = np.linalg.norm(obs_mean_a - obs_mean_b)

    # Permutation
    rng = np.random.default_rng(42)
    perm_stats = []
    for _ in range(n_permutations):
        perm = rng.permutation(len(combined))
        perm_a = combined[perm[:n_a]]
        perm_b = combined[perm[n_a:]]
        perm_stat = np.linalg.norm(perm_a.mean(axis=0) - perm_b.mean(axis=0))
        perm_stats.append(perm_stat)

    perm_stats = np.array(perm_stats)
    # +1 smoothing: avoids p=0, ensures valid under H0
    count_extreme = np.sum(perm_stats >= obs_stat)
    p_value = (count_extreme + 1) / (n_permutations + 1)

    return {
        "method": "Permutation test",
        "statistic": float(obs_stat),
        "p_value": float(p_value),
        "significant": p_value < 0.05,
        "n_permutations": n_permutations,
    }


def compare_segments(
    utilities: pd.DataFrame,
    segment_labels: pd.Series,
    segment_a: str,
    segment_b: str,
    test_type: str = "welch",
) -> dict[str, object]:
    """Compare two segments statistically.

    Args:
        utilities: Individual utility matrix (n_resp x n_features).
        segment_labels: Series mapping respondent_id -> segment name.
        segment_a: Name of first segment.
        segment_b: Name of second segment.
        test_type: "hotelling", "welch", or "permutation".

    Returns:
        Complete comparison result dict.
    """
    # Filter utilities by segment
    mask_a = segment_labels == segment_a
    mask_b = segment_labels == segment_b

    group_a = utilities[mask_a]
    group_b = utilities[mask_b]

    n_a = len(group_a)
    n_b = len(group_b)

    # Overall test
    if test_type == "hotelling":
        overall = hotellings_t2(group_a, group_b)
    elif test_type == "permutation":
        overall = permutation_test(group_a, group_b)
    else:
        # Default: use Hotelling for overall with Welch for per-attribute
        overall = hotellings_t2(group_a, group_b)

    # Per-attribute tests (always Welch)
    per_attribute = []
    for col in utilities.columns:
        result = welch_ttest(group_a[col], group_b[col])
        result["attribute"] = col
        per_attribute.append(result)

    # ── Multiple comparison correction (Bonferroni-Holm) ──────────────
    from statsmodels.stats.multitest import multipletests
    raw_pvalues = [r["p_value"] for r in per_attribute]
    _reject, corrected_p, _alpha_sidak, _alpha_bonf = multipletests(
        raw_pvalues, alpha=0.05, method="holm",
    )
    for i, result in enumerate(per_attribute):
        result["corrected_p_value"] = float(corrected_p[i])
        result["corrected_significant"] = bool(corrected_p[i] < 0.05)

    # Generate interpretation (uses corrected significance)
    sig_attrs = [
        r for r in per_attribute
        if r.get("corrected_significant", r["significant"])
        and r["effect_size"] in ("medium", "large")
    ]
    if sig_attrs:
        attr_names = ", ".join([r["attribute"] for r in sig_attrs[:3]])
        interpretation = (
            f"两群体在{attr_names}等属性上存在显著差异"
            f"（p<0.05, 效应量≥中等），建议差异化策略。"
        )
    else:
        interpretation = "两群体偏好无显著差异，可考虑统一策略。"

    return {
        "segment_a": segment_a,
        "segment_b": segment_b,
        "n_a": n_a,
        "n_b": n_b,
        "overall_test": overall,
        "per_attribute": per_attribute,
        "interpretation": interpretation,
    }
