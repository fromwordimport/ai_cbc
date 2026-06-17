"""Pluggable store for analysis jobs and results.

Defaults to MongoDB in production/staging and keeps an in-memory fallback for
local development and tests.
"""

from __future__ import annotations

import asyncio
import os
import threading
from datetime import UTC, datetime
from typing import Any

from aicbc.analysis.models import (
    AnalysisJobStatus,
    AnalysisResultResponse,
    ConvergenceDiagnostics,
    ImportanceResponse,
    MarketSimResponse,
    SegmentComparisonResponse,
    WTPResponse,
)


def _use_memory_store() -> bool:
    """Return True if the environment requests the in-memory store."""
    env = os.environ.get("USE_MEMORY_STORE", "").lower()
    if env in ("1", "true", "yes"):
        return True
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment in ("development", "dev", "testing", "test"):
        mongo_url = os.environ.get("MONGODB_URL", "")
        if not mongo_url or mongo_url == "mongodb://localhost:27017":
            return True
    return False


def _get_mongo_stores() -> Any:
    from aicbc.core import store_mongo

    return store_mongo


class MemoryAnalysisStore:
    """Thread-safe in-memory store for analysis jobs and computed results."""

    def __init__(self) -> None:
        self._jobs: dict[str, AnalysisJobStatus] = {}
        self._results: dict[str, AnalysisResultResponse] = {}
        self._convergence: dict[str, ConvergenceDiagnostics] = {}
        self._importance: dict[str, ImportanceResponse] = {}
        self._wtp: dict[str, WTPResponse] = {}
        self._market_sim: dict[str, MarketSimResponse] = {}
        self._segment_comparison: dict[str, SegmentComparisonResponse] = {}
        self._latent_class: dict[str, Any] = {}
        self._lock = threading.Lock()

    def save_job(self, job: AnalysisJobStatus) -> None:
        """Store a job status (upsert)."""
        with self._lock:
            self._jobs[job.analysis_id] = job

    async def asave_job(self, job: AnalysisJobStatus) -> None:
        """Async-compatible save_job (delegates to sync implementation)."""
        self.save_job(job)

    def get_job(self, analysis_id: str) -> AnalysisJobStatus | None:
        """Retrieve a job by analysis_id."""
        with self._lock:
            return self._jobs.get(analysis_id)

    async def aget_job(self, analysis_id: str) -> AnalysisJobStatus | None:
        """Async-compatible get_job (delegates to sync implementation)."""
        return self.get_job(analysis_id)

    _VALID_TRANSITIONS: dict[str, set[str]] = {
        "PENDING": {"QUEUED", "CANCELLED"},
        "QUEUED": {"RUNNING", "CANCELLED"},
        "RUNNING": {"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"},
        "COMPLETED": set(),
        "FAILED": set(),
        "CANCELLED": set(),
        "TIMED_OUT": set(),
    }

    def update_job_status(
        self,
        analysis_id: str,
        status: str,
        progress: float | None = None,
    ) -> AnalysisJobStatus | None:
        """Update job status and optionally progress."""
        with self._lock:
            job = self._jobs.get(analysis_id)
            if job is None:
                return None
            allowed = self._VALID_TRANSITIONS.get(job.status, set())
            if allowed and status not in allowed:
                import structlog

                log = structlog.get_logger("aicbc.analysis")
                log.warning(
                    "illegal_state_transition",
                    analysis_id=analysis_id,
                    current=job.status,
                    attempted=status,
                )
                return job
            job.status = status
            if status == "RUNNING" and job.started_at is None:
                job.started_at = datetime.now(UTC)
            if status == "COMPLETED":
                job.completed_at = datetime.now(UTC)
            if progress is not None:
                job.progress_percent = progress
            return job

    async def aupdate_job_status(
        self,
        analysis_id: str,
        status: str,
        progress: float | None = None,
    ) -> AnalysisJobStatus | None:
        """Async-compatible update_job_status (delegates to sync implementation)."""
        return self.update_job_status(analysis_id, status, progress)

    def save_result(self, result: AnalysisResultResponse) -> None:
        """Store a complete analysis result."""
        with self._lock:
            self._results[result.analysis_id] = result

    async def asave_result(self, result: AnalysisResultResponse) -> None:
        """Async-compatible save_result (delegates to sync implementation)."""
        self.save_result(result)

    def get_result(self, analysis_id: str) -> AnalysisResultResponse | None:
        """Retrieve a complete analysis result."""
        with self._lock:
            return self._results.get(analysis_id)

    async def aget_result(self, analysis_id: str) -> AnalysisResultResponse | None:
        """Async-compatible get_result (delegates to sync implementation)."""
        return self.get_result(analysis_id)

    def save_convergence(self, analysis_id: str, diag: ConvergenceDiagnostics) -> None:
        """Store convergence diagnostics."""
        with self._lock:
            self._convergence[analysis_id] = diag

    async def asave_convergence(self, analysis_id: str, diag: ConvergenceDiagnostics) -> None:
        """Async-compatible save_convergence (delegates to sync implementation)."""
        self.save_convergence(analysis_id, diag)

    def get_convergence(self, analysis_id: str) -> ConvergenceDiagnostics | None:
        """Retrieve convergence diagnostics."""
        with self._lock:
            return self._convergence.get(analysis_id)

    async def aget_convergence(self, analysis_id: str) -> ConvergenceDiagnostics | None:
        """Async-compatible get_convergence (delegates to sync implementation)."""
        return self.get_convergence(analysis_id)

    def save_importance(self, analysis_id: str, importance: ImportanceResponse) -> None:
        """Store attribute importance results."""
        with self._lock:
            self._importance[analysis_id] = importance

    async def asave_importance(self, analysis_id: str, importance: ImportanceResponse) -> None:
        """Async-compatible save_importance (delegates to sync implementation)."""
        self.save_importance(analysis_id, importance)

    def get_importance(self, analysis_id: str) -> ImportanceResponse | None:
        """Retrieve attribute importance results."""
        with self._lock:
            return self._importance.get(analysis_id)

    async def aget_importance(self, analysis_id: str) -> ImportanceResponse | None:
        """Async-compatible get_importance (delegates to sync implementation)."""
        return self.get_importance(analysis_id)

    def save_wtp(self, analysis_id: str, wtp: WTPResponse) -> None:
        """Store WTP results."""
        with self._lock:
            self._wtp[analysis_id] = wtp

    async def asave_wtp(self, analysis_id: str, wtp: WTPResponse) -> None:
        """Async-compatible save_wtp (delegates to sync implementation)."""
        self.save_wtp(analysis_id, wtp)

    def get_wtp(self, analysis_id: str) -> WTPResponse | None:
        """Retrieve WTP results."""
        with self._lock:
            return self._wtp.get(analysis_id)

    async def aget_wtp(self, analysis_id: str) -> WTPResponse | None:
        """Async-compatible get_wtp (delegates to sync implementation)."""
        return self.get_wtp(analysis_id)

    def save_market_sim(self, analysis_id: str, sim_id: str, result: MarketSimResponse) -> None:
        """Store market simulation result keyed by analysis_id + sim_id."""
        with self._lock:
            self._market_sim[f"{analysis_id}:{sim_id}"] = result

    async def asave_market_sim(
        self, analysis_id: str, sim_id: str, result: MarketSimResponse
    ) -> None:
        """Async-compatible save_market_sim (delegates to sync implementation)."""
        self.save_market_sim(analysis_id, sim_id, result)

    def get_market_sim(self, analysis_id: str, sim_id: str) -> MarketSimResponse | None:
        """Retrieve market simulation result."""
        with self._lock:
            return self._market_sim.get(f"{analysis_id}:{sim_id}")

    async def aget_market_sim(self, analysis_id: str, sim_id: str) -> MarketSimResponse | None:
        """Async-compatible get_market_sim (delegates to sync implementation)."""
        return self.get_market_sim(analysis_id, sim_id)

    def save_segment_comparison(
        self,
        analysis_id: str,
        segment_a: str,
        segment_b: str,
        result: SegmentComparisonResponse,
    ) -> None:
        """Store segment comparison result."""
        key = f"{analysis_id}:{segment_a}:{segment_b}"
        with self._lock:
            self._segment_comparison[key] = result

    async def asave_segment_comparison(
        self,
        analysis_id: str,
        segment_a: str,
        segment_b: str,
        result: SegmentComparisonResponse,
    ) -> None:
        """Async-compatible save_segment_comparison (delegates to sync implementation)."""
        self.save_segment_comparison(analysis_id, segment_a, segment_b, result)

    def get_segment_comparison(
        self,
        analysis_id: str,
        segment_a: str | None = None,
        segment_b: str | None = None,
    ) -> SegmentComparisonResponse | None:
        """Retrieve segment comparison result."""
        with self._lock:
            if segment_a is not None and segment_b is not None:
                key = f"{analysis_id}:{segment_a}:{segment_b}"
                return self._segment_comparison.get(key)
            for key, result in self._segment_comparison.items():
                if key.startswith(f"{analysis_id}:"):
                    return result
            return None

    async def aget_segment_comparison(
        self,
        analysis_id: str,
        segment_a: str | None = None,
        segment_b: str | None = None,
    ) -> SegmentComparisonResponse | None:
        """Async-compatible get_segment_comparison (delegates to sync implementation)."""
        return self.get_segment_comparison(analysis_id, segment_a, segment_b)

    def get_latest_market_sim(self, analysis_id: str) -> MarketSimResponse | None:
        """Return the most recent market simulation for an analysis."""
        with self._lock:
            key = None
            for k in self._market_sim:
                if k.startswith(f"{analysis_id}:") and (key is None or k > key):
                    key = k
            return self._market_sim.get(key) if key else None

    async def aget_latest_market_sim(self, analysis_id: str) -> MarketSimResponse | None:
        """Async-compatible get_latest_market_sim (delegates to sync implementation)."""
        return self.get_latest_market_sim(analysis_id)

    def save_latent_class_result(self, analysis_id: str, result: dict[str, Any]) -> None:
        """Store a latent class model result."""
        with self._lock:
            self._latent_class[analysis_id] = result

    async def asave_latent_class_result(self, analysis_id: str, result: dict[str, Any]) -> None:
        """Async-compatible save_latent_class_result (delegates to sync implementation)."""
        self.save_latent_class_result(analysis_id, result)

    def get_latent_class_result(self, analysis_id: str) -> dict[str, Any] | None:
        """Retrieve a latent class model result."""
        with self._lock:
            return self._latent_class.get(analysis_id)

    async def aget_latent_class_result(self, analysis_id: str) -> dict[str, Any] | None:
        """Async-compatible get_latent_class_result (delegates to sync implementation)."""
        return self.get_latent_class_result(analysis_id)

    def delete_by_study(self, study_id: str) -> int:
        """Delete all analyses belonging to a study."""
        with self._lock:
            analysis_ids = [aid for aid, job in self._jobs.items() if job.study_id == study_id]
            for aid in analysis_ids:
                self._delete_analysis_unlocked(aid)
            return len(analysis_ids)

    async def adelete_by_study(self, study_id: str) -> int:
        """Async-compatible delete_by_study (delegates to sync implementation)."""
        return self.delete_by_study(study_id)

    def list_jobs_by_study(self, study_id: str) -> list[AnalysisJobStatus]:
        """Return all analysis jobs belonging to a study."""
        with self._lock:
            return [job for job in self._jobs.values() if job.study_id == study_id]

    async def alist_jobs_by_study(self, study_id: str) -> list[AnalysisJobStatus]:
        """Async-compatible list_jobs_by_study (delegates to sync implementation)."""
        return self.list_jobs_by_study(study_id)

    def clear(self) -> None:
        """Clear all stored analysis data."""
        with self._lock:
            self._jobs.clear()
            self._results.clear()
            self._convergence.clear()
            self._importance.clear()
            self._wtp.clear()
            self._market_sim.clear()
            self._segment_comparison.clear()
            self._latent_class.clear()

    async def aclear(self) -> None:
        """Async-compatible clear (delegates to sync implementation)."""
        self.clear()

    def delete_analysis(self, analysis_id: str) -> bool:
        """Delete a job, its result, and all derivative artefacts."""
        with self._lock:
            return self._delete_analysis_unlocked(analysis_id)

    async def adelete_analysis(self, analysis_id: str) -> bool:
        """Async-compatible delete_analysis (delegates to sync implementation)."""
        return self.delete_analysis(analysis_id)

    def _delete_analysis_unlocked(self, analysis_id: str) -> bool:
        """Delete analysis artefacts without acquiring the lock.

        Must only be called while ``self._lock`` is already held.
        """
        if analysis_id not in self._jobs:
            return False
        self._jobs.pop(analysis_id, None)
        self._results.pop(analysis_id, None)
        self._convergence.pop(analysis_id, None)
        self._importance.pop(analysis_id, None)
        self._wtp.pop(analysis_id, None)
        self._latent_class.pop(analysis_id, None)
        for key in list(self._market_sim.keys()):
            if key.startswith(f"{analysis_id}:"):
                self._market_sim.pop(key, None)
        for key in list(self._segment_comparison.keys()):
            if key.startswith(f"{analysis_id}:"):
                self._segment_comparison.pop(key, None)
        return True


# Alias for backward compatibility.
AnalysisStore = MemoryAnalysisStore


_analysis_store: AnalysisStore | None = None


def get_analysis_store() -> AnalysisStore:
    """Return the global AnalysisStore singleton."""
    global _analysis_store
    if _analysis_store is None:
        if _use_memory_store():
            _analysis_store = MemoryAnalysisStore()
        else:
            _analysis_store = _get_mongo_stores().MongoAnalysisStore()
    return _analysis_store


def reset_analysis_store() -> None:
    """Reset the global AnalysisStore singleton.

    When called from an async context, callers should use
    :func:`areset_analysis_store` instead.  This sync wrapper dispatches to
    ``aclear()`` for Mongo-backed stores and ``clear()`` for memory stores,
    using ``asyncio.run`` only when no event loop is running.
    """
    global _analysis_store
    _analysis_store = None
    try:
        asyncio.get_running_loop()
        # Called from an async context — caller should use areset_analysis_store().
        get_analysis_store().clear()
    except RuntimeError:
        # No event loop running — safe to use asyncio.run for Mongo stores.
        asyncio.run(areset_analysis_store())
    _analysis_store = None


async def areset_analysis_store() -> None:
    """Async version of :func:`reset_analysis_store`.

    Awaits the store's ``aclear()`` so Mongo-backed stores are cleaned
    without blocking the event loop.
    """
    global _analysis_store
    _analysis_store = None
    await get_analysis_store().aclear()
    _analysis_store = None
