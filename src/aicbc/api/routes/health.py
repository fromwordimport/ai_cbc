"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    """Readiness check for orchestrators."""
    return {"status": "ready"}


@router.get("/metrics")
async def metrics() -> dict[str, str]:
    """Prometheus metrics placeholder."""
    return {"status": "metrics_endpoint"}
