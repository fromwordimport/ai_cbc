"""Data preprocessing: CBCRawDataset → analysis-ready long format."""

from __future__ import annotations

import pandas as pd

from aicbc.questionnaire.design.effects_coding import encode_profile
from aicbc.questionnaire.models import Attribute, AttributeType
from aicbc.questionnaire.response_models import CBCRawDataset


def to_long_format(
    dataset: CBCRawDataset,
    attributes: list[Attribute],
) -> pd.DataFrame:
    """Convert CBCRawDataset to long-format DataFrame for analysis.

    Each row represents one alternative in one choice set for one respondent.
    The ``chosen`` column is 1 if the alternative was selected, 0 otherwise.

    Args:
        dataset: Standard exchange dataset from questionnaire system.
        attributes: Ordered list of attribute definitions.

    Returns:
        DataFrame with columns:
        - resp_id, resp_index, task_id, task_index, alt_id
        - chosen (0/1)
        - {attribute_id}_{level_index} for each categorical attribute
        - {attribute_id} for each continuous/price attribute
    """
    rows: list[dict] = []

    import pandas as pd

    for record in dataset.choice_records:
        for alt in record.alternatives:
            row: dict = {
                "resp_id": record.respondent_id,
                "resp_index": record.respondent_index,
                "task_id": record.choice_set_id,
                "task_index": record.choice_set_index,
                "alt_id": alt.alt_index,
                "chosen": 1 if alt.chosen else 0,
            }

            # Encode attributes using effects coding
            encoded = encode_profile(alt.attributes, attributes)
            param_idx = 0
            for attr in attributes:
                if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
                    n_levels = len(attr.levels)
                    for i in range(n_levels - 1):
                        col_name = f"{attr.id}_{i}"
                        row[col_name] = encoded[param_idx]
                        param_idx += 1
                else:
                    row[attr.id] = encoded[param_idx]
                    param_idx += 1

            rows.append(row)

    return pd.DataFrame(rows)


def get_feature_columns(
    attributes: list[Attribute],
) -> list[str]:
    """Return the list of feature column names for the given attributes.

    These columns can be used directly as the design matrix X for
    conditional logit / hierarchical Bayes models.
    """
    cols: list[str] = []
    for attr in attributes:
        if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
            for i in range(len(attr.levels) - 1):
                cols.append(f"{attr.id}_{i}")
        else:
            cols.append(attr.id)
    return cols


def validate_dataset(
    dataset: CBCRawDataset,
    attributes: list[Attribute],
) -> dict:
    """Validate dataset quality and return diagnostic report.

    Checks (per design spec):
    - attributes_complete (ERROR): every alternative has values for all attributes
    - one_choice_per_task (ERROR): exactly one chosen alternative per task
    - sample size adequacy (WARNING): n_resp * n_tasks >= n_params * 5
    - none_option_rate (WARNING): none-option choice rate within expected bounds
    - level coverage (WARNING): each level appears in >= 10% of alternatives
    """
    df = to_long_format(dataset, attributes)
    n_params = len(get_feature_columns(attributes))
    attr_ids = {attr.id for attr in attributes}

    report: dict = {
        "valid": True,
        "warnings": [],
        "errors": [],
    }

    # ── Rule 1: attributes_complete (ERROR) ──────────────────────────────
    missing_attr_count = 0
    for record in dataset.choice_records:
        for alt in record.alternatives:
            alt_attr_ids = set(alt.attributes.keys())
            missing = attr_ids - alt_attr_ids
            if missing:
                missing_attr_count += 1
    if missing_attr_count > 0:
        report["errors"].append(
            f"{missing_attr_count} alternatives are missing required "
            f"attributes (expected: {sorted(attr_ids)})"
        )
        report["valid"] = False

    # ── Rule 2: one_choice_per_task (ERROR) ──────────────────────────────
    if df.empty:
        report["errors"].append("Dataset is empty (no alternatives found)")
        report["valid"] = False
    else:
        choice_counts = df.groupby(["resp_id", "task_id"])["chosen"].sum()
        bad_tasks = choice_counts[choice_counts != 1]
        if len(bad_tasks) > 0:
            report["errors"].append(f"{len(bad_tasks)} tasks do not have exactly one choice")
            report["valid"] = False

    # ── Rule 3: sample size (WARNING) ────────────────────────────────────
    n_resp = dataset.metadata.n_respondents
    n_tasks = dataset.metadata.n_choice_sets
    min_required = n_params * 5
    actual = n_resp * n_tasks
    if actual < min_required:
        report["warnings"].append(
            f"Sample size may be insufficient: {actual} < {min_required} "
            f"(need n_params * 5, n_params={n_params})"
        )

    # ── Rule 4: none_option_rate (WARNING) ───────────────────────────────
    # The "none" alternative (if present) is identified by having all-zero
    # effects-coded values or being explicitly tagged.
    if df.shape[0] > 0:
        n_none_tasks = 0
        for (_, _), group in df.groupby(["resp_id", "task_id"]):
            # A "none" choice: alternative has all-zero feature values
            feature_cols = get_feature_columns(attributes)
            for _, row in group.iterrows():
                if row["chosen"] == 1:
                    all_zero = all(abs(float(row.get(col, 0.0))) < 1e-9 for col in feature_cols)
                    if all_zero:
                        n_none_tasks += 1
                    break
        none_rate = n_none_tasks / max(df["resp_id"].nunique(), 1)
        if none_rate > 0.5:
            report["warnings"].append(
                f"None-option choice rate is {none_rate:.1%} (>50%). "
                f"Product attributes may have low relevance to respondents."
            )
        elif none_rate == 0 and getattr(dataset.metadata, "include_none", False):
            report["warnings"].append(
                "None-option was included in design but zero respondents chose it. "
                "This may indicate demand effects or insufficient price range."
            )

    # ── Rule 5: level coverage (WARNING) ──────────────────────────────────
    for attr in attributes:
        if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
            level_counts: dict[str, int] = {}
            for record in dataset.choice_records:
                for alt in record.alternatives:
                    val = str(alt.attributes.get(attr.id, ""))
                    level_counts[val] = level_counts.get(val, 0) + 1

            total_alts = len(df)
            if total_alts > 0:
                for level in attr.levels:
                    count = level_counts.get(str(level.value), 0)
                    if count / total_alts < 0.1:
                        report["warnings"].append(
                            f"Level '{level.value}' of '{attr.id}' appears in "
                            f"{count / total_alts:.1%} of alternatives (< 10%)"
                        )

    return report
