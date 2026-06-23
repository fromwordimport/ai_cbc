"""Feature flag API routes.

Public read endpoints allow the application (and clients) to query flag state.
Admin write endpoints allow the CI/CD ``feature-switch.yml`` workflow to toggle
flags without redeploying.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from aicbc.core.feature_flags import FeatureFlag, get_feature_flag_store

router = APIRouter()


@router.get("/flags/{flag_name}")
async def get_flag(flag_name: str, environment: str = "staging") -> dict[str, Any]:
    """Return the current state of a feature flag."""
    store = get_feature_flag_store()
    flag = await store.aget(flag_name, environment)
    if flag is None:
        return {
            "name": flag_name,
            "environment": environment,
            "enabled": False,
            "updated_by": "system",
            "updated_at": None,
        }
    return flag.to_dict()


@router.get("/flags")
async def list_flags(environment: str | None = None) -> list[dict[str, Any]]:
    """List all known feature flags, optionally filtered by environment."""
    store = get_feature_flag_store()
    flags = await store.alist(environment)
    return [flag.to_dict() for flag in flags]


@router.put("/admin/flags/{flag_name}")
async def set_flag(
    flag_name: str,
    action: str,
    environment: str = "staging",
    requested_by: str = "workflow",
) -> dict[str, Any]:
    """Enable or disable a feature flag.

    This endpoint is protected by the RBAC middleware: callers must present an
    admin role (e.g. ``X-User-Role: admin`` header for service accounts).
    """
    if action not in ("enable", "disable"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action must be 'enable' or 'disable'",
        )

    store = get_feature_flag_store()
    flag = FeatureFlag(
        name=flag_name,
        enabled=action == "enable",
        environment=environment,
        updated_by=requested_by,
        updated_at=datetime_now_iso(),
    )
    await store.aset(flag)
    return flag.to_dict()


def datetime_now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
