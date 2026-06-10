"""FastAPI application entry point."""

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from aicbc.analysis import routes as analysis_routes
from aicbc.api.routes import personas, questionnaires, responses, simulations
from aicbc.config.settings import get_settings
from aicbc.monitoring.health import router as health_router
from aicbc.monitoring.middleware import MetricsMiddleware, SecurityHeadersMiddleware

settings = get_settings()
logger = structlog.get_logger()

app = FastAPI(
    title="AI_CBC API",
    description="AI-powered Choice-Based Conjoint virtual consumer research platform",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Add middleware
app.add_middleware(MetricsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Register routes
app.include_router(health_router, tags=["Health"])
app.include_router(personas.router, prefix="/api/v1", tags=["Personas"])
app.include_router(simulations.router, prefix="/api/v1", tags=["Simulations"])
app.include_router(questionnaires.router, prefix="/api/v1", tags=["Questionnaires"])
app.include_router(responses.router, prefix="/api/v1", tags=["Responses"])
app.include_router(analysis_routes.router, prefix="/api/v1", tags=["Analysis"])


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions."""
    logger.error("Unhandled exception", exc_info=exc, path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


@app.on_event("startup")
async def startup_event() -> None:
    """Application startup handler."""
    logger.info("AI_CBC API starting up", environment=settings.environment)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown handler."""
    logger.info("AI_CBC API shutting down")
