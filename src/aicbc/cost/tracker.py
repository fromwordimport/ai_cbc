"""Global cost tracker with per-study, daily, and weekly accounting.

Thread-safe singleton that aggregates LLM call costs across all
subsystems and exposes real-time fuse-status checks.

State is persisted to ``./data/cost_state.json`` (default) or Redis
when ``COST_TRACKER_BACKEND=redis`` is set, so that budget
accumulation survives process restarts.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog

from aicbc.config.settings import CostFuseSettings, get_settings

logger = structlog.get_logger("aicbc.cost")

_USD_TO_CNY = 7.2

# Persistent state file path (fallback)
_STATE_FILE = Path("./data/cost_state.json")

# Redis key for cost state
_REDIS_KEY = "aicbc:cost:state"
# TTL: 7 days
_REDIS_TTL = 604800


class FuseStatus(StrEnum):
    """Current fuse status derived from cost consumption."""

    NORMAL = "NORMAL"  # < 80%  of any budget
    WARNING = "WARNING"  # >= 80% of any budget
    DEGRADE = "DEGRADE"  # >= 95% of any budget
    FUSE = "FUSE"  # >= 100% of any budget
    EMERGENCY = "EMERGENCY"  # >= 120% of any budget


@dataclass
class CostRecord:
    """A single LLM call cost record."""

    timestamp: datetime
    study_id: str | None
    persona_id: str | None
    task_phase: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cost_cny: float
    cached: bool = False
    degraded: bool = False


@dataclass
class CostSummary:
    """Aggregated cost summary for a dimension."""

    total_cny: float = 0.0
    total_calls: int = 0
    total_tokens: int = 0
    records: list[CostRecord] = field(default_factory=list)


class CostTracker:
    """Thread-safe global cost tracker.

    Tracks costs along three dimensions:
    - **per_study**: keyed by ``study_id``
    - **daily**: keyed by ``YYYY-MM-DD``
    - **weekly**: keyed by ``YYYY-Www`` (ISO calendar week)

    Also maintains a global cumulative total for emergency checks.
    """

    def __init__(self, settings: CostFuseSettings | None = None) -> None:
        self._settings = settings or get_settings().cost_fuse
        self._tracker_settings = get_settings().cost_tracker
        self._backend = self._tracker_settings.backend
        self._lock = threading.Lock()

        # Dimension buckets
        self._per_study: dict[str, CostSummary] = {}
        self._daily: dict[str, CostSummary] = {}
        self._weekly: dict[str, CostSummary] = {}
        self._monthly: dict[str, CostSummary] = {}

        # Global cumulative (for emergency threshold)
        self._global_total_cny: float = 0.0

        # Notification deduplication
        self._last_notified_status: FuseStatus | None = None

        # Budget reset tracking
        self._last_reset_date: str = datetime.now(UTC).strftime("%Y-%m-%d")

        # Write throttling: avoid I/O on every record() call
        self._dirty: bool = False
        self._last_save_time: float = 0.0

        # Lazy Redis client (only instantiated when backend is redis)
        self._redis: Any | None = None

        # Load persisted state on init
        self._load_state()

    # ------------------------------------------------------------------
    # Redis client (lazy singleton)
    # ------------------------------------------------------------------

    def _get_redis(self) -> Any:
        """Return a sync Redis client, creating it lazily once."""
        if self._redis is None:
            import redis as redis_lib

            redis_url = get_settings().database.redis_url
            self._redis = redis_lib.Redis.from_url(redis_url, decode_responses=True)
        return self._redis

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        cost_usd: float,
        study_id: str | None = None,
        persona_id: str | None = None,
        task_phase: str = "unknown",
        provider: str = "unknown",
        model: str = "unknown",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached: bool = False,
        degraded: bool = False,
    ) -> CostRecord:
        """Record a single LLM call cost.

        Returns the created record for downstream use.
        """
        cost_cny = cost_usd * _USD_TO_CNY
        now = datetime.now(UTC)
        record = CostRecord(
            timestamp=now,
            study_id=study_id,
            persona_id=persona_id,
            task_phase=task_phase,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            cost_cny=cost_cny,
            cached=cached,
            degraded=degraded,
        )

        day_key = now.strftime("%Y-%m-%d")
        week_key = now.strftime("%Y-W%W")
        month_key = now.strftime("%Y-%m")

        with self._lock:
            self._global_total_cny += cost_cny

            # per-study
            if study_id:
                summary = self._per_study.setdefault(study_id, CostSummary())
                summary.total_cny += cost_cny
                summary.total_calls += 1
                summary.total_tokens += prompt_tokens + completion_tokens
                summary.records.append(record)

            # daily
            day_summary = self._daily.setdefault(day_key, CostSummary())
            day_summary.total_cny += cost_cny
            day_summary.total_calls += 1
            day_summary.total_tokens += prompt_tokens + completion_tokens
            day_summary.records.append(record)

            # weekly
            week_summary = self._weekly.setdefault(week_key, CostSummary())
            week_summary.total_cny += cost_cny
            week_summary.total_calls += 1
            week_summary.total_tokens += prompt_tokens + completion_tokens
            week_summary.records.append(record)

            # monthly
            month_summary = self._monthly.setdefault(month_key, CostSummary())
            month_summary.total_cny += cost_cny
            month_summary.total_calls += 1
            month_summary.total_tokens += prompt_tokens + completion_tokens
            month_summary.records.append(record)

        log = logger.bind(
            study_id=study_id,
            persona_id=persona_id,
            task_phase=task_phase,
            cost_cny=round(cost_cny, 6),
            model=model,
        )
        log.info("cost_recorded")
        self._dirty = True
        self._maybe_save()
        return record

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _serialize_state(self) -> dict[str, Any]:
        """Build a JSON-serializable state dict from in-memory buckets."""
        return {
            "per_study": {
                k: {
                    "total_cny": v.total_cny,
                    "total_calls": v.total_calls,
                    "total_tokens": v.total_tokens,
                }
                for k, v in self._per_study.items()
            },
            "daily": {
                k: {
                    "total_cny": v.total_cny,
                    "total_calls": v.total_calls,
                    "total_tokens": v.total_tokens,
                }
                for k, v in self._daily.items()
            },
            "weekly": {
                k: {
                    "total_cny": v.total_cny,
                    "total_calls": v.total_calls,
                    "total_tokens": v.total_tokens,
                }
                for k, v in self._weekly.items()
            },
            "monthly": {
                k: {
                    "total_cny": v.total_cny,
                    "total_calls": v.total_calls,
                    "total_tokens": v.total_tokens,
                }
                for k, v in self._monthly.items()
            },
            "global_total_cny": self._global_total_cny,
            "last_reset_date": self._last_reset_date,
            "saved_at": datetime.now(UTC).isoformat(),
        }

    def _deserialize_state(self, state: dict[str, Any]) -> None:
        """Populate in-memory buckets from a JSON state dict."""
        for k, v in state.get("per_study", {}).items():
            self._per_study[k] = CostSummary(
                total_cny=v.get("total_cny", 0.0),
                total_calls=v.get("total_calls", 0),
                total_tokens=v.get("total_tokens", 0),
            )
        for k, v in state.get("daily", {}).items():
            self._daily[k] = CostSummary(
                total_cny=v.get("total_cny", 0.0),
                total_calls=v.get("total_calls", 0),
                total_tokens=v.get("total_tokens", 0),
            )
        for k, v in state.get("weekly", {}).items():
            self._weekly[k] = CostSummary(
                total_cny=v.get("total_cny", 0.0),
                total_calls=v.get("total_calls", 0),
                total_tokens=v.get("total_tokens", 0),
            )
        for k, v in state.get("monthly", {}).items():
            self._monthly[k] = CostSummary(
                total_cny=v.get("total_cny", 0.0),
                total_calls=v.get("total_calls", 0),
                total_tokens=v.get("total_tokens", 0),
            )
        self._global_total_cny = state.get("global_total_cny", 0.0)
        self._last_reset_date = state.get("last_reset_date", datetime.now(UTC).strftime("%Y-%m-%d"))

    def _save_state(self) -> None:
        """Persist current cost state to the configured backend."""
        if self._backend == "redis":
            self._save_state_redis()
        else:
            self._save_state_file()

    def _save_state_file(self) -> None:
        """Persist current cost state to disk."""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = self._serialize_state()
            with open(_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("cost_state_save_failed", error=str(exc))

    def _save_state_redis(self) -> None:
        """Persist current cost state to Redis with TTL."""
        try:
            r = self._get_redis()
            state = self._serialize_state()
            r.setex(
                self._tracker_settings.redis_key,
                self._tracker_settings.redis_ttl,
                json.dumps(state, ensure_ascii=False),
            )
        except Exception as exc:
            logger.warning("cost_state_save_redis_failed", error=str(exc))

    def _maybe_save(self) -> None:
        """Throttled save: persist only if dirty and 30+ seconds since last write."""
        import time

        now = time.time()
        if self._dirty and (now - self._last_save_time >= 30.0):
            self._save_state()
            self._dirty = False
            self._last_save_time = now

    def _load_state(self) -> None:
        """Load persisted cost state from the configured backend."""
        if self._backend == "redis":
            self._load_state_redis()
        else:
            self._load_state_file()

    def _load_state_file(self) -> None:
        """Load persisted cost state from disk."""
        if not _STATE_FILE.exists():
            return
        try:
            with open(_STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)
            self._deserialize_state(state)
            logger.info("cost_state_loaded", file=str(_STATE_FILE))
        except Exception as exc:
            logger.warning("cost_state_load_failed", error=str(exc))

    def _load_state_redis(self) -> None:
        """Load persisted cost state from Redis."""
        try:
            r = self._get_redis()
            raw = r.get(self._tracker_settings.redis_key)
            if raw is None:
                return
            state = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode("utf-8"))
            self._deserialize_state(state)
            logger.info("cost_state_loaded", backend="redis", key=self._tracker_settings.redis_key)
        except Exception as exc:
            logger.warning("cost_state_load_redis_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Auto-reset
    # ------------------------------------------------------------------

    def _maybe_reset_budgets(self) -> None:
        """Automatically reset daily/weekly/monthly budgets when boundaries cross."""
        now = datetime.now(UTC)
        today_str = now.strftime("%Y-%m-%d")
        current_week = now.strftime("%Y-W%W")
        current_month = now.strftime("%Y-%m")

        with self._lock:
            last_reset = datetime.strptime(self._last_reset_date, "%Y-%m-%d").replace(tzinfo=UTC)

            # Daily reset: if last reset was not today
            if today_str != self._last_reset_date:
                self._daily.clear()
                logger.info("cost_budget_reset_daily", date=today_str)

            # Weekly reset: if week changed
            last_week = last_reset.strftime("%Y-W%W")
            if current_week != last_week:
                self._weekly.clear()
                logger.info("cost_budget_reset_weekly", week=current_week)

            # Monthly reset: if month changed
            last_month = last_reset.strftime("%Y-%m")
            if current_month != last_month:
                self._monthly.clear()
                logger.info("cost_budget_reset_monthly", month=current_month)

            self._last_reset_date = today_str
            self._save_state()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_study_cost(self, study_id: str) -> float:
        """Return total CNY cost for a study."""
        with self._lock:
            return self._per_study.get(study_id, CostSummary()).total_cny

    def get_daily_cost(self, date: str | None = None) -> float:
        """Return total CNY cost for a day (YYYY-MM-DD). Defaults to today."""
        day_key = date or datetime.now(UTC).strftime("%Y-%m-%d")
        with self._lock:
            return self._daily.get(day_key, CostSummary()).total_cny

    def get_weekly_cost(self, week: str | None = None) -> float:
        """Return total CNY cost for a week (YYYY-Www). Defaults to current week."""
        week_key = week or datetime.now(UTC).strftime("%Y-W%W")
        with self._lock:
            return self._weekly.get(week_key, CostSummary()).total_cny

    def get_monthly_cost(self, month: str | None = None) -> float:
        """Return total CNY cost for a month (YYYY-MM). Defaults to current month."""
        month_key = month or datetime.now(UTC).strftime("%Y-%m")
        with self._lock:
            return self._monthly.get(month_key, CostSummary()).total_cny

    def get_study_summary(self, study_id: str) -> CostSummary:
        """Return full cost summary for a study."""
        with self._lock:
            return self._per_study.get(study_id, CostSummary())

    def get_global_total(self) -> float:
        """Return global cumulative cost in CNY."""
        with self._lock:
            return self._global_total_cny

    # ------------------------------------------------------------------
    # Fuse status
    # ------------------------------------------------------------------

    def check_fuse_status(
        self,
        study_id: str | None = None,
    ) -> tuple[FuseStatus, dict[str, Any]]:
        """Check current fuse status across all relevant dimensions.

        Returns the **most severe** status and a detail dict with
        consumption ratios per dimension.
        """
        # P0-003: Auto-reset budgets before checking
        self._maybe_reset_budgets()

        settings = self._settings
        now = datetime.now(UTC)
        day_key = now.strftime("%Y-%m-%d")
        week_key = now.strftime("%Y-W%W")
        month_key = now.strftime("%Y-%m")

        with self._lock:
            study_cost = (
                self._per_study.get(study_id or "", CostSummary()).total_cny if study_id else 0.0
            )
            daily_cost = self._daily.get(day_key, CostSummary()).total_cny
            weekly_cost = self._weekly.get(week_key, CostSummary()).total_cny
            monthly_cost = self._monthly.get(month_key, CostSummary()).total_cny
            global_total = self._global_total_cny

        # Compute ratios
        ratios: dict[str, float] = {}
        if study_id:
            ratios["study"] = study_cost / max(settings.single_study_cny, 0.01)
        ratios["daily"] = daily_cost / max(settings.daily_cny, 0.01)
        ratios["weekly"] = weekly_cost / max(settings.weekly_cny, 0.01)
        ratios["monthly"] = monthly_cost / max(settings.monthly_cny, 0.01)

        # Determine most severe status
        max_ratio = max(ratios.values())
        if max_ratio >= 1.20:
            status = FuseStatus.EMERGENCY
        elif max_ratio >= 1.00:
            status = FuseStatus.FUSE
        elif max_ratio >= 0.95:
            status = FuseStatus.DEGRADE
        elif max_ratio >= 0.80:
            status = FuseStatus.WARNING
        else:
            status = FuseStatus.NORMAL

        details = {
            "status": status.value,
            "ratios": {k: round(v, 4) for k, v in ratios.items()},
            "costs_cny": {
                "study": round(study_cost, 4),
                "daily": round(daily_cost, 4),
                "weekly": round(weekly_cost, 4),
                "monthly": round(monthly_cost, 4),
                "global": round(global_total, 4),
            },
            "thresholds": {
                "single_study": settings.single_study_cny,
                "daily": settings.daily_cny,
                "weekly": settings.weekly_cny,
                "monthly": settings.monthly_cny,
            },
        }
        return status, details

    def should_allow_call(
        self, study_id: str | None = None
    ) -> tuple[bool, FuseStatus, dict[str, Any]]:
        """Convenience wrapper: return (allowed, status, details).

        Calls are **blocked** only at FUSE or EMERGENCY level.
        DEGRADE level still allows calls but signals model downgrade.
        """
        status, details = self.check_fuse_status(study_id)
        allowed = status not in (FuseStatus.FUSE, FuseStatus.EMERGENCY)
        return allowed, status, details

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def notify_if_changed(self, status: FuseStatus, details: dict[str, Any]) -> bool:
        """Emit a notification log if the fuse status has changed.

        Returns True if a notification was emitted.
        """
        if self._last_notified_status == status:
            return False

        self._last_notified_status = status
        log = logger.bind(**details)

        if status == FuseStatus.WARNING:
            log.warning("cost_fuse_warning", message="费用达预算80%，请留意")
        elif status == FuseStatus.DEGRADE:
            log.warning("cost_fuse_degrade", message="费用达预算95%，自动降级模型")
        elif status == FuseStatus.FUSE:
            log.error("cost_fuse_triggered", message="费用达预算100%，暂停新任务")
        elif status == FuseStatus.EMERGENCY:
            log.error("cost_fuse_emergency", message="费用达预算120%，锁定所有LLM调用")
        else:
            log.info("cost_fuse_normal", message="费用正常")

        return True

    # ------------------------------------------------------------------
    # Reset (testing / admin)
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all tracked data and remove persisted state. Useful in tests."""
        # Force save any pending dirty state before resetting
        self._save_state()
        self._dirty = False
        self._last_save_time = 0.0

        with self._lock:
            self._per_study.clear()
            self._daily.clear()
            self._weekly.clear()
            self._monthly.clear()
            self._global_total_cny = 0.0
            self._last_notified_status = None
            self._last_reset_date = datetime.now(UTC).strftime("%Y-%m-%d")

        # Remove persisted state from whichever backend is active
        if self._backend == "redis":
            try:
                r = self._get_redis()
                r.delete(self._tracker_settings.redis_key)
            except Exception as exc:
                logger.warning("cost_state_redis_remove_failed", error=str(exc))
        else:
            try:
                if _STATE_FILE.exists():
                    _STATE_FILE.unlink()
            except Exception as exc:
                logger.warning("cost_state_file_remove_failed", error=str(exc))


# Module-level singleton
_cost_tracker: CostTracker | None = None


def get_cost_tracker() -> CostTracker:
    """Return the global CostTracker singleton."""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker()
    return _cost_tracker


def reset_cost_tracker() -> None:
    """Reset the global CostTracker singleton and delete persisted state.

    Useful for tests to prevent state leakage between test files or runs.
    """
    global _cost_tracker
    tracker = get_cost_tracker()
    tracker.reset()
    _cost_tracker = None
