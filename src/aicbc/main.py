"""FastAPI application entry point."""

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from aicbc.api.routes import health, personas, simulations
from aicbc.config.settings import get_settings

settings = get_settings()
logger = structlog.get_logger()

app = FastAPI(
    title="AI_CBC API",
    description="AI-powered Choice-Based Conjoint virtual consumer research platform",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Register routes
app.include_router(health.router, tags=["Health"])
app.include_router(personas.router, prefix="/api/v1", tags=["Personas"])
app.include_router(simulations.router, prefix="/api/v1", tags=["Simulations"])


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
