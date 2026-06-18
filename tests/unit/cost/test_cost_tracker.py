"""Unit tests for CostTracker."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from datetime import UTC, datetime
from unittest.mock import MagicMock

from aicbc.config.settings import CostFuseSettings
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


# ---------------------------------------------------------------------------
# Tests: CostTracker per-study isolation and global budget
# ---------------------------------------------------------------------------


class TestCostTrackerIsolation:
    """Tests for per-study cost isolation and global budget effects."""

    def test_per_study_isolation(self, tracker):
        """Different studies should have independent cost tracking."""
        tracker.record(cost_usd=5 / 7.2, study_id="study-A")
        tracker.record(cost_usd=9.6 / 7.2, study_id="study-B")

        # study-A at 50% of 100 CNY = NORMAL
        status_a, _ = tracker.check_fuse_status("study-A")
        assert status_a == FuseStatus.NORMAL

        # study-B at 96% of 100 CNY = DEGRADE (>= 95%)
        status_b, _ = tracker.check_fuse_status("study-B")
        assert status_b == FuseStatus.DEGRADE

    def test_global_daily_budget_affects_all_studies(self, tracker):
        """Daily budget is global and affects all studies."""
        # Exhaust daily budget via study-A
        tracker.record(cost_usd=200 / 7.2, study_id="study-A")

        # study-B should also be blocked
        status_b, _ = tracker.check_fuse_status("study-B")
        assert status_b == FuseStatus.FUSE


# ---------------------------------------------------------------------------
# Tests: CostTracker thread safety
# ---------------------------------------------------------------------------


class TestCostTrackerThreadSafety:
    """Tests for thread safety of cost recording."""

    def test_thread_safety_simulation(self, tracker):
        """Simulate concurrent cost recording to verify thread safety."""
        import threading

        def _record_costs(study_id: str, n_calls: int) -> None:
            for _ in range(n_calls):
                tracker.record(
                    cost_usd=0.1,
                    study_id=study_id,
                    task_phase="test",
                )

        threads = [
            threading.Thread(target=_record_costs, args=(f"study-{i}", 50))
            for i in range(4)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total: 4 threads * 50 calls * 0.1 USD * 7.2 = 144 CNY
        assert tracker.get_global_total() == pytest.approx(144.0, abs=1.0)

        # Each study should have 50 calls
        for i in range(4):
            summary = tracker.get_study_summary(f"study-{i}")
            assert summary.total_calls == 50

    def test_zero_cost_call_does_not_affect_status(self, tracker):
        """A zero-cost call should not change fuse status."""
        tracker.record(cost_usd=5.0 / 7.2, study_id="study-001")
        status_before, _ = tracker.check_fuse_status("study-001")

        tracker.record(cost_usd=0.0, study_id="study-001")
        status_after, _ = tracker.check_fuse_status("study-001")

        assert status_before == status_after

    def test_negative_cost_is_handled_gracefully(self, tracker):
        """Negative cost (e.g., refund) should reduce total cost."""
        tracker.record(cost_usd=5.0 / 7.2, study_id="study-001")
        initial = tracker.get_study_cost("study-001")

        tracker.record(cost_usd=-1.0 / 7.2, study_id="study-001")
        after = tracker.get_study_cost("study-001")

        assert after < initial


# ---------------------------------------------------------------------------
# Tests: CostTracker threshold boundary precision
# ---------------------------------------------------------------------------


class TestCostTrackerThresholdBoundaries:
    """Test cost tracker behavior at and around all threshold boundaries."""

    def test_exactly_at_80_percent_warning(self, tracker):
        """Exactly 80% should trigger WARNING, not DEGRADE."""
        tracker.record(cost_usd=80.0 / 7.2, study_id="study-001")
        status, details = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.WARNING
        assert details["ratios"]["study"] == pytest.approx(0.8, abs=0.01)

    def test_exactly_at_95_percent_degrade(self, tracker):
        """Exactly 95% should trigger DEGRADE."""
        tracker.record(cost_usd=95.0 / 7.2, study_id="study-001")
        status, details = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.DEGRADE
        assert details["ratios"]["study"] == pytest.approx(0.95, abs=0.01)

    def test_exactly_at_100_percent_fuse(self, tracker):
        """Exactly 100% should trigger FUSE (calls blocked)."""
        tracker.record(cost_usd=100.0 / 7.2, study_id="study-001")
        allowed, status, _ = tracker.should_allow_call("study-001")
        assert allowed is False
        assert status == FuseStatus.FUSE

    def test_exactly_at_120_percent_emergency(self, tracker):
        """Exactly 120% should trigger EMERGENCY."""
        tracker.record(cost_usd=120.0 / 7.2, study_id="study-001")
        status, _ = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.EMERGENCY

    def test_just_below_threshold_boundary(self, tracker):
        """79.9% should remain NORMAL, not WARNING."""
        tracker.record(cost_usd=79.9 / 7.2, study_id="study-001")
        status, _ = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.NORMAL

    def test_just_above_threshold_boundary(self, tracker):
        """80.1% should trigger WARNING."""
        tracker.record(cost_usd=80.1 / 7.2, study_id="study-001")
        status, _ = tracker.check_fuse_status("study-001")
        assert status == FuseStatus.WARNING

    def test_monthly_budget_triggers_emergency(self, tracker):
        """Monthly budget at 120% should trigger EMERGENCY even if daily is fine."""
        # Daily: 100 CNY = 50% (NORMAL)
        # Monthly: 600 CNY = 120% (EMERGENCY) — need monthly setting
        tracker._settings.monthly_cny = 500.0
        tracker.record(cost_usd=100.0 / 7.2)  # daily
        tracker.record(cost_usd=500.0 / 7.2)  # additional for monthly
        status, _ = tracker.check_fuse_status()
        assert status == FuseStatus.EMERGENCY

    def test_weekly_budget_triggers_fuse(self, tracker):
        """Weekly budget at 100% should trigger FUSE."""
        # Temporarily raise daily threshold so weekly wins
        tracker._settings.daily_cny = 1000.0
        tracker.record(cost_usd=500.0 / 7.2)
        status, _ = tracker.check_fuse_status()
        assert status == FuseStatus.FUSE


# ---------------------------------------------------------------------------
# Tests: Notification escalation and de-escalation
# ---------------------------------------------------------------------------


class TestNotificationEscalation:
    """Tests for notification behavior on status changes."""

    def test_notification_on_escalation_then_deescalation(self, tracker):
        """Status going up then down should trigger notifications on each change."""
        # Start at NORMAL
        tracker.notify_if_changed(FuseStatus.NORMAL, {})

        # Escalate to WARNING
        tracker.record(cost_usd=80.0 / 7.2, study_id="study-001")
        status, details = tracker.check_fuse_status("study-001")
        assert tracker.notify_if_changed(status, details) is True
        assert status == FuseStatus.WARNING

        # Reset and de-escalate back to NORMAL
        tracker.reset()
        status, details = tracker.check_fuse_status("study-001")
        assert tracker.notify_if_changed(status, details) is True
        assert status == FuseStatus.NORMAL
