"""Cost fuse logic: automatic model degradation and call blocking.

Integrates with ``LLMClient`` to intercept calls when budgets are
exhausted and to downgrade models proactively.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import structlog

from aicbc.config.settings import get_settings
from aicbc.cost.tracker import CostTracker, FuseStatus

logger = structlog.get_logger("aicbc.cost")


class DegradationLevel(StrEnum):
    """Model degradation level based on cost consumption."""

    STANDARD = "STANDARD"  # Normal routing
    DEGRADED = "DEGRADED"  # Switch to lighter model
    EMERGENCY = "EMERGENCY"  # Block non-essential calls


class CostFuseError(Exception):
    """Raised when a call is blocked by the cost fuse."""

    pass


class CostFuse:
    """High-level cost fuse that wraps LLM calls.

    Usage::

        fuse = CostFuse()
        allowed, status, degrade_model = fuse.pre_call_check(study_id="proj-001")
        if not allowed:
            raise CostFuseError("Cost fuse triggered")
        # ... make LLM call ...
        fuse.record_call(response, study_id="proj-001")
    """

    def __init__(self, tracker: CostTracker | None = None) -> None:
        self._tracker = tracker or CostTracker()
        self._settings = get_settings().cost_fuse

    @property
    def tracker(self) -> CostTracker:
        """Expose the underlying tracker."""
        return self._tracker

    # ------------------------------------------------------------------
    # Pre-call check
    # ------------------------------------------------------------------

    def pre_call_check(
        self,
        study_id: str | None = None,
        requested_model: str | None = None,
    ) -> tuple[bool, FuseStatus, str]:
        """Check whether a call should proceed and what model to use.

        Returns:
            (allowed, status, effective_model)

        - ``allowed`` is False only at FUSE / EMERGENCY.
        - ``effective_model`` is the downgrade model when status is DEGRADE,
          otherwise the requested model.
        """
        allowed, status, details = self._tracker.should_allow_call(study_id)

        # Emit notification if status changed
        self._tracker.notify_if_changed(status, details)

        if status == FuseStatus.EMERGENCY:
            logger.error(
                "cost_fuse_blocked_emergency",
                study_id=study_id,
                status=status.value,
            )
            return False, status, requested_model or ""

        if status == FuseStatus.FUSE:
            logger.error(
                "cost_fuse_blocked",
                study_id=study_id,
                status=status.value,
            )
            return False, status, requested_model or ""

        if status == FuseStatus.DEGRADE:
            degrade_model = self._settings.degrade_model
            logger.warning(
                "cost_fuse_degrade_model",
                study_id=study_id,
                requested_model=requested_model,
                degrade_model=degrade_model,
            )
            return True, status, degrade_model

        return True, status, requested_model or ""

    # ------------------------------------------------------------------
    # Post-call recording
    # ------------------------------------------------------------------

    def record_call(
        self,
        response: Any,
        *,
        study_id: str | None = None,
        persona_id: str | None = None,
        task_phase: str = "unknown",
        degraded: bool = False,
    ) -> None:
        """Record an LLM response cost into the tracker.

        ``response`` must expose the attributes used by ``LLMResponse``:
        ``estimated_cost_usd``, ``provider``, ``model``, ``prompt_tokens``,
        ``completion_tokens``.
        """
        try:
            cost_usd = getattr(response, "estimated_cost_usd", 0.0)
            provider = getattr(response, "provider", "unknown")
            model = getattr(response, "model", "unknown")
            prompt_tokens = getattr(response, "prompt_tokens", 0)
            completion_tokens = getattr(response, "completion_tokens", 0)
        except Exception as exc:
            logger.warning("cost_fuse_record_failed", error=str(exc))
            return

        provider_str = provider.value if hasattr(provider, "value") else str(provider)

        self._tracker.record(
            cost_usd=cost_usd,
            study_id=study_id,
            persona_id=persona_id,
            task_phase=task_phase,
            provider=provider_str,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            degraded=degraded,
        )

    # ------------------------------------------------------------------
    # Degradation helpers
    # ------------------------------------------------------------------

    def get_degradation_level(self, study_id: str | None = None) -> DegradationLevel:
        """Return the current degradation level."""
        status, _ = self._tracker.check_fuse_status(study_id)
        if status == FuseStatus.EMERGENCY:
            return DegradationLevel.EMERGENCY
        if status in (FuseStatus.FUSE, FuseStatus.DEGRADE):
            return DegradationLevel.DEGRADED
        return DegradationLevel.STANDARD

    def resolve_model(self, model: str | None, study_id: str | None = None) -> str:
        """Resolve the effective model considering degradation."""
        level = self.get_degradation_level(study_id)
        if level == DegradationLevel.DEGRADED:
            return self._settings.degrade_model
        settings = get_settings()
        if model:
            return model
        if settings.llm.model:
            return settings.llm.model
        # Fall back to the active provider's default model.
        from aicbc.llm.client import LLMClient

        provider = LLMClient._detect_provider("")
        return LLMClient._default_model_for_provider(provider)
