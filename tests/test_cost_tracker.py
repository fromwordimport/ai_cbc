"""Tests for CostTracker and CostFuse.

All LLM calls are mocked — no real API requests are made.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from aicbc.config.settings import CostFuseSettings
from aicbc.cost.fuse import CostFuse, DegradationLevel
from aicbc.cost.tracker import CostRecord, CostTracker, FuseStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fuse_settings():
    """Return tight fuse settings for deterministic testing."""
    return CostFuseSettings(
        single_study_cny=100.0,
        daily_cny=200.0,
        weekly_cny=500.0,
        degrade_model="claude-haiku-4-5",
    )


@pytest.fixture
def tracker(fuse_settings):
    """Return a fresh CostTracker with tight settings."""
    t = CostTracker(settings=fuse_settings)
    t.reset()  # Ensure no persisted state from previous runs leaks into tests
    return t


@pytest.fixture
def fuse(tracker):
    """Return a CostFuse wrapping the tracker."""
    return CostFuse(tracker=tracker)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(cost_usd: float = 0.01, model: str = "claude-sonnet-4-6"):
    """Build a mock LLMResponse-like object."""
    response = MagicMock()
    response.estimated_cost_usd = cost_usd
    response.provider = MagicMock()
    response.provider.value = "anthropic"
    response.model = model
    response.prompt_tokens = 100
    response.completion_tokens = 50
    return response


# ---------------------------------------------------------------------------
# Tests: CostTracker basic recording
# ---------------------------------------------------------------------------


class TestCostTrackerRecording:
    """Tests for basic cost recording and querying."""

    def test_record_single_call(self, tracker):
        """Recording a single call should update all dimensions."""
        tracker.record(
            cost_usd=0.01,
            study_id="study-001",
            persona_id="persona-001",
            task_phase="generation",
            provider="anthropic",
            model="claude-sonnet-4-6",
            prompt_tokens=100,
            completion_tokens=50,
        )

        assert tracker.get_study_cost("study-001") == pytest.approx(0.072, abs=0.001)
        assert tracker.get_daily_cost() > 0
        assert tracker.get_weekly_cost() > 0
        assert tracker.get_global_total() > 0

    def test_record_multiple_calls_same_study(self, tracker):
        """Multiple calls to the same study should accumulate."""
        for _i in range(5):
            tracker.record(
                cost_usd=0.01,
                study_id="study-001",
                task_phase="generation",
            )

        # 5 * 0.01 USD * 7.2 = 0.36 CNY
        assert tracker.get_study_cost("study-001") == pytest.approx(0.36, abs=0.01)

    def test_record_different_studies(self, tracker):
        """Calls to different studies should be tracked separately."""
        tracker.record(cost_usd=0.01, study_id="study-A")
        tracker.record(cost_usd=0.02, study_id="study-B")
        tracker.record(cost_usd=0.01, study_id="study-A")

        assert tracker.get_study_cost("study-A") == pytest.approx(0.144, abs=0.001)
        assert tracker.get_study_cost("study-B") == pytest.approx(0.144, abs=0.001)

    def test_summary_contains_records(self, tracker):
        """CostSummary should contain all recorded records."""
        tracker.record(cost_usd=0.01, study_id="study-001")
        tracker.record(cost_usd=0.02, study_id="study-001")

        summary = tracker.get_study_summary("study-001")
        assert summary.total_calls == 2
        assert len(summary.records) == 2

    def test_reset_clears_all(self, tracker):
        """Reset should clear all tracked data."""
        tracker.record(cost_usd=0.01, study_id="study-001")
        tracker.reset()

        assert tracker.get_study_cost("study-001") == 0.0
        assert tracker.get_daily_cost() == 0.0
        assert tracker.get_global_total() == 0.0


# ---------------------------------------------------------------------------
# Tests: FuseStatus calculation
# ---------------------------------------------------------------------------


class TestFuseStatus:
    """Tests for fuse status thresholds."""

    def test_normal_status(self, tracker):
        """Below 80% should be NORMAL."""
        # 50 CNY = 50% of single_study (100)
        tracker.record(cost_usd=50 / 7.2, study_id="study-001")
        status, details = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.NORMAL
        assert details["ratios"]["study"] < 0.8

    def test_warning_status(self, tracker):
        """At 80% should be WARNING."""
        # 80 CNY = 80% of single_study
        tracker.record(cost_usd=80 / 7.2, study_id="study-001")
        status, details = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.WARNING
        assert details["ratios"]["study"] >= 0.8

    def test_degrade_status(self, tracker):
        """At 95% should be DEGRADE."""
        # 95 CNY = 95% of single_study
        tracker.record(cost_usd=95 / 7.2, study_id="study-001")
        status, details = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.DEGRADE
        assert details["ratios"]["study"] >= 0.95

    def test_fuse_status(self, tracker):
        """At 100% should be FUSE."""
        tracker.record(cost_usd=100 / 7.2, study_id="study-001")
        status, details = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.FUSE
        assert details["ratios"]["study"] >= 1.0

    def test_emergency_status(self, tracker):
        """At 120% should be EMERGENCY."""
        tracker.record(cost_usd=120 / 7.2, study_id="study-001")
        status, details = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.EMERGENCY
        assert details["ratios"]["study"] >= 1.2

    def test_daily_threshold_triggers_fuse(self, tracker):
        """Daily budget exhaustion should trigger FUSE."""
        # 200 CNY = 100% of daily
        tracker.record(cost_usd=200 / 7.2)
        status, _ = tracker.check_fuse_status()
        assert status == FuseStatus.FUSE

    def test_weekly_threshold_triggers_warning(self, tracker):
        """Weekly budget at 80% should trigger WARNING."""
        # 400 CNY = 80% of weekly (500), need daily > 400 to avoid daily override
        tracker._settings.daily_cny = 1000.0
        tracker.record(cost_usd=400 / 7.2)
        status, _ = tracker.check_fuse_status()
        assert status == FuseStatus.WARNING

    def test_most_severe_status_wins(self, tracker):
        """When multiple dimensions breach, most severe wins."""
        # study at 50% (NORMAL), daily at 100% (FUSE)
        tracker._settings.daily_cny = 250.0
        tracker._settings.weekly_cny = 10000.0
        tracker.record(cost_usd=50 / 7.2, study_id="study-001")
        tracker.record(cost_usd=200 / 7.2)
        status, _ = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.FUSE

    def test_should_allow_call_blocks_at_fuse(self, tracker):
        """should_allow_call should return False at FUSE."""
        tracker.record(cost_usd=100 / 7.2, study_id="study-001")
        allowed, status, details = tracker.should_allow_call("study-001")
        assert allowed is False
        assert status == FuseStatus.FUSE

    def test_should_allow_call_allows_at_degrade(self, tracker):
        """should_allow_call should return True at DEGRADE."""
        tracker.record(cost_usd=95 / 7.2, study_id="study-001")
        allowed, status, details = tracker.should_allow_call("study-001")
        assert allowed is True
        assert status == FuseStatus.DEGRADE


# ---------------------------------------------------------------------------
# Tests: CostFuse integration
# ---------------------------------------------------------------------------


class TestCostFuse:
    """Tests for CostFuse high-level wrapper."""

    def test_pre_call_check_normal(self, fuse):
        """Normal state should allow call with requested model."""
        allowed, status, model = fuse.pre_call_check(
            study_id="study-001",
            requested_model="claude-sonnet-4-6",
        )
        assert allowed is True
        assert status == FuseStatus.NORMAL
        assert model == "claude-sonnet-4-6"

    def test_pre_call_check_degrade(self, fuse):
        """DEGRADE state should allow call but switch model."""
        # Push to 95%
        fuse.tracker.record(cost_usd=95 / 7.2, study_id="study-001")
        allowed, status, model = fuse.pre_call_check(
            study_id="study-001",
            requested_model="claude-sonnet-4-6",
        )
        assert allowed is True
        assert status == FuseStatus.DEGRADE
        assert model == "claude-haiku-4-5"  # degraded model

    def test_pre_call_check_fuse_blocks(self, fuse):
        """FUSE state should block calls."""
        fuse.tracker.record(cost_usd=100 / 7.2, study_id="study-001")
        allowed, status, model = fuse.pre_call_check(
            study_id="study-001",
            requested_model="claude-sonnet-4-6",
        )
        assert allowed is False
        assert status == FuseStatus.FUSE

    def test_pre_call_check_emergency_blocks(self, fuse):
        """EMERGENCY state should block calls."""
        fuse.tracker.record(cost_usd=120 / 7.2, study_id="study-001")
        allowed, status, model = fuse.pre_call_check(
            study_id="study-001",
            requested_model="claude-sonnet-4-6",
        )
        assert allowed is False
        assert status == FuseStatus.EMERGENCY

    def test_record_call(self, fuse):
        """record_call should extract data from mock response."""
        response = _make_mock_response(cost_usd=0.01)
        fuse.record_call(
            response,
            study_id="study-001",
            persona_id="persona-001",
            task_phase="generation",
        )

        assert fuse.tracker.get_study_cost("study-001") > 0

    def test_get_degradation_level(self, fuse):
        """Degradation level should match fuse status."""
        assert fuse.get_degradation_level("study-001") == DegradationLevel.STANDARD

        fuse.tracker.record(cost_usd=95 / 7.2, study_id="study-001")
        assert fuse.get_degradation_level("study-001") == DegradationLevel.DEGRADED

        fuse.tracker.record(cost_usd=30 / 7.2, study_id="study-001")  # now 125%
        assert fuse.get_degradation_level("study-001") == DegradationLevel.EMERGENCY

    def test_resolve_model_normal(self, fuse):
        """Normal state should return requested model."""
        model = fuse.resolve_model("claude-sonnet-4-6", study_id="study-001")
        assert model == "claude-sonnet-4-6"

    def test_resolve_model_degraded(self, fuse):
        """Degraded state should return degrade_model."""
        fuse.tracker.record(cost_usd=95 / 7.2, study_id="study-001")
        model = fuse.resolve_model("claude-sonnet-4-6", study_id="study-001")
        assert model == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Tests: Notification deduplication
# ---------------------------------------------------------------------------


class TestNotification:
    """Tests for fuse status change notifications."""

    def test_notify_on_status_change(self, tracker):
        """Notification should fire when status changes."""
        status1, details1 = tracker.check_fuse_status("study-001")
        assert tracker.notify_if_changed(status1, details1) is True

        # Same status — no duplicate notification
        assert tracker.notify_if_changed(status1, details1) is False

    def test_notify_on_escalation(self, tracker):
        """Notification should fire on status escalation."""
        tracker.notify_if_changed(FuseStatus.NORMAL, {})

        tracker.record(cost_usd=80 / 7.2, study_id="study-001")
        status, details = tracker.check_fuse_status("study-001")
        assert tracker.notify_if_changed(status, details) is True
        assert status == FuseStatus.WARNING


# ---------------------------------------------------------------------------
# Tests: CostRecord structure
# ---------------------------------------------------------------------------


class TestCostRecord:
    """Tests for CostRecord dataclass."""

    def test_cost_record_fields(self):
        """CostRecord should store all expected fields."""
        now = datetime.now(UTC)
        record = CostRecord(
            timestamp=now,
            study_id="study-001",
            persona_id="persona-001",
            task_phase="generation",
            provider="anthropic",
            model="claude-sonnet-4-6",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.01,
            cost_cny=0.072,
            cached=False,
            degraded=False,
        )
        assert record.study_id == "study-001"
        assert record.cost_cny == pytest.approx(0.072, abs=0.001)
        assert record.cached is False

    def test_cost_record_with_cached_flag(self):
        """CostRecord should support cached flag."""
        record = CostRecord(
            timestamp=datetime.now(UTC),
            study_id="study-001",
            persona_id=None,
            task_phase="simulation",
            provider="anthropic",
            model="claude-haiku-4-5",
            prompt_tokens=50,
            completion_tokens=20,
            cost_usd=0.005,
            cost_cny=0.036,
            cached=True,
            degraded=True,
        )
        assert record.cached is True
        assert record.degraded is True
