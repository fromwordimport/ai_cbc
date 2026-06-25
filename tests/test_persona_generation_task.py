"""Tests for async persona generation Celery task."""

import json
import os

import pytest

from aicbc.analysis.tasks import run_persona_generation_task


def test_persona_generation_task_signature() -> None:
    assert run_persona_generation_task.name == "aicbc.analysis.run_persona_generation_task"


@pytest.mark.slow
@pytest.mark.skipif(not os.getenv("CI"), reason="Requires running Celery worker")
def test_persona_generation_task_runs() -> None:
    request = {
        "study_id": "test-async-gen",
        "count": 2,
        "seed": 42,
        "life_stages": ["白领"],
    }
    result = run_persona_generation_task.delay("job-test-1", json.dumps(request))
    assert result.get(timeout=120)["status"] == "COMPLETED"
