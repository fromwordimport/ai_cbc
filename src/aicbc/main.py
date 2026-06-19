"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager

import jwt as pyjwt
import structlog
from beanie import init_beanie
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from jwt import PyJWTError
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.base import BaseHTTPMiddleware

from aicbc.analysis import routes as analysis_routes
from aicbc.api.middleware.audit_log import AuditLogMiddleware
from aicbc.api.middleware.rate_limit import RateLimitMiddleware
from aicbc.api.middleware.rbac import RBACMiddleware
from aicbc.api.routes import admin, auth, personas, questionnaires, responses, simulations
from aicbc.config.settings import get_settings
from aicbc.core.models.db_documents import ALL_DOCUMENT_MODELS
from aicbc.monitoring.health import router as health_router
from aicbc.monitoring.middleware import MetricsMiddleware, SecurityHeadersMiddleware

settings = get_settings()
logger = structlog.get_logger()

# MongoDB client lifecycle (None when running in memory-only mode)
_mongo_client: AsyncIOMotorClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize MongoDB/Beanie and clean up on shutdown."""
    logger.info("AI_CBC API starting up", environment=settings.environment)

    use_memory = os.environ.get("USE_MEMORY_STORE", "").lower() in ("1", "true", "yes")
    env = settings.environment.lower()
    is_dev_without_mongo = env in ("development", "dev", "testing", "test") and (
        not settings.database.mongodb_url
        or settings.database.mongodb_url == "mongodb://localhost:27017"
    )

    if not (use_memory or is_dev_without_mongo):
        global _mongo_client
        _mongo_client = AsyncIOMotorClient(
            settings.database.mongodb_url,
            maxPoolSize=settings.database.mongodb_max_connections,
        )
        await init_beanie(
            database=_mongo_client[settings.database.mongodb_database],
            document_models=ALL_DOCUMENT_MODELS,
        )
        logger.info("MongoDB/Beanie initialized")
    else:
        logger.info("Using in-memory stores; MongoDB initialization skipped")

    yield

    if _mongo_client is not None:
        _mongo_client.close()
    logger.info("AI_CBC API shutting down")


app = FastAPI(
    title="AI_CBC API",
    description="AI-powered Choice-Based Conjoint virtual consumer research platform",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)
app.state.debug = settings.debug

# CORS: allow frontend origin
cors_origins = ["https://aicbc.fromworldimport.com"]
if settings.debug:
    cors_origins.append("http://localhost:3000")


class AuthMiddleware(BaseHTTPMiddleware):
    """Unified authentication middleware: API key (service) or JWT (frontend).

    - Valid ``X-API-Key`` → service account; role from ``X-User-Role`` header.
    - Valid ``Authorization: Bearer <jwt>`` → frontend user; role from JWT claim.
    - In debug mode, auth is skipped to preserve local development ergonomics.
    """

    EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/ready", "/metrics"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Allow CORS preflight requests to pass through
        if request.method == "OPTIONS":
            return await call_next(request)

        if settings.debug:
            return await call_next(request)

        # 1. Service account via API key
        api_key = request.headers.get("X-API-Key")
        if api_key and api_key == settings.api_key:
            request.state.role = request.headers.get("X-User-Role", "viewer")
            return await call_next(request)

        # 2. Frontend user via JWT
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = pyjwt.decode(token, settings.secret_key, algorithms=["HS256"])
                request.state.role = payload.get("role", "viewer")
                return await call_next(request)
            except PyJWTError:
                pass

        return ORJSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Unauthorized"},
        )


# Add middleware (order matters: rate limit first, then metrics, then security headers, then auth, then RBAC, then audit)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(RBACMiddleware)
app.add_middleware(AuditLogMiddleware)

# Compress JSON responses above 1 KB. Placed before CORS so CORS remains outermost.
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

# CORS must be the outermost middleware so OPTIONS preflight responses are returned
# before any auth/RBAC checks can reject them without CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health_router, tags=["Health"])
app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/v1", tags=["Admin"])
app.include_router(personas.router, prefix="/api/v1", tags=["Personas"])
app.include_router(simulations.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(questionnaires.router, prefix="/api/v1", tags=["Questionnaires"])
app.include_router(responses.router, prefix="/api/v1", tags=["Responses"])
app.include_router(analysis_routes.router, prefix="/api/v1", tags=["Analysis"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
    """Handle unhandled exceptions.

    In production (debug=False) only a generic message is returned to avoid
    information leakage. Detailed errors are exposed only in debug mode.
    """
    logger.error("Unhandled exception", exc_info=exc, path=request.url.path)
    if settings.debug:
        return ORJSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )
    return ORJSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )
