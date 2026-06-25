"""Tests for MongoDB projection helpers."""

import pytest

from aicbc.core.store_mongo import MongoAnalysisStore, MongoPersonaStore


@pytest.mark.asyncio
async def test_alist_all_lightweight_excludes_data(clean_db):
    store = MongoPersonaStore()
    docs, total = await store.alist_all_lightweight(page_size=5)
    assert total >= 0
    for doc in docs:
        assert "data" not in doc
        assert "persona_id" in doc


@pytest.mark.asyncio
async def test_alist_jobs_by_study_lightweight(clean_db):
    store = MongoAnalysisStore()
    docs = await store.alist_jobs_by_study_lightweight("nonexistent-study")
    assert docs == []
