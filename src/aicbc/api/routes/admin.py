"""Admin routes: settings, cost status, and audit log queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from aicbc.api.schemas import AuditLogListResponse
from aicbc.config.settings import get_settings
from aicbc.core.audit import get_audit_logger
from aicbc.core.security.encryption import encrypt_value, is_encrypted

router = APIRouter()

# Map provider names to their settings attribute and default model field name.
_PROVIDER_ATTRS: dict[str, tuple[str, str]] = {
    "anthropic": ("anthropic", "model_persona"),
    "openai": ("openai", "model"),
    "deepseek": ("deepseek", "model"),
    "qwen": ("qwen", "model"),
    "glm": ("glm", "model"),
}


def _provider_config(provider: str) -> dict[str, Any]:
    """Return non-sensitive provider configuration for the frontend."""
    s = get_settings()
    if provider not in _PROVIDER_ATTRS:
        return {}
    attr, default_model_attr = _PROVIDER_ATTRS[provider]
    cfg = getattr(s, attr)
    return {
        "enabled": getattr(cfg, "enabled", False),
        "api_key_set": bool(getattr(cfg, "api_key", "")),
        "base_url": getattr(cfg, "base_url", ""),
        "model": getattr(cfg, default_model_attr, ""),
    }


def _validate_authenticity_threshold(
    name: str, value: Any, max_score: int
) -> tuple[int | None, str | None]:
    """Validate an authenticity threshold value.

    Returns (validated_value, error_message). A boolean is rejected because
    ``bool`` is a subclass of ``int`` in Python.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None, f"{name} must be an integer"
    if value < 0 or value > max_score:
        return None, f"{name} must be between 0 and {max_score}"
    return value, None


def _validate_positive_number(name: str, value: Any) -> tuple[float | None, str | None]:
    """Validate a positive numeric budget value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f"{name} must be a number"
    if value <= 0:
        return None, f"{name} must be > 0"
    return float(value), None


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
            "provider": s.llm.provider,
            "model": s.llm.model,
            "temperature": s.llm.temperature,
            "max_tokens": s.llm.max_tokens,
            "timeout_seconds": s.llm.timeout_seconds,
        },
        "providers": {name: _provider_config(name) for name in _PROVIDER_ATTRS},
        "available_models": {
            "anthropic": {
                "persona": s.anthropic.model_persona,
                "simulation": s.anthropic.model_simulation,
                "audit": s.anthropic.model_audit,
            },
            "openai": {"model": s.openai.model},
            "deepseek": {"model": s.deepseek.model},
            "qwen": {"model": s.qwen.model},
            "glm": {"model": s.glm.model},
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
            "max_score": s.authenticity.max_score,
        },
    }


@router.put("/admin/settings")
async def admin_update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Update select non-sensitive configuration at runtime.

    Only a subset of settings can be changed at runtime without restarting.
    Security-critical settings (environment) are read-only. API keys are
    encrypted with SECRET_KEY before storage and are never returned.
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
        if key == "llm_provider" and isinstance(value, str):
            s.llm.provider = value
            applied[key] = value
        elif key == "llm_model" and isinstance(value, str):
            s.llm.model = value
            applied[key] = value
        elif key == "providers" and isinstance(value, dict):
            for provider, cfg in value.items():
                if provider not in _PROVIDER_ATTRS:
                    rejected[f"providers.{provider}"] = "unknown provider"
                    continue
                attr, default_model_attr = _PROVIDER_ATTRS[provider]
                provider_settings = getattr(s, attr)
                provider_applied: dict[str, object] = {}
                if isinstance(cfg, dict):
                    if "base_url" in cfg and isinstance(cfg["base_url"], str):
                        provider_settings.base_url = cfg["base_url"]
                        provider_applied["base_url"] = cfg["base_url"]
                    if "model" in cfg and isinstance(cfg["model"], str):
                        setattr(provider_settings, default_model_attr, cfg["model"])
                        provider_applied["model"] = cfg["model"]
                    if "api_key" in cfg and isinstance(cfg["api_key"], str):
                        api_key = cfg["api_key"].strip()
                        if api_key:
                            # Re-encrypt only if the value is plaintext.
                            if not is_encrypted(api_key):
                                api_key = encrypt_value(api_key, s.secret_key)
                            provider_settings.api_key = api_key
                            provider_settings.enabled = True
                            provider_applied["api_key"] = "***"
                        elif getattr(provider_settings, "api_key", ""):
                            # Empty string clears the key.
                            provider_settings.api_key = ""
                            provider_settings.enabled = False
                            provider_applied["api_key"] = ""
                if provider_applied:
                    applied[f"providers.{provider}"] = provider_applied
        elif key in allowed_llm and hasattr(s.llm, key):
            object.__setattr__(s.llm, key, value)
            applied[key] = value
        elif key in allowed_authenticity and hasattr(s.authenticity, key):
            validated, err = _validate_authenticity_threshold(key, value, s.authenticity.max_score)
            if err:
                rejected[key] = err
                continue
            assert validated is not None
            # Ensure pass_threshold does not exceed excellent_threshold.
            other_key = "excellent_threshold" if key == "pass_threshold" else "pass_threshold"
            other_value = payload.get(other_key)
            if other_value is None:
                other_value = getattr(s.authenticity, other_key)
            other_validated, _ = _validate_authenticity_threshold(
                other_key, other_value, s.authenticity.max_score
            )
            if other_validated is not None:
                if key == "pass_threshold" and validated > other_validated:
                    rejected[key] = "pass_threshold must be <= excellent_threshold"
                    continue
                if key == "excellent_threshold" and validated < other_validated:
                    rejected[key] = "excellent_threshold must be >= pass_threshold"
                    continue
            object.__setattr__(s.authenticity, key, validated)
            applied[key] = validated
        elif key in allowed_study and hasattr(s.study, key):
            object.__setattr__(s.study, key, value)
            applied[key] = value
        elif key == "cost_budget_daily":
            cost_validated, cost_err = _validate_positive_number(key, value)
            if cost_validated is not None:
                object.__setattr__(s.cost_fuse, "daily_cny", cost_validated)
                applied[key] = cost_validated
            elif cost_err:
                rejected[key] = cost_err
        elif key == "cost_budget_monthly":
            cost_validated, cost_err = _validate_positive_number(key, value)
            if cost_validated is not None:
                object.__setattr__(s.cost_fuse, "monthly_cny", cost_validated)
                applied[key] = cost_validated
            elif cost_err:
                rejected[key] = cost_err
        else:
            rejected[key] = f"field '{key}' is read-only or not recognized"

    if rejected:
        return {
            "status": "partial",
            "applied": applied,
            "rejected": rejected,
            "note": "Runtime-only changes — restart reverts to .env values",
        }

    # Refresh the singleton LLM client so runtime provider/key changes take effect.
    try:
        from aicbc.api.dependencies import get_llm_client

        get_llm_client().reconfigure()
    except Exception as exc:  # pragma: no cover - dependencies may be unavailable in some contexts
        logger = get_audit_logger()
        logger.warning("llm_client_reconfigure_failed", error=str(exc))

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
