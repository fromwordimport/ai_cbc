"""AI_CBC Prometheus metrics collection.

This module provides unified metrics collection for the AI_CBC platform,
including business metrics (persona generation, simulation), system metrics
(API requests, LLM calls), and security metrics (injection attempts).

All metrics follow the naming convention: aicbc_<domain>_<metric>_<unit>
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest

# ---------------------------------------------------------------------------
# Business Metrics
# ---------------------------------------------------------------------------

PERSONAS_GENERATED_TOTAL = Counter(
    "aicbc_personas_generated_total",
    "Total number of personas generated",
    ["status", "model"],
)

SIMULATION_DURATION_SECONDS = Histogram(
    "aicbc_simulation_duration_seconds",
    "Simulation execution time distribution",
    ["agent_type", "model"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

AUTHENTICITY_SCORE_AVERAGE = Gauge(
    "aicbc_authenticity_score_average",
    "Average authenticity score for the latest batch",
)

COST_PER_PERSONA_CNY = Gauge(
    "aicbc_cost_per_persona_cny",
    "Average cost per persona in CNY",
    ["model"],
)

COST_PER_STUDY_CNY = Gauge(
    "aicbc_cost_per_study_cny",
    "Total cost per study in CNY",
    ["study_id"],
)

# ---------------------------------------------------------------------------
# System Metrics
# ---------------------------------------------------------------------------

API_REQUEST_DURATION_SECONDS = Histogram(
    "aicbc_api_request_duration_seconds",
    "API request duration distribution",
    ["endpoint", "method", "status"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30],
)

API_REQUESTS_TOTAL = Counter(
    "aicbc_api_requests_total",
    "Total API requests",
    ["endpoint", "method", "status"],
)

LLM_API_CALLS_TOTAL = Counter(
    "aicbc_llm_api_calls_total",
    "Total LLM API calls",
    ["model", "agent", "status"],
)

LLM_TOKENS_TOTAL = Counter(
    "aicbc_llm_tokens_total",
    "Total LLM token usage",
    ["model", "type"],  # type: prompt | completion
)

LLM_LATENCY_SECONDS = Histogram(
    "aicbc_llm_latency_seconds",
    "LLM API call latency",
    ["model", "agent"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
)

QUEUE_SIZE = Gauge(
    "aicbc_queue_size",
    "Current task queue size",
    ["queue_name"],
)

# ---------------------------------------------------------------------------
# Security Metrics
# ---------------------------------------------------------------------------

INJECTION_ATTEMPTS_TOTAL = Counter(
    "aicbc_injection_attempts_total",
    "Total injection attempts detected",
    ["type", "blocked"],
)

AUTHENTICATION_FAILURES_TOTAL = Counter(
    "aicbc_authentication_failures_total",
    "Total authentication failures",
    ["reason"],
)

SUSPICIOUS_REQUESTS_TOTAL = Counter(
    "aicbc_suspicious_requests_total",
    "Total suspicious requests",
    ["type"],
)

# ---------------------------------------------------------------------------
# Application Info
# ---------------------------------------------------------------------------

APP_INFO = Info("aicbc_app", "AI_CBC application information")

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
    APP_INFO.info({"version": version, "environment": environment})


def get_metrics() -> bytes:
    """Generate latest Prometheus metrics in text format."""
    return generate_latest()


def record_llm_call(
    model: str,
    agent: str,
    status: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_seconds: float,
) -> None:
    """Record a single LLM API call with all related metrics."""
    LLM_API_CALLS_TOTAL.labels(model=model, agent=agent, status=status).inc()
    LLM_TOKENS_TOTAL.labels(model=model, type="prompt").inc(prompt_tokens)
    LLM_TOKENS_TOTAL.labels(model=model, type="completion").inc(completion_tokens)
    LLM_LATENCY_SECONDS.labels(model=model, agent=agent).observe(latency_seconds)


def record_persona_generation(
    status: str,
    model: str,
    cost_cny: float,
    authenticity_score: float | None = None,
) -> None:
    """Record persona generation metrics."""
    PERSONAS_GENERATED_TOTAL.labels(status=status, model=model).inc()
    COST_PER_PERSONA_CNY.labels(model=model).set(cost_cny)
    if authenticity_score is not None:
        AUTHENTICITY_SCORE_AVERAGE.set(authenticity_score)


def record_api_request(
    endpoint: str,
    method: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record API request metrics."""
    status = str(status_code)
    API_REQUESTS_TOTAL.labels(endpoint=endpoint, method=method, status=status).inc()
    API_REQUEST_DURATION_SECONDS.labels(
        endpoint=endpoint, method=method, status=status
    ).observe(duration_seconds)


def record_security_event(event_type: str, blocked: bool, detail: str = "") -> None:
    """Record security-related events."""
    blocked_str = "true" if blocked else "false"
    if event_type == "injection":
        INJECTION_ATTEMPTS_TOTAL.labels(type=detail, blocked=blocked_str).inc()
    elif event_type == "auth_failure":
        AUTHENTICATION_FAILURES_TOTAL.labels(reason=detail).inc()
    elif event_type == "suspicious":
        SUSPICIOUS_REQUESTS_TOTAL.labels(type=detail).inc()
