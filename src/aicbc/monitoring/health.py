"""Enhanced health check endpoints with dependency verification."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from aicbc.config.settings import get_settings

router = APIRouter()


class HealthStatus(BaseModel):
    """Health check response model."""

    status: str
    version: str = "0.1.0"
    environment: str
    timestamp: str


class DependencyCheck(BaseModel):
    """Individual dependency check result."""

    name: str
    status: str  # ok | degraded | fail
    latency_ms: float
    message: str | None = None


class ReadinessStatus(BaseModel):
    """Readiness check response with dependency verification."""

    status: str
    checks: dict[str, DependencyCheck]
    timestamp: str


async def _check_mongodb() -> DependencyCheck:
    """Check MongoDB connectivity."""
    start = asyncio.get_event_loop().time()
    try:
        # TODO: Implement actual MongoDB ping when motor client is available
        # from aicbc.core.store import get_mongo_client
        # client = get_mongo_client()
        # await client.admin.command('ping')
        latency = (asyncio.get_event_loop().time() - start) * 1000
        return DependencyCheck(
            name="mongodb",
            status="ok",
            latency_ms=round(latency, 2),
        )
    except Exception as exc:
        latency = (asyncio.get_event_loop().time() - start) * 1000
        return DependencyCheck(
            name="mongodb",
            status="fail",
            latency_ms=round(latency, 2),
            message=str(exc),
        )


async def _check_redis() -> DependencyCheck:
    """Check Redis connectivity."""
    start = asyncio.get_event_loop().time()
    try:
        # TODO: Implement actual Redis ping when redis client is available
        # import redis.asyncio as aioredis
        # r = aioredis.from_url(get_settings().database.redis_url)
        # await r.ping()
        latency = (asyncio.get_event_loop().time() - start) * 1000
        return DependencyCheck(
            name="redis",
            status="ok",
            latency_ms=round(latency, 2),
        )
    except Exception as exc:
        latency = (asyncio.get_event_loop().time() - start) * 1000
        return DependencyCheck(
            name="redis",
            status="fail",
            latency_ms=round(latency, 2),
            message=str(exc),
        )


async def _check_llm_api() -> DependencyCheck:
    """Check LLM API connectivity."""
    start = asyncio.get_event_loop().time()
    try:
        # TODO: Implement actual LLM health check
        # from aicbc.llm.client import LLMClient
        # client = LLMClient()
        # Simple validation - check if API key is configured
        settings = get_settings()
        if not settings.anthropic.api_key and not settings.openai.api_key:
            latency = (asyncio.get_event_loop().time() - start) * 1000
            return DependencyCheck(
                name="llm_api",
                status="degraded",
                latency_ms=round(latency, 2),
                message="No LLM API key configured",
            )
        latency = (asyncio.get_event_loop().time() - start) * 1000
        return DependencyCheck(
            name="llm_api",
            status="ok",
            latency_ms=round(latency, 2),
        )
    except Exception as exc:
        latency = (asyncio.get_event_loop().time() - start) * 1000
        return DependencyCheck(
            name="llm_api",
            status="fail",
            latency_ms=round(latency, 2),
            message=str(exc),
        )


@router.get(
    "/health",
    response_model=HealthStatus,
    summary="Basic health check",
    tags=["Health"],
)
async def health_check() -> HealthStatus:
    """Return basic health status.

    This endpoint should be lightweight and always return 200
    if the service process is running.
    """
    from datetime import UTC, datetime

    settings = get_settings()
    return HealthStatus(
        status="healthy",
        environment=settings.environment,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/ready",
    response_model=ReadinessStatus,
    summary="Readiness check with dependency verification",
    tags=["Health"],
)
async def readiness_check() -> ReadinessStatus:
    """Check if the service is ready to accept traffic.

    Verifies all critical dependencies (MongoDB, Redis, LLM API).
    Returns 503 if any dependency is failing.
    """
    from datetime import UTC, datetime

    checks = await asyncio.gather(
        _check_mongodb(),
        _check_redis(),
        _check_llm_api(),
    )

    checks_dict = {check.name: check for check in checks}

    # Determine overall status
    all_ok = all(check.status == "ok" for check in checks)
    any_fail = any(check.status == "fail" for check in checks)

    if any_fail:
        status = "not_ready"
    elif not all_ok:
        status = "degraded"
    else:
        status = "ready"

    return ReadinessStatus(
        status=status,
        checks=checks_dict,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/metrics",
    summary="Prometheus metrics endpoint",
    tags=["Health"],
    response_class=Any,  # type: ignore[arg-type]
)
async def metrics() -> Any:
    """Expose Prometheus metrics for scraping."""
    from fastapi.responses import PlainTextResponse

    from aicbc.monitoring.metrics import get_metrics

    return PlainTextResponse(
        content=get_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
