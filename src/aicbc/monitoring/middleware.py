"""FastAPI middleware for metrics collection and request tracking."""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from aicbc.monitoring.metrics import record_api_request, record_security_event


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect API metrics for every request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and record metrics."""
        start_time = time.perf_counter()

        # Extract endpoint pattern for metrics
        endpoint = request.url.path
        method = request.method

        try:
            response = await call_next(request)
            status_code = response.status_code

            # Record security events
            if status_code == 429:
                record_security_event(
                    event_type="suspicious",
                    blocked=True,
                    detail="rate_limited",
                )

            return response

        except Exception as exc:
            status_code = 500
            raise exc

        finally:
            duration = time.perf_counter() - start_time
            record_api_request(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                duration_seconds=duration,
            )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers."""
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response
