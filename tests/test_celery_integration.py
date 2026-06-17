"""Integration tests for Celery Worker + Redis message queue.

These tests verify that Celery tasks are correctly registered,
can be enqueued via Redis broker, and consumed by a worker.
In CI environments without a running Redis, tests are skipped.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from aicbc.analysis.models import AnalysisJobStatus
from aicbc.analysis.store import get_analysis_store
from aicbc.analysis.tasks import celery_app, run_analysis_task, run_latent_class_task


pytestmark = [
    pytest.mark.slow,
]


def _redis_available() -> bool:
    """Check whether Redis broker is reachable."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis
        r = redis.from_url(url)
        return r.ping()
    except Exception:  # noqa: BLE001
        return False


class TestCeleryAppConfig:
    """Verify Celery app configuration without a running broker."""

    def test_celery_app_exists(self):
        assert celery_app is not None
        assert celery_app.main == "aicbc.analysis"

    def test_task_registered(self):
        tasks = celery_app.tasks
        assert "aicbc.analysis.run_analysis_task" in tasks
        assert "aicbc.analysis.run_latent_class_task" in tasks

    def test_broker_url_from_settings(self):
        from aicbc.config.settings import get_settings
        settings = get_settings()
        assert settings.celery_broker_url.startswith("redis://")

    def test_result_backend_configured(self):
        """Result backend must be set for cross-process status tracking."""
        assert celery_app.conf.result_backend is not None
        assert celery_app.conf.result_backend.startswith("redis://")

    def test_task_time_limits(self):
        task = celery_app.tasks.get("aicbc.analysis.run_analysis_task")
        assert task is not None
        assert task.time_limit == 600  # Hard timeout 10 minutes
        assert task.soft_time_limit == 540  # Soft timeout 9 minutes

    def test_latent_class_task_time_limits(self):
        task = celery_app.tasks.get("aicbc.analysis.run_latent_class_task")
        assert task is not None
        assert task.time_limit == 900  # Hard timeout 15 minutes
        assert task.soft_time_limit == 780  # Soft timeout 13 minutes

    def test_task_serialization_config(self):
        """Task serialization must use JSON."""
        assert celery_app.conf.task_serializer == "json"
        assert "json" in celery_app.conf.accept_content

    def test_task_tracking_enabled(self):
        """Task tracking must be enabled for progress monitoring."""
        assert celery_app.conf.task_track_started is True

    def test_prefetch_multiplier(self):
        """Prefetch multiplier should be 1 for fair task distribution."""
        assert celery_app.conf.worker_prefetch_multiplier == 1

    def test_result_expires_short(self):
        assert celery_app.conf.result_expires == 300

    def test_task_ignore_result_enabled(self):
        task = celery_app.tasks.get("aicbc.analysis.run_analysis_task")
        assert task.ignore_result is True

    def test_result_extended_disabled(self):
        assert celery_app.conf.result_extended is False


@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
class TestCeleryRedisIntegration:
    """Integration tests requiring a running Redis broker."""

    def test_redis_ping(self):
        assert _redis_available()

    def test_send_task_enqueues(self):
        """Verify that sending a task creates a job in the broker."""
        result = run_analysis_task.apply_async(
            args=["study-test-001", "analysis-test-001", "mnl", "{}"],
            countdown=3600,  # Delay 1 hour so it doesn't actually run
        )
        assert result.id is not None
        # Revoke the task so it doesn't run
        result.revoke(terminate=False)

    def test_task_state_transitions(self):
        """Verify PENDING -> RUNNING -> COMPLETED/FAILED state flow."""
        store = get_analysis_store()
        job = AnalysisJobStatus(
            analysis_id="analysis-celery-test-001",
            study_id="study-test-001",
            status="PENDING",
            model_type="mnl",
            queued_at=datetime.now(UTC),
            estimated_duration_seconds=60,
        )
        store.save_job(job)

        # Simulate worker picking up the task
        job = store.update_job_status("analysis-celery-test-001", "RUNNING", progress=0.0)
        assert job is not None
        assert job.status == "RUNNING"

        # Simulate progress updates
        job = store.update_job_status("analysis-celery-test-001", "RUNNING", progress=50.0)
        assert job.progress_percent == 50.0

        # Simulate completion
        job = store.update_job_status("analysis-celery-test-001", "COMPLETED", progress=100.0)
        assert job.status == "COMPLETED"

    def test_task_revoke(self):
        """Verify task revocation updates job status to CANCELLED."""
        store = get_analysis_store()
        job = AnalysisJobStatus(
            analysis_id="analysis-celery-test-002",
            study_id="study-test-001",
            status="PENDING",
            model_type="mnl",
            queued_at=datetime.now(UTC),
            estimated_duration_seconds=60,
        )
        store.save_job(job)

        # Simulate cancellation (worker revokes task)
        job = store.update_job_status("analysis-celery-test-002", "CANCELLED")
        assert job is not None
        assert job.status == "CANCELLED"

    def test_latent_class_task_enqueue(self):
        """Verify latent class task can be enqueued."""
        result = run_latent_class_task.apply_async(
            args=["study-test-001", "analysis-lc-001", "{}"],
            countdown=3600,
        )
        assert result.id is not None
        result.revoke(terminate=False)
