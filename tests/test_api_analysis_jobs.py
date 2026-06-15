"""Tests for analysis job listing and deletion endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aicbc.analysis.models import AnalysisJobStatus
from aicbc.analysis.store import get_analysis_store, reset_analysis_store
from aicbc.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_analysis_store():
    """Reset the analysis store before and after each test."""
    reset_analysis_store()
    yield
    reset_analysis_store()


def _make_job(analysis_id: str, study_id: str) -> AnalysisJobStatus:
    return AnalysisJobStatus(
        analysis_id=analysis_id,
        study_id=study_id,
        status="QUEUED",
        model_type="hb",
        queued_at=datetime.now(UTC),
        estimated_duration_seconds=300,
        progress_percent=0.0,
    )


class TestListAnalyses:
    """Tests for GET /studies/{study_id}/analysis."""

    def test_list_analyses_empty(self) -> None:
        response = client.get("/api/v1/studies/s-001/analysis")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_analyses_with_jobs(self) -> None:
        store = get_analysis_store()
        store.save_job(_make_job("a-1", "s-001"))
        store.save_job(_make_job("a-2", "s-001"))
        store.save_job(_make_job("a-3", "s-002"))

        response = client.get("/api/v1/studies/s-001/analysis")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert {job["analysis_id"] for job in data} == {"a-1", "a-2"}


class TestDeleteAnalysis:
    """Tests for DELETE /studies/{study_id}/analysis/{analysis_id}."""

    def test_delete_analysis_success(self) -> None:
        store = get_analysis_store()
        store.save_job(_make_job("a-1", "s-001"))

        response = client.delete("/api/v1/studies/s-001/analysis/a-1")
        assert response.status_code == 204
        assert store.get_job("a-1") is None

    def test_delete_analysis_not_found(self) -> None:
        response = client.delete("/api/v1/studies/s-001/analysis/a-missing")
        assert response.status_code == 404

    def test_delete_analysis_wrong_study(self) -> None:
        store = get_analysis_store()
        store.save_job(_make_job("a-2", "s-002"))

        response = client.delete("/api/v1/studies/s-001/analysis/a-2")
        assert response.status_code == 404
        assert store.get_job("a-2") is not None
