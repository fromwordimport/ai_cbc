"""LLM Model Router with cost-aware routing and automatic degradation.

This module implements the ModelRouter specified in the deployment architecture,
supporting dynamic model switching based on:
- Task type (persona_generation, choice_simulation, review_scoring, etc.)
- Budget status (normal, warning, degrade, fuse)
- Model availability and failure rates
- A/B testing configuration

Usage:
    router = ModelRouter()
    model = router.route({"type": "persona_generation", "complexity": "high"})
    # Returns "claude-sonnet-4-6" or degraded model based on budget
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog

from aicbc.config.settings import get_settings
from aicbc.cost.fuse import CostFuse

logger = structlog.get_logger("aicbc.llm.router")


class BudgetStatus(StrEnum):
    """Budget status levels for cost-aware routing."""

    NORMAL = "normal"
    WARNING = "warning"
    DEGRADE = "degrade"
    FUSE = "fuse"
    EMERGENCY = "emergency"


class TaskType(StrEnum):
    """Supported task types for model routing."""

    PERSONA_GENERATION = "persona_generation"
    CHOICE_SIMULATION = "choice_simulation"
    REVIEW_SCORING = "review_scoring"
    RESULT_INTERPRETATION = "result_interpretation"
    DEEP_ANALYSIS = "deep_analysis"
    DEFAULT = "default"


@dataclass
class ModelConfig:
    """Configuration for a single LLM model."""

    provider: str
    input_cost_per_1k: float  # USD
    output_cost_per_1k: float  # USD
    max_tokens: int
    quality_tier: str
    enabled: bool = True
    failure_count: int = 0
    last_failure: float | None = None


@dataclass
class RoutingRule:
    """A routing rule for model selection."""

    task_type: str
    default_model: str
    degrade_model: str | None = None
    fallback_model: str | None = None


@dataclass
class BudgetThreshold:
    """Budget threshold configuration."""

    warning: float = 0.80
    degrade: float = 0.95
    fuse: float = 1.00
    emergency: float = 1.20


class ModelRouter:
    """Dynamic LLM model router with cost awareness and failover.

    Implements the model routing strategy defined in:
    - docs/系统部署与运维架构.md (Section 4)
    - docs/部署架构初步方案与实施路线图.md (Section 5)
    - docs/成本管控方案.md (Section 3.1)
    """

    # Default model configurations — sourced from unified pricing registry.
    # Input/output costs are per-1K-token in USD (matching PRICE_TABLE).
    # fmt: off
    DEFAULT_MODELS: dict[str, ModelConfig] = {
        "claude-sonnet-4-6": ModelConfig(
            provider="anthropic",
            input_cost_per_1k=3.0, output_cost_per_1k=15.0,
            max_tokens=200_000, quality_tier="high",
        ),
        "claude-haiku-4-5": ModelConfig(
            provider="anthropic",
            input_cost_per_1k=0.25, output_cost_per_1k=1.25,
            max_tokens=200_000, quality_tier="medium",
        ),
        "gpt-4o": ModelConfig(
            provider="openai",
            input_cost_per_1k=5.0, output_cost_per_1k=15.0,
            max_tokens=128_000, quality_tier="high",
        ),
        "gpt-4o-mini": ModelConfig(
            provider="openai",
            input_cost_per_1k=0.15, output_cost_per_1k=0.60,
            max_tokens=128_000, quality_tier="medium",
        ),
    }
    # fmt: on

    DEFAULT_ROUTES: dict[str, RoutingRule] = {
        TaskType.PERSONA_GENERATION: RoutingRule(
            task_type=TaskType.PERSONA_GENERATION,
            default_model="claude-sonnet-4-6",
            degrade_model="claude-haiku-4-5",
            fallback_model="gpt-4o",
        ),
        TaskType.CHOICE_SIMULATION: RoutingRule(
            task_type=TaskType.CHOICE_SIMULATION,
            default_model="claude-sonnet-4-6",
            degrade_model="claude-haiku-4-5",
            fallback_model="gpt-4o",
        ),
        TaskType.REVIEW_SCORING: RoutingRule(
            task_type=TaskType.REVIEW_SCORING,
            default_model="claude-haiku-4-5",
            degrade_model="gpt-4o-mini",
        ),
        TaskType.RESULT_INTERPRETATION: RoutingRule(
            task_type=TaskType.RESULT_INTERPRETATION,
            default_model="claude-haiku-4-5",
            degrade_model="gpt-4o-mini",
        ),
        TaskType.DEEP_ANALYSIS: RoutingRule(
            task_type=TaskType.DEEP_ANALYSIS,
            default_model="claude-opus-4-8",
            degrade_model="claude-sonnet-4-6",
            fallback_model="gpt-4o",
        ),
        TaskType.DEFAULT: RoutingRule(
            task_type=TaskType.DEFAULT,
            default_model="claude-sonnet-4-6",
            degrade_model="claude-haiku-4-5",
            fallback_model="gpt-4o",
        ),
    }

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize the model router.

        Args:
            config_path: Optional path to a YAML/JSON config file for model configs.
        """
        self.models: dict[str, ModelConfig] = copy.deepcopy(self.DEFAULT_MODELS)
        self.routes: dict[str, RoutingRule] = copy.deepcopy(self.DEFAULT_ROUTES)
        self.budget_threshold = BudgetThreshold()
        self._current_budget_status = BudgetStatus.NORMAL
        self._current_daily_cost = 0.0
        self._daily_budget = 1000.0  # CNY, from settings

        # Load custom config if provided
        if config_path and Path(config_path).exists():
            self._load_config(config_path)

        # Load from settings
        settings = get_settings()
        self._daily_budget = settings.cost_fuse.daily_cny
        self._degrade_model = settings.cost_fuse.degrade_model

        logger.info(
            "model_router_initialized",
            daily_budget=self._daily_budget,
            degrade_model=self._degrade_model,
        )

    def _load_config(self, path: str) -> None:
        """Load model configuration from file."""
        config_file = Path(path)
        if not config_file.exists():
            return

        try:
            with open(config_file, encoding="utf-8") as f:
                if config_file.suffix == ".json":
                    data = json.load(f)
                else:
                    # Simple YAML-like parsing for models config
                    import yaml

                    data = yaml.safe_load(f)

            if "models" in data:
                for name, cfg in data["models"].items():
                    self.models[name] = ModelConfig(**cfg)

            if "routing_rules" in data:
                for task, rule in data["routing_rules"].items():
                    self.routes[task] = RoutingRule(**rule)

            if "budget_thresholds" in data:
                self.budget_threshold = BudgetThreshold(**data["budget_thresholds"])

            logger.info("model_config_loaded", path=path)
        except Exception as exc:
            logger.warning("model_config_load_failed", path=path, error=str(exc))

    def update_budget_status(
        self, current_cost: float, budget: float | None = None
    ) -> BudgetStatus:
        """Update budget status based on current spending.

        Args:
            current_cost: Current daily cost in CNY.
            budget: Optional budget override (defaults to settings).

        Returns:
            Current budget status level.
        """
        if budget is not None:
            self._daily_budget = budget

        self._current_daily_cost = current_cost
        ratio = current_cost / self._daily_budget if self._daily_budget > 0 else 0

        if ratio >= self.budget_threshold.emergency:
            status = BudgetStatus.EMERGENCY
        elif ratio >= self.budget_threshold.fuse:
            status = BudgetStatus.FUSE
        elif ratio >= self.budget_threshold.degrade:
            status = BudgetStatus.DEGRADE
        elif ratio >= self.budget_threshold.warning:
            status = BudgetStatus.WARNING
        else:
            status = BudgetStatus.NORMAL

        if status != self._current_budget_status:
            logger.warning(
                "budget_status_changed",
                old_status=self._current_budget_status.value,
                new_status=status.value,
                current_cost=current_cost,
                budget=self._daily_budget,
                ratio=round(ratio, 4),
            )
            self._current_budget_status = status

        return status

    def get_budget_status(self) -> BudgetStatus:
        """Get current budget status."""
        return self._current_budget_status

    def route(self, task: dict[str, Any]) -> str:
        """Select the best model for a given task.

        Args:
            task: Task dictionary with keys:
                - type: TaskType value
                - complexity: Optional complexity hint (low/medium/high)
                - urgency: Optional urgency hint (low/normal/high)
                - preferred_model: Optional explicit model preference

        Returns:
            Model identifier string.
        """
        task_type = task.get("type", TaskType.DEFAULT)
        complexity = task.get("complexity", "medium")
        urgency = task.get("urgency", "normal")
        preferred = task.get("preferred_model")

        # Use preferred model if specified and enabled
        if preferred and preferred in self.models:
            if self.models[preferred].enabled:
                return preferred
            logger.warning("preferred_model_disabled", model=preferred)

        # Get routing rule for task type
        rule = self.routes.get(task_type, self.routes[TaskType.DEFAULT])

        # Determine model based on budget status.
        # CostFuse is the single source of truth for budget state;
        # pre_call_check() auto-updates its internal tracker with the
        # latest cumulative costs, so we read the live status from it.
        cost_fuse = CostFuse()  # uses singleton CostTracker
        allowed, fuse_status, degraded_model = cost_fuse.pre_call_check(study_id=None)
        budget_status = BudgetStatus(fuse_status.lower())

        if budget_status == BudgetStatus.EMERGENCY:
            logger.error("budget_emergency_all_calls_blocked")
            raise RuntimeError(
                "Budget emergency: All LLM calls are blocked. "
                f"Current cost: ¥{self._current_daily_cost}, "
                f"Budget: ¥{self._daily_budget}"
            )

        if budget_status == BudgetStatus.FUSE:
            logger.error("budget_fuse_all_calls_blocked")
            raise RuntimeError("Budget fuse triggered: All LLM calls are paused.")

        if budget_status == BudgetStatus.DEGRADE:
            # Use CostFuse-recommended degraded model if available
            model = degraded_model or rule.degrade_model or self._degrade_model
            if model and model in self.models and self.models[model].enabled:
                logger.info(
                    "model_degraded",
                    task_type=task_type,
                    original=rule.default_model,
                    degraded=model,
                    reason="budget_degrade",
                )
                return model
            # If degrade model unavailable, try fallback
            model = rule.fallback_model
            if model and model in self.models and self.models[model].enabled:
                return model
            # Last resort: return default even if over budget
            logger.warning("degrade_model_unavailable_using_default")
            return rule.default_model

        if budget_status == BudgetStatus.WARNING and (complexity == "low" or urgency == "low"):
            # For non-critical tasks, use degrade model
            model = rule.degrade_model or self._degrade_model
            if model and model in self.models and self.models[model].enabled:
                logger.info(
                    "model_degraded_for_low_priority",
                    task_type=task_type,
                    original=rule.default_model,
                    degraded=model,
                )
                return model

        # Normal routing: use default model
        model = rule.default_model
        if model in self.models and self.models[model].enabled:
            return model

        # Fallback chain
        for fallback in [rule.degrade_model, rule.fallback_model, "gpt-4o-mini"]:
            if fallback and fallback in self.models and self.models[fallback].enabled:
                logger.warning(
                    "model_fallback",
                    original=model,
                    fallback=fallback,
                    reason="default_unavailable",
                )
                return fallback

        raise RuntimeError(f"No available model for task type: {task_type}")

    def record_failure(self, model: str) -> None:
        """Record a model failure for failover tracking.

        Args:
            model: The model that failed.
        """
        if model in self.models:
            self.models[model].failure_count += 1
            self.models[model].last_failure = time.time()
            logger.warning(
                "model_failure_recorded",
                model=model,
                failure_count=self.models[model].failure_count,
            )

            # Disable model if too many failures
            if self.models[model].failure_count >= 10:
                self.models[model].enabled = False
                logger.error("model_disabled_due_to_failures", model=model)

    def get_model_info(self, model: str | None = None) -> dict[str, Any]:
        """Get information about a model or all models.

        Args:
            model: Optional specific model name.

        Returns:
            Model configuration dictionary.
        """
        if model:
            cfg = self.models.get(model)
            if not cfg:
                return {}
            return {
                "name": model,
                "provider": cfg.provider,
                "input_cost_per_1k": cfg.input_cost_per_1k,
                "output_cost_per_1k": cfg.output_cost_per_1k,
                "max_tokens": cfg.max_tokens,
                "quality_tier": cfg.quality_tier,
                "enabled": cfg.enabled,
                "failure_count": cfg.failure_count,
            }

        return {
            name: {
                "provider": cfg.provider,
                "input_cost_per_1k": cfg.input_cost_per_1k,
                "output_cost_per_1k": cfg.output_cost_per_1k,
                "max_tokens": cfg.max_tokens,
                "quality_tier": cfg.quality_tier,
                "enabled": cfg.enabled,
            }
            for name, cfg in self.models.items()
        }

    def switch_model(self, new_model: str, reason: str) -> None:
        """Manually switch the default model for a task type.

        Args:
            new_model: New default model identifier.
            reason: Reason for the switch (logged for audit).
        """
        if new_model not in self.models:
            raise ValueError(f"Unknown model: {new_model}")

        old_defaults = {task: rule.default_model for task, rule in self.routes.items()}

        # Update all routes to use new model as default
        for rule in self.routes.values():
            rule.default_model = new_model

        logger.info(
            "model_switched",
            new_model=new_model,
            reason=reason,
            old_defaults=old_defaults,
        )

    def get_routing_summary(self) -> dict[str, Any]:
        """Get current routing configuration summary."""
        return {
            "budget_status": self._current_budget_status.value,
            "current_daily_cost": self._current_daily_cost,
            "daily_budget": self._daily_budget,
            "budget_ratio": (
                self._current_daily_cost / self._daily_budget if self._daily_budget > 0 else 0
            ),
            "models": self.get_model_info(),
            "routes": {
                task: {
                    "default": rule.default_model,
                    "degrade": rule.degrade_model,
                    "fallback": rule.fallback_model,
                }
                for task, rule in self.routes.items()
            },
        }
