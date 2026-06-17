"""Admin routes: settings, cost status, and audit log queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from aicbc.api.schemas import AuditLogListResponse
from aicbc.config.settings import get_settings
from aicbc.core.audit import get_audit_logger

router = APIRouter()


@router.get("/admin/settings")
async def admin_get_settings() -> dict[str, Any]:
    """Return non-sensitive configuration for the frontend settings page.

    SECURITY NOTE: This endpoint exposes configuration metadata. Sensitive
    fields (API keys, secret keys, passwords) are excluded.
    """
    s = get_settings()
    return {
        "environment": s.environment,
        "log_level": s.log_level,
        "llm": {
            "temperature": s.llm.temperature,
            "max_tokens": s.llm.max_tokens,
            "timeout_seconds": s.llm.timeout_seconds,
        },
        "available_models": {
            "anthropic": {
                "persona": s.anthropic.model_persona,
                "simulation": s.anthropic.model_simulation,
                "audit": s.anthropic.model_audit,
            },
            "openai": {"model": s.openai.model},
        },
        "cost_fuse": {
            "single_study_cny": s.cost_fuse.single_study_cny,
            "daily_cny": s.cost_fuse.daily_cny,
            "monthly_cny": s.cost_fuse.monthly_cny,
        },
        "study_defaults": {
            "n_choice_sets": s.study.n_choice_sets,
            "n_alternatives": s.study.n_alternatives,
            "sample_size": s.study.sample_size,
            "d_efficiency_target": s.study.d_efficiency_target,
        },
        "authenticity": {
            "pass_threshold": s.authenticity.pass_threshold,
            "excellent_threshold": s.authenticity.excellent_threshold,
        },
    }


@router.put("/admin/settings")
async def admin_update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Update select non-sensitive configuration at runtime.

    Only a subset of settings can be changed at runtime without restarting.
    Security-critical settings (API keys, environment) are read-only.
    Changes are applied to the cached Settings singleton immediately but
    revert to .env values on restart.
    """
    s = get_settings()
    allowed_llm = {"temperature", "max_tokens", "timeout_seconds"}
    allowed_authenticity = {"pass_threshold", "excellent_threshold"}
    allowed_study = {
        "n_choice_sets",
        "n_alternatives",
        "sample_size",
        "d_efficiency_target",
    }
    applied: dict[str, object] = {}
    rejected: dict[str, str] = {}

    for key, value in payload.items():
        if key in allowed_llm and hasattr(s.llm, key):
            object.__setattr__(s.llm, key, value)
            applied[key] = value
        elif key in allowed_authenticity and hasattr(s.authenticity, key):
            object.__setattr__(s.authenticity, key, value)
            applied[key] = value
        elif key in allowed_study and hasattr(s.study, key):
            object.__setattr__(s.study, key, value)
            applied[key] = value
        else:
            rejected[key] = f"field '{key}' is read-only or not recognized"

    if rejected:
        return {
            "status": "partial",
            "applied": applied,
            "rejected": rejected,
            "note": "Runtime-only changes — restart reverts to .env values",
        }
    return {
        "status": "ok",
        "applied": applied,
        "note": "Runtime-only changes — restart reverts to .env values",
    }


@router.get("/cost-status")
async def admin_cost_status() -> dict[str, Any]:
    """Return current cost consumption and fuse status."""
    from aicbc.cost.fuse import CostFuse

    fuse = CostFuse()
    status, details = fuse.tracker.check_fuse_status()
    return {
        "fuse_status": status.value,
        "details": details,
    }


@router.get("/admin/audit-logs", response_model=AuditLogListResponse)
async def admin_audit_logs(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    user_id: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    result: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AuditLogListResponse:
    """Query audit logs with optional filters and pagination.

    Admin role is required via RBAC middleware (`/api/v1/admin/*`).
    """
    logger = get_audit_logger()
    filters: dict[str, Any] = {}
    if start_time is not None:
        filters["start_time"] = start_time
    if end_time is not None:
        filters["end_time"] = end_time
    if user_id is not None:
        filters["user_id"] = user_id
    if action is not None:
        filters["action"] = action
    if resource is not None:
        filters["resource"] = resource
    if result is not None:
        filters["result"] = result

    entries, total = await logger.query_logs(filters, page=page, page_size=page_size)

    return AuditLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        entries=entries,
    )
