"""AI_CBC Prometheus metrics collection.

This module provides unified metrics collection for the AI_CBC platform,
including business metrics (persona generation, simulation), system metrics
(API requests, LLM calls), and security metrics (injection attempts).

All metrics follow the naming convention: aicbc_<domain>_<metric>_<unit>
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import lru_cache, wraps
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# Lazy Metrics Initialization
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_metrics() -> dict[str, Any]:
    """Lazily initialize and cache all Prometheus metrics.

    prometheus_client imports and metric object creation are deferred until
    the first metrics call, avoiding ~200-400ms startup cost and potential
    Windows process crashes triggered by prometheus_client's C extensions
    being imported at module load time.
    """
    from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest

    return {
        # Business Metrics
        "personas_generated_total": Counter(
            "aicbc_personas_generated_total",
            "Total number of personas generated",
            ["status", "model"],
        ),
        "simulation_duration_seconds": Histogram(
            "aicbc_simulation_duration_seconds",
            "Simulation execution time distribution",
            ["agent_type", "model"],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600],
        ),
        "authenticity_score_average": Gauge(
            "aicbc_authenticity_score_average",
            "Average authenticity score for the latest batch",
        ),
        "cost_per_persona_cny": Gauge(
            "aicbc_cost_per_persona_cny",
            "Average cost per persona in CNY",
            ["model"],
        ),
        "cost_per_study_cny": Gauge(
            "aicbc_cost_per_study_cny",
            "Total cost per study in CNY",
            ["study_id"],
        ),
        "persona_generation_duration_seconds": Histogram(
            "aicbc_persona_generation_duration_seconds",
            "Duration of a persona generation Celery task",
            ["study_id"],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800],
        ),
        "persona_generation_batch_size": Histogram(
            "aicbc_persona_generation_batch_size",
            "Number of personas requested per batch task",
            buckets=[1, 5, 10, 25, 50, 100],
        ),
        "cache_hit_ratio": Gauge(
            "aicbc_cache_hit_ratio",
            "Cache hit ratio for the active cache backend",
            ["cache_name"],
        ),
        "mongodb_query_duration_seconds": Histogram(
            "aicbc_mongodb_query_duration_seconds",
            "MongoDB query duration",
            ["collection", "operation"],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2, 5],
        ),
        # System Metrics
        "api_request_duration_seconds": Histogram(
            "aicbc_api_request_duration_seconds",
            "API request duration distribution",
            ["endpoint", "method", "status"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30],
        ),
        "api_requests_total": Counter(
            "aicbc_api_requests_total",
            "Total API requests",
            ["endpoint", "method", "status"],
        ),
        "llm_api_calls_total": Counter(
            "aicbc_llm_api_calls_total",
            "Total LLM API calls",
            ["model", "agent", "status"],
        ),
        "llm_tokens_total": Counter(
            "aicbc_llm_tokens_total",
            "Total LLM token usage",
            ["model", "type"],  # label kind: prompt | completion
        ),
        "llm_latency_seconds": Histogram(
            "aicbc_llm_latency_seconds",
            "LLM API call latency",
            ["model", "agent"],
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
        ),
        "queue_size": Gauge(
            "aicbc_queue_size",
            "Current task queue size",
            ["queue_name"],
        ),
        # Security Metrics
        "injection_attempts_total": Counter(
            "aicbc_injection_attempts_total",
            "Total injection attempts detected",
            ["type", "blocked"],
        ),
        "authentication_failures_total": Counter(
            "aicbc_authentication_failures_total",
            "Total authentication failures",
            ["reason"],
        ),
        "suspicious_requests_total": Counter(
            "aicbc_suspicious_requests_total",
            "Total suspicious requests",
            ["type"],
        ),
        # Application Info
        "app_info": Info("aicbc_app", "AI_CBC application information"),
        # Utility – exposed so get_metrics() can call generate_latest
        "generate_latest": generate_latest,
    }


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])


def timed(metric: Histogram, **labels: str) -> Callable[[F], F]:
    """Decorator to measure function execution time."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                metric.labels(**labels).observe(duration)

        return wrapper  # type: ignore[return-value]

    return decorator


def count_calls(metric: Counter, **labels: str) -> Callable[[F], F]:
    """Decorator to count function calls."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            metric.labels(**labels).inc()
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------


def set_app_info(version: str, environment: str) -> None:
    """Set application info metrics."""
    metrics = _get_metrics()
    metrics["app_info"].info({"version": version, "environment": environment})


def get_metrics() -> bytes:
    """Generate latest Prometheus metrics in text format."""
    metrics = _get_metrics()
    return metrics["generate_latest"]()


def record_llm_call(
    model: str,
    agent: str,
    status: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_seconds: float,
) -> None:
    """Record a single LLM API call with all related metrics."""
    metrics = _get_metrics()
    metrics["llm_api_calls_total"].labels(model=model, agent=agent, status=status).inc()
    metrics["llm_tokens_total"].labels(model=model, type="prompt").inc(prompt_tokens)
    metrics["llm_tokens_total"].labels(model=model, type="completion").inc(completion_tokens)
    metrics["llm_latency_seconds"].labels(model=model, agent=agent).observe(latency_seconds)


def record_persona_generation(
    status: str,
    model: str,
    cost_cny: float,
    authenticity_score: float | None = None,
) -> None:
    """Record persona generation metrics."""
    metrics = _get_metrics()
    metrics["personas_generated_total"].labels(status=status, model=model).inc()
    metrics["cost_per_persona_cny"].labels(model=model).set(cost_cny)
    if authenticity_score is not None:
        metrics["authenticity_score_average"].set(authenticity_score)


def record_api_request(
    endpoint: str,
    method: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record API request metrics."""
    status = str(status_code)
    metrics = _get_metrics()
    metrics["api_requests_total"].labels(endpoint=endpoint, method=method, status=status).inc()
    metrics["api_request_duration_seconds"].labels(
        endpoint=endpoint, method=method, status=status
    ).observe(duration_seconds)


def record_security_event(event_type: str, blocked: bool, detail: str = "") -> None:
    """Record security-related events."""
    blocked_str = "true" if blocked else "false"
    metrics = _get_metrics()
    if event_type == "injection":
        metrics["injection_attempts_total"].labels(type=detail, blocked=blocked_str).inc()
    elif event_type == "auth_failure":
        metrics["authentication_failures_total"].labels(reason=detail).inc()
    elif event_type == "suspicious":
        metrics["suspicious_requests_total"].labels(type=detail).inc()


def record_persona_generation_task(
    study_id: str,
    duration_seconds: float,
    batch_size: int,
) -> None:
    """Record persona generation Celery task metrics."""
    metrics = _get_metrics()
    metrics["persona_generation_duration_seconds"].labels(study_id=study_id).observe(
        duration_seconds
    )
    metrics["persona_generation_batch_size"].observe(batch_size)


def record_cache_hit_ratio(cache_name: str, hit_ratio: float) -> None:
    """Record cache hit ratio (0.0-1.0)."""
    metrics = _get_metrics()
    metrics["cache_hit_ratio"].labels(cache_name=cache_name).set(hit_ratio)


def record_mongodb_query_duration(
    collection: str,
    operation: str,
    duration_seconds: float,
) -> None:
    """Record MongoDB query duration."""
    metrics = _get_metrics()
    metrics["mongodb_query_duration_seconds"].labels(
        collection=collection, operation=operation
    ).observe(duration_seconds)
