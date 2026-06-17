import pytest

from aicbc.core.models.db_documents import (
    ALL_DOCUMENT_MODELS,
    AnalysisJobDocument,
    AnalysisResultDocument,
)


def test_analysis_job_has_created_at_index():
    settings = AnalysisJobDocument.Settings
    index_fields = _extract_index_fields(settings)
    assert ("created_at", -1) in index_fields or "created_at" in index_fields


def test_analysis_result_has_created_at_index():
    settings = AnalysisResultDocument.Settings
    index_fields = _extract_index_fields(settings)
    assert ("created_at", -1) in index_fields or "created_at" in index_fields


def _extract_index_fields(settings):
    names = set()
    for idx in getattr(settings, "indexes", []):
        for field, direction in idx.document["key"].items():
            names.add((field, direction))
    return names
