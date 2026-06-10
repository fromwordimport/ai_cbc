"""Cost tracking and budget monitoring for AI_CBC.

Implements the cost tracking and fuse mechanism specified in:
- docs/成本管控方案.md
- docs/系统部署与运维架构.md (Section 3)
- docs/部署架构初步方案与实施路线图.md (Section 4.3)

Usage:
    tracker = CostTracker()
    tracker.record_call("claude-sonnet-4-6", 1000, 500, 0.05)
    status = tracker.check_budget_status()
    if status == BudgetStatus.DEGRADE:
        # Trigger model degradation
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from aicbc.config.settings import get_settings
from aicbc.monitoring.metrics import (
    COST_PER_PERSONA_CNY,
    COST_PER_STUDY_CNY,
    record_llm_call,
)

logger = structlog.get_logger("aicbc.cost")


@dataclass
class CostRecord:
    """Record of a single LLM API call cost."""

    timestamp: float
    model: str
    provider: str
    task_type: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cost_cny: float
    latency_seconds: float
    study_id: str | None = None
    persona_id: str | None = None
    cached: bool = False
    degraded: bool = False


@dataclass
class BudgetStatus:
    """Current budget status."""

    level: str  # normal | warning | degrade | fuse | emergency
    current_daily_cost: float
    daily_budget: float
    current_weekly_cost: float
    weekly_budget: float
    ratio: float
    remaining: float


class CostTracker:
    """Track LLM API costs and enforce budget constraints.

    Implements a four-level fuse mechanism:
    - NORMAL: Normal operation
    - WARNING (80%): Send alert, continue
    - DEGRADE (95%): Auto-switch to cheaper models
    - FUSE (100%): Block new LLM calls
    - EMERGENCY (120%): Lock all operations
    """

    EXCHANGE_RATE = 7.2  # USD to CNY

    def __init__(self, state_file: str | None = None) -> None:
        """Initialize cost tracker.

        Args:
            state_file: Optional path to persist cost state.
        """
        settings = get_settings()
        self.daily_budget = settings.cost_fuse.daily_cny
        self.weekly_budget = settings.cost_fuse.weekly_cny
        self.single_study_budget = settings.cost_fuse.single_study_cny
        self.degrade_model = settings.cost_fuse.degrade_model

        self.state_file = state_file or "./data/cost_state.json"
        self.records: list[CostRecord] = []
        self._daily_cost = 0.0
        self._weekly_cost = 0.0
        self._study_costs: dict[str, float] = {}
        self._last_check = time.time()

        # Load persisted state
        self._load_state()

        logger.info(
            "cost_tracker_initialized",
            daily_budget=self.daily_budget,
            weekly_budget=self.weekly_budget,
            single_study_budget=self.single_study_budget,
        )

    def _load_state(self) -> None:
        """Load cost state from file."""
        state_path = Path(self.state_file)
        if not state_path.exists():
            return

        try:
            with open(state_path, encoding="utf-8") as f:
                data = json.load(f)

            self._daily_cost = data.get("daily_cost", 0.0)
            self._weekly_cost = data.get("weekly_cost", 0.0)
            self._study_costs = data.get("study_costs", {})

            # Reset daily cost if it's a new day
            last_date = data.get("last_date", "")
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            if last_date != today:
                logger.info("new_day_reset", last_date=last_date, today=today)
                self._daily_cost = 0.0

            # Reset weekly cost if it's a new week
            last_week = data.get("last_week", "")
            current_week = datetime.now(UTC).strftime("%Y-%W")
            if last_week != current_week:
                logger.info("new_week_reset", last_week=last_week, current_week=current_week)
                self._weekly_cost = 0.0

        except Exception as exc:
            logger.warning("cost_state_load_failed", error=str(exc))

    def _save_state(self) -> None:
        """Persist cost state to file."""
        state_path = Path(self.state_file)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "daily_cost": self._daily_cost,
            "weekly_cost": self._weekly_cost,
            "study_costs": self._study_costs,
            "last_date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "last_week": datetime.now(UTC).strftime("%Y-%W"),
            "last_updated": datetime.now(UTC).isoformat(),
        }

        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            logger.warning("cost_state_save_failed", error=str(exc))

    def record_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_seconds: float,
        task_type: str = "default",
        study_id: str | None = None,
        persona_id: str | None = None,
        cached: bool = False,
        degraded: bool = False,
    ) -> CostRecord:
        """Record a single LLM API call cost.

        Args:
            model: Model identifier.
            prompt_tokens: Number of prompt tokens.
            completion_tokens: Number of completion tokens.
            cost_usd: Cost in USD.
            latency_seconds: API call latency.
            task_type: Type of task.
            study_id: Optional study ID.
            persona_id: Optional persona ID.
            cached: Whether the response was cached.
            degraded: Whether a degraded model was used.

        Returns:
            CostRecord object.
        """
        cost_cny = cost_usd * self.EXCHANGE_RATE

        record = CostRecord(
            timestamp=time.time(),
            model=model,
            provider=self._detect_provider(model),
            task_type=task_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            cost_cny=cost_cny,
            latency_seconds=latency_seconds,
            study_id=study_id,
            persona_id=persona_id,
            cached=cached,
            degraded=degraded,
        )

        self.records.append(record)
        self._daily_cost += cost_cny
        self._weekly_cost += cost_cny

        if study_id:
            self._study_costs[study_id] = self._study_costs.get(study_id, 0.0) + cost_cny

        # Update Prometheus metrics
        record_llm_call(
            model=model,
            agent=task_type,
            status="success",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_seconds=latency_seconds,
        )

        if persona_id:
            COST_PER_PERSONA_CNY.labels(model=model).set(
                self._study_costs.get(study_id, 0.0) / max(len(self.records), 1)
            )

        if study_id:
            COST_PER_STUDY_CNY.labels(study_id=study_id).set(self._study_costs[study_id])

        logger.info(
            "cost_recorded",
            model=model,
            cost_usd=round(cost_usd, 6),
            cost_cny=round(cost_cny, 4),
            daily_total=round(self._daily_cost, 4),
            weekly_total=round(self._weekly_cost, 4),
            task_type=task_type,
        )

        # Periodically save state
        if time.time() - self._last_check > 60:
            self._save_state()
            self._last_check = time.time()

        return record

    def check_budget_status(self) -> BudgetStatus:
        """Check current budget status.

        Returns:
            BudgetStatus with current level and details.
        """
        daily_ratio = self._daily_cost / self.daily_budget if self.daily_budget > 0 else 0
        weekly_ratio = self._weekly_cost / self.weekly_budget if self.weekly_budget > 0 else 0

        # Use the higher ratio
        ratio = max(daily_ratio, weekly_ratio)
        remaining = self.daily_budget - self._daily_cost

        if ratio >= 1.20:
            level = "emergency"
        elif ratio >= 1.00:
            level = "fuse"
        elif ratio >= 0.95:
            level = "degrade"
        elif ratio >= 0.80:
            level = "warning"
        else:
            level = "normal"

        status = BudgetStatus(
            level=level,
            current_daily_cost=self._daily_cost,
            daily_budget=self.daily_budget,
            current_weekly_cost=self._weekly_cost,
            weekly_budget=self.weekly_budget,
            ratio=round(ratio, 4),
            remaining=round(remaining, 4),
        )

        # Log level changes
        if level in ("degrade", "fuse", "emergency"):
            logger.warning(
                "budget_threshold_exceeded",
                level=level,
                daily_cost=self._daily_cost,
                daily_budget=self.daily_budget,
                ratio=ratio,
            )

        return status

    def check_study_budget(self, study_id: str) -> dict[str, Any]:
        """Check budget status for a specific study.

        Args:
            study_id: Study identifier.

        Returns:
            Budget info for the study.
        """
        study_cost = self._study_costs.get(study_id, 0.0)
        ratio = study_cost / self.single_study_budget if self.single_study_budget > 0 else 0

        return {
            "study_id": study_id,
            "current_cost": round(study_cost, 4),
            "budget": self.single_study_budget,
            "ratio": round(ratio, 4),
            "remaining": round(self.single_study_budget - study_cost, 4),
            "exceeded": ratio >= 1.0,
        }

    def can_execute(self, estimated_cost_cny: float = 0.0) -> bool:
        """Check if a new LLM call can be executed.

        Args:
            estimated_cost_cny: Estimated cost of the call.

        Returns:
            True if execution is allowed, False otherwise.
        """
        status = self.check_budget_status()

        if status.level in ("fuse", "emergency"):
            return False

        if status.level == "degrade":
            # Allow but only with degraded model (caller should handle)
            return True

        # Check if this call would exceed budget
        projected = self._daily_cost + estimated_cost_cny
        if projected > self.daily_budget:
            logger.warning(
                "call_would_exceed_budget",
                projected=projected,
                budget=self.daily_budget,
            )
            return False

        return True

    def get_summary(self) -> dict[str, Any]:
        """Get cost tracking summary.

        Returns:
            Summary dictionary with current costs and status.
        """
        status = self.check_budget_status()

        # Calculate per-model costs
        model_costs: dict[str, float] = {}
        task_costs: dict[str, float] = {}
        for record in self.records:
            model_costs[record.model] = model_costs.get(record.model, 0.0) + record.cost_cny
            task_costs[record.task_type] = task_costs.get(record.task_type, 0.0) + record.cost_cny

        return {
            "status": status.level,
            "daily": {
                "current": round(self._daily_cost, 4),
                "budget": self.daily_budget,
                "remaining": round(self.daily_budget - self._daily_cost, 4),
                "ratio": status.ratio,
            },
            "weekly": {
                "current": round(self._weekly_cost, 4),
                "budget": self.weekly_budget,
                "remaining": round(self.weekly_budget - self._weekly_cost, 4),
            },
            "single_study_budget": self.single_study_budget,
            "model_breakdown": {k: round(v, 4) for k, v in model_costs.items()},
            "task_breakdown": {k: round(v, 4) for k, v in task_costs.items()},
            "total_calls": len(self.records),
            "study_costs": {k: round(v, 4) for k, v in self._study_costs.items()},
        }

    def reset_daily(self) -> None:
        """Reset daily cost counter."""
        logger.info("daily_cost_reset", old_cost=self._daily_cost)
        self._daily_cost = 0.0
        self._save_state()

    def reset_weekly(self) -> None:
        """Reset weekly cost counter."""
        logger.info("weekly_cost_reset", old_cost=self._weekly_cost)
        self._weekly_cost = 0.0
        self._save_state()

    @staticmethod
    def _detect_provider(model: str) -> str:
        """Detect provider from model name."""
        if model.lower().startswith("claude-"):
            return "anthropic"
        if model.lower().startswith("gpt-"):
            return "openai"
        return "unknown"

    def export_records(self, output_path: str) -> None:
        """Export cost records to JSON file.

        Args:
            output_path: Path to output file.
        """
        data = [
            {
                "timestamp": datetime.fromtimestamp(r.timestamp, UTC).isoformat(),
                "model": r.model,
                "provider": r.provider,
                "task_type": r.task_type,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cost_usd": r.cost_usd,
                "cost_cny": r.cost_cny,
                "latency_seconds": r.latency_seconds,
                "study_id": r.study_id,
                "persona_id": r.persona_id,
                "cached": r.cached,
                "degraded": r.degraded,
            }
            for r in self.records
        ]

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("cost_records_exported", path=output_path, count=len(data))
