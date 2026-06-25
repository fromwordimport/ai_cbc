"""Tests for monitoring metrics."""

from aicbc.monitoring.metrics import (
    record_cache_hit_ratio,
    record_mongodb_query_duration,
    record_persona_generation_task,
)


def test_record_persona_generation_task() -> None:
    record_persona_generation_task("study-1", 12.5, 10)


def test_record_cache_hit_ratio() -> None:
    record_cache_hit_ratio("dashboard", 0.85)


def test_record_mongodb_query_duration() -> None:
    record_mongodb_query_duration("personas", "find", 0.025)
