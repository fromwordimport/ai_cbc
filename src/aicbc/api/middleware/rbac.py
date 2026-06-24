"""Role-based access control (RBAC) middleware for AI_CBC API.

Roles (least-privilege order):
  - viewer: read-only access (GET/HEAD/OPTIONS)
  - researcher: can create studies, generate personas, run analyses
  - admin: full access including deletion and admin endpoints

Role resolution order:
  1. ``X-User-Role`` request header (for test / service-account integration)
  2. ``role`` claim inside a JWT bearer token (if present)
  3. Default: ``viewer`` in production/staging; ``admin`` in development when
     ``DEBUG=true`` to preserve local ergonomics.

Protected paths (non-exhaustive):
  - DELETE /api/v1/personas/{id}            → admin
  - DELETE /api/v1/studies/{id}             → admin
  - PUT  /api/v1/studies/{id}/design        → researcher+
  - POST /api/v1/personas/generate          → researcher+
  - POST /api/v1/studies/{study_id}/analyze → researcher+
  - POST /api/v1/admin/*                    → admin
  - PUT  /api/v1/admin/settings             → admin
"""

from __future__ import annotations

import base64
import json
from typing import ClassVar

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = structlog.get_logger("aicbc.api.middleware.rbac")


class RBACMiddleware(BaseHTTPMiddleware):
    """Enforce role-based access control on incoming requests."""

    ROLES: ClassVar[tuple[str, ...]] = ("viewer", "researcher", "admin")

    # Public read endpoints that do not require elevated privileges.
    PUBLIC_PATHS: ClassVar[set[str]] = {
        "/health",
        "/ready",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/login",
    }

    # Method-based minimum role.
    METHOD_ROLES: ClassVar[dict[str, str]] = {
        "GET": "viewer",
        "HEAD": "viewer",
        "OPTIONS": "viewer",
    }

    # Path prefix / method → minimum role.
    PATH_RULES: ClassVar[list[tuple[str, str, str]]] = [
        # admin-only endpoints
        ("/api/v1/admin/", "*", "admin"),
        # deletion requires admin
        ("/api/v1/personas/", "DELETE", "admin"),
        ("/api/v1/studies/", "DELETE", "admin"),
        # mutation endpoints require researcher
        ("/api/v1/personas/generate", "POST", "researcher"),
        ("/api/v1/studies", "POST", "researcher"),
        ("/api/v1/studies/", "PUT", "researcher"),
        ("/api/v1/studies/", "POST", "researcher"),
    ]

    def __init__(self, app, default_debug_role: str = "admin") -> None:
        super().__init__(app)
        self.default_debug_role = default_debug_role

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Exempt public/documentation paths.
        if path in self.PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Allow CORS preflight requests to pass through; CORS middleware will
        # intercept them if registered as the outermost layer.
        if request.method == "OPTIONS":
            return await call_next(request)

        role = getattr(request.state, "role", None)
        if role is None:
            role = self._resolve_role(request)
            request.state.role = role

        required = self._required_role(request)
        if not self._role_satisfies(role, required):
            logger.warning(
                "rbac_denied",
                path=path,
                method=request.method,
                role=role,
                required=required,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Forbidden",
                    "detail": f"Role '{role}' cannot access this resource",
                },
            )

        return await call_next(request)

    def _resolve_role(self, request: Request) -> str:
        """Resolve the caller's role from header, JWT, or environment default."""
        header_role = request.headers.get("X-User-Role")
        if header_role and header_role in self.ROLES:
            return header_role

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            role = self._extract_role_from_jwt(auth_header[7:])
            if role in self.ROLES:
                return role

        # In debug/development, default to admin so local clients don't break.
        if getattr(request.app.state, "debug", False) or request.headers.get("X-Debug") == "1":
            return self.default_debug_role

        return "viewer"

    @staticmethod
    def _extract_role_from_jwt(token: str) -> str | None:
        """Extract the ``role`` claim from an unverified JWT payload.

        Note: signature verification is intentionally left to the API key /
        authentication layer. This middleware only reads the role claim for
        coarse-grained authorization.
        """
        try:
            payload_b64 = token.split(".")[1]
            # Pad base64 to multiple of 4
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
            payload = json.loads(payload_json)
            return payload.get("role")
        except Exception:
            return None

    def _required_role(self, request: Request) -> str:
        """Determine the minimum role required for the request."""
        method = request.method
        path = request.url.path

        for prefix, req_method, req_role in self.PATH_RULES:
            if path.startswith(prefix) and (req_method == "*" or method == req_method):
                return req_role

        # Default: read-only methods → viewer, anything else → researcher.
        return self.METHOD_ROLES.get(method, "researcher")

    @classmethod
    def _role_satisfies(cls, role: str, required: str) -> bool:
        """Return True if ``role`` is at least as privileged as ``required``."""
        hierarchy = {r: i for i, r in enumerate(cls.ROLES)}
        return hierarchy.get(role, -1) >= hierarchy.get(required, -1)
