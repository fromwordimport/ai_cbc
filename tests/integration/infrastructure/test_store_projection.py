"""Tests for MongoDB projection helpers."""

import pytest

from aicbc.core.models.db_documents import AnalysisJobDocument, PersonaDocument
from aicbc.core.store_mongo import MongoAnalysisStore, MongoPersonaStore


@pytest.mark.asyncio
async def test_alist_all_lightweight_excludes_data(clean_db):
    # Insert a lightweight persona doc directly
    await PersonaDocument(
        persona_id="persona-test-001",
        fingerprint="fp1",
        segment="premium",
        city="tier1",
        bias_audit_status="passed",
        status="active",
        data={"layer1": {"city": "tier1"}},
    ).insert()

    store = MongoPersonaStore()
    docs, total = await store.alist_all_lightweight(page_size=5)
    assert total == 1
    for doc in docs:
        assert "persona_id" in doc
        assert "segment" in doc
        assert "city" in doc
        assert "bias_audit_status" in doc
        assert "status" in doc
        assert "created_at" in doc
        assert "data" not in doc


@pytest.mark.asyncio
async def test_alist_jobs_by_study_lightweight(clean_db):
    # Insert an analysis job directly
    await AnalysisJobDocument(
        analysis_id="analysis-test-001",
        study_id="study-test-001",
        status="PENDING",
        data={"progress": 0},
    ).insert()

    store = MongoAnalysisStore()
    docs = await store.alist_jobs_by_study_lightweight("study-test-001")
    assert len(docs) == 1
    doc = docs[0]
    assert "analysis_id" in doc
    assert "study_id" in doc
    assert "status" in doc
    assert "created_at" in doc
    assert "data" not in doc
    assert "result_data" not in doc

    # Nonexistent study returns empty list
    docs_empty = await store.alist_jobs_by_study_lightweight("nonexistent-study")
    assert docs_empty == []
