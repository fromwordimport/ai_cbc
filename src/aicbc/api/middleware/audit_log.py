"""Audit log middleware for AI_CBC API.

Records all mutating requests (POST/PUT/PATCH/DELETE) and security-relevant
responses (401/403/429) to the audit log store.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from aicbc.core.audit import get_audit_logger


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Middleware that writes audit entries for write operations and failures."""

    AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        response = await call_next(request)

        # Only audit mutating requests and security-relevant responses.
        if method in self.AUDIT_METHODS or response.status_code in (401, 403, 429):
            logger = get_audit_logger()

            result = "success" if response.status_code < 400 else "error"
            if response.status_code == 401:
                result = "auth_failure"
            elif response.status_code == 403:
                result = "denied"
            elif response.status_code == 429:
                result = "rate_limited"

            # Derive resource/resource_id from the path.
            parts = [p for p in path.split("/") if p]
            resource = parts[2] if len(parts) >= 3 and parts[0] == "api" else "api"
            resource_id = parts[3] if len(parts) >= 4 else ""

            await logger.log_event(
                action=method if method in self.AUDIT_METHODS else f"{result}",
                resource=resource,
                resource_id=resource_id,
                result=result,
                request=request,
                data={
                    "status_code": response.status_code,
                    "path": path,
                },
            )

        return response
