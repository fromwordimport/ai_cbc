"""Tests for monitoring metrics."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from aicbc.monitoring.metrics import (
    record_cache_hit_ratio,
    record_mongodb_query_duration,
    record_persona_generation_task,
)


def _find_metric_sample(metric_name: str, labels: dict[str, str]) -> float | None:
    """Find a metric sample in the global registry by sample name and labels."""
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == metric_name and sample.labels == labels:
                return sample.value
    return None


def _metric_name_exists(metric_name: str) -> bool:
    """Check if a metric name exists in the registry."""
    return metric_name in REGISTRY._names_to_collectors


@pytest.mark.unit
def test_record_persona_generation_task() -> None:
    result = record_persona_generation_task("study-1", 12.5, 10)
    assert result is None

    # Verify the metric was registered
    assert _metric_name_exists("aicbc_persona_generation_duration_seconds")
    assert _metric_name_exists("aicbc_persona_generation_batch_size")

    # Verify the duration histogram was updated (12.5 falls into the 30.0 bucket)
    duration_value = _find_metric_sample(
        "aicbc_persona_generation_duration_seconds_bucket",
        {"study_id": "study-1", "le": "30.0"},
    )
    assert duration_value is not None
    assert duration_value >= 1.0

    # Verify the batch size histogram was updated (10 falls into the 10.0 bucket)
    batch_value = _find_metric_sample(
        "aicbc_persona_generation_batch_size_bucket",
        {"le": "10.0"},
    )
    assert batch_value is not None
    assert batch_value >= 1.0


@pytest.mark.unit
def test_record_cache_hit_ratio() -> None:
    result = record_cache_hit_ratio("dashboard", 0.85)
    assert result is None

    # Verify the gauge was updated
    gauge_value = _find_metric_sample(
        "aicbc_cache_hit_ratio",
        {"cache_name": "dashboard"},
    )
    assert gauge_value is not None
    assert gauge_value == 0.85


@pytest.mark.unit
def test_record_cache_hit_ratio_boundary_zero() -> None:
    result = record_cache_hit_ratio("edge_zero", 0.0)
    assert result is None

    gauge_value = _find_metric_sample(
        "aicbc_cache_hit_ratio",
        {"cache_name": "edge_zero"},
    )
    assert gauge_value is not None
    assert gauge_value == 0.0


@pytest.mark.unit
def test_record_cache_hit_ratio_boundary_one() -> None:
    result = record_cache_hit_ratio("edge_one", 1.0)
    assert result is None

    gauge_value = _find_metric_sample(
        "aicbc_cache_hit_ratio",
        {"cache_name": "edge_one"},
    )
    assert gauge_value is not None
    assert gauge_value == 1.0


@pytest.mark.unit
def test_record_mongodb_query_duration() -> None:
    result = record_mongodb_query_duration("personas", "find", 0.025)
    assert result is None

    # Verify the metric was registered
    assert _metric_name_exists("aicbc_mongodb_query_duration_seconds")

    # Verify the histogram was updated (0.025 falls into the 0.05 bucket)
    duration_value = _find_metric_sample(
        "aicbc_mongodb_query_duration_seconds_bucket",
        {"collection": "personas", "operation": "find", "le": "0.05"},
    )
    assert duration_value is not None
    assert duration_value >= 1.0
