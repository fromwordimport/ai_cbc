"""Tests for dashboard summary optimization."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from aicbc.monitoring.health import dashboard_summary
from aicbc.questionnaire.models import (
    Attribute,
    AttributeLevel,
    AttributeType,
    CBCStudy,
    StudyStatus,
)


def _make_minimal_study(study_id: str, status: StudyStatus, created_at: datetime) -> CBCStudy:
    """Build a minimal valid CBCStudy for testing."""
    return CBCStudy(
        study_id=study_id,
        product_category="洗碗机",
        research_goal="测试",
        attributes=[
            Attribute(
                id="brand",
                name="品牌",
                type=AttributeType.CATEGORICAL,
                levels=[
                    AttributeLevel(value="A", label="品牌A"),
                    AttributeLevel(value="B", label="品牌B"),
                ],
            ),
            Attribute(
                id="price",
                name="价格",
                type=AttributeType.PRICE,
                levels=[
                    AttributeLevel(value=1000, label="1000元"),
                    AttributeLevel(value=2000, label="2000元"),
                ],
            ),
        ],
        status=status,
        created_at=created_at,
    )


@pytest.fixture(autouse=True)
def _clean_dashboard_summary_cache():
    from aicbc.core.cache import invalidate_dashboard_summary
    invalidate_dashboard_summary()
    yield


@pytest.mark.asyncio
async def test_dashboard_summary_uses_cache():
    first = await dashboard_summary()
    second = await dashboard_summary()
    assert first == second


@pytest.mark.asyncio
async def test_dashboard_summary_invalidates():
    from aicbc.core.cache import invalidate_dashboard_summary
    from aicbc.core.store import get_questionnaire_store

    # Seed a study so the first call has non-empty data
    study_store = get_questionnaire_store()
    study = _make_minimal_study(
        study_id="test-001",
        status=StudyStatus.INIT,
        created_at=datetime.now(UTC),
    )
    await study_store.asave_study(study)

    first = await dashboard_summary()
    invalidate_dashboard_summary()

    # In test environment MemoryQuestionnaireStore is used, so patch it
    with patch.object(
        study_store, "acount_studies_by_status", return_value={"draft": 5}
    ):
        second = await dashboard_summary()
    assert first != second
    assert second["summary"]["studies_by_status"].get("draft") == 5
