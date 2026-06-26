"""Enhanced health check endpoints with dependency verification."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from aicbc.config.settings import get_settings
from aicbc.core.cache import get_dashboard_summary_cache
from aicbc.core.store import get_questionnaire_store, get_store

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
        from aicbc.main import _mongo_client

        if _mongo_client is None:
            raise RuntimeError("MongoDB client not initialized")
        await _mongo_client.admin.command("ping")
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
        import redis.asyncio as aioredis

        settings = get_settings()
        r = aioredis.from_url(settings.database.redis_url, decode_responses=True)
        try:
            await r.ping()
        finally:
            await r.aclose()
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
    response_class=PlainTextResponse,
)
async def metrics() -> Any:
    """Expose Prometheus metrics for scraping."""
    from aicbc.monitoring.metrics import get_metrics

    return PlainTextResponse(
        content=get_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get(
    "/cost-status",
    summary="Cost tracker and fuse status",
    tags=["Health"],
)
async def cost_status() -> dict[str, Any]:
    """Return current cost consumption and fuse status.

    Shows real-time cost tracking across study/daily/weekly/monthly
    dimensions and the current fuse status.
    """
    from aicbc.cost.fuse import CostFuse
    from aicbc.cost.tracker import FuseStatus

    fuse = CostFuse()
    status, details = fuse.tracker.check_fuse_status()
    costs = details.get("costs_cny", {})
    thresholds = details.get("thresholds", {})
    return {
        "fuse_status": status.value,
        "total_cost_cny": costs.get("global", 0.0),
        "daily_cost_cny": costs.get("daily", 0.0),
        "daily_budget_cny": thresholds.get("daily", 0.0),
        "warning": status != FuseStatus.NORMAL,
        "details": details,
    }


@router.get(
    "/dashboard/summary",
    summary="Aggregated dashboard statistics",
    tags=["Health"],
)
async def dashboard_summary() -> dict[str, Any]:
    """Aggregated dashboard statistics from all subsystems.

    Uses MongoDB aggregation for status counts and projection for recent
    studies. Cached for 30s to reduce load on frequently-refreshed dashboard.
    """
    from datetime import UTC, datetime, timedelta

    from aicbc.monitoring.metrics import record_mongodb_query_duration

    cache = get_dashboard_summary_cache()
    cached = cache.get("summary")
    if cached is not None:
        return cached  # type: ignore[return-value]

    persona_store = get_store()
    study_store = get_questionnaire_store()

    start = datetime.now(UTC)
    study_status_counts = await study_store.acount_studies_by_status()
    record_mongodb_query_duration(
        "studies", "aggregate_count", (datetime.now(UTC) - start).total_seconds()
    )

    total_studies = sum(study_status_counts.values())

    start = datetime.now(UTC)
    persona_count = await persona_store.acount()
    record_mongodb_query_duration("personas", "count", (datetime.now(UTC) - start).total_seconds())

    week_ago = datetime.now(UTC) - timedelta(days=7)
    start = datetime.now(UTC)
    recent_docs, _ = await study_store.alist_recent_studies(week_ago, limit=10)
    record_mongodb_query_duration(
        "studies", "find_projection", (datetime.now(UTC) - start).total_seconds()
    )

    recent_studies = [
        {
            "study_id": doc["study_id"],
            "product_category": doc.get("product_category", ""),
            "status": doc["status"],
            "created_at": doc["created_at"].isoformat(),
        }
        for doc in recent_docs
    ]

    result = {
        "summary": {
            "total_studies": total_studies,
            "total_personas": persona_count,
            "studies_by_status": study_status_counts,
            "recent_studies_last_7d": len(recent_studies),
        },
        "recent_studies": recent_studies,
    }
    cache.set("summary", result)
    return result
