"""Shutdown middleware: reject non-health/metrics traffic during graceful shutdown."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class ShutdownMiddleware(BaseHTTPMiddleware):
    """Return 503 when the application is shutting down."""

    async def dispatch(self, request: Request, call_next):
        shutting_down = getattr(request.app.state, "shutting_down", False)
        if shutting_down and request.url.path not in {"/health", "/metrics"}:
            return JSONResponse(
                status_code=503,
                content={"error": "Service is shutting down"},
            )
        return await call_next(request)
