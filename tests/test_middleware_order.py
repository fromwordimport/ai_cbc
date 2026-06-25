"""Tests for middleware ordering."""

from aicbc.main import app


def test_metrics_middleware_before_rate_limit() -> None:
    # FastAPI stacks middleware in reverse order of registration.
    # The last registered is the outermost. We verify MetricsMiddleware
    # was registered before RateLimitMiddleware so it wraps it.
    assert app.user_middleware is not None
    names = [m.cls.__name__ for m in app.user_middleware]
    metrics_idx = names.index("MetricsMiddleware")
    rate_limit_idx = names.index("RateLimitMiddleware")
    assert metrics_idx < rate_limit_idx
