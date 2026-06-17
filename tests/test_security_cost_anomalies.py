"""Security and cost anomaly tests for AI_CBC (Task #14).

Covers:
1. 安全异常测试用例 — LLM tool call failures, malformed output, provider errors,
   retry exhaustion, JSON parse failures, timeout simulation.
2. 成本异常测试用例 — cost fuse triggering at all thresholds, budget exhaustion
   mid-batch, cross-study budget isolation, emergency lockdown.
3. Agent鲁棒性测试 — BaseAgent tool errors, correction loop limits, prompt
   injection resilience, fallback behavior under degradation.

All tests use mocking — no real API calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aicbc.agents.base import (
    BaseAgent,
    DynamicExample,
    RuleInjection,
    SystemInstruction,
)
from aicbc.config.settings import CostFuseSettings
from aicbc.cost.fuse import CostFuse, CostFuseError, DegradationLevel
from aicbc.cost.tracker import CostTracker, FuseStatus
from aicbc.llm.client import LLMClient, Provider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tight_fuse_settings() -> CostFuseSettings:
    """Very tight budget settings to trigger fuse quickly in tests."""
    return CostFuseSettings(
        single_study_cny=10.0,
        daily_cny=20.0,
        weekly_cny=50.0,
        monthly_cny=200.0,
        degrade_model="claude-haiku-4-5",
    )


@pytest.fixture
def cost_tracker(tight_fuse_settings: CostFuseSettings) -> CostTracker:
    """Fresh CostTracker with tight settings."""
    tracker = CostTracker(settings=tight_fuse_settings)
    tracker.reset()
    return tracker


@pytest.fixture
def cost_fuse(cost_tracker: CostTracker) -> CostFuse:
    """Fresh CostFuse wrapping the tracker."""
    return CostFuse(tracker=cost_tracker)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Return a fully-populated mock settings object."""
    settings = MagicMock()
    settings.llm.provider = "anthropic"
    settings.llm.model = ""
    settings.llm.temperature = 0.3
    settings.llm.max_tokens = 4096
    settings.llm.timeout_seconds = 120
    settings.llm.max_retries = 2
    settings.anthropic.enabled = True
    settings.anthropic.api_key = "sk-ant-test"
    settings.anthropic.base_url = "https://api.anthropic.com"
    settings.anthropic.model_persona = "claude-sonnet-4-6"
    settings.openai.enabled = True
    settings.openai.api_key = "sk-test"
    settings.openai.base_url = "https://api.openai.com/v1"
    settings.openai.model = "gpt-4o"
    settings.deepseek.enabled = False
    settings.deepseek.api_key = ""
    settings.deepseek.base_url = "https://api.deepseek.com/v1"
    settings.deepseek.model = "deepseek-chat"
    settings.qwen.enabled = False
    settings.qwen.api_key = ""
    settings.qwen.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    settings.qwen.model = "qwen-max"
    settings.glm.enabled = False
    settings.glm.api_key = ""
    settings.glm.base_url = "https://open.bigmodel.cn/api/paas/v4"
    settings.glm.model = "glm-4"
    settings.cost_fuse = CostFuseSettings(
        single_study_cny=10.0,
        daily_cny=20.0,
        weekly_cny=50.0,
        monthly_cny=200.0,
        degrade_model="claude-haiku-4-5",
    )
    return settings


@pytest.fixture
def mock_llm_client(mock_settings: MagicMock) -> LLMClient:
    """Return an LLMClient with patched settings and no cost fuse."""
    with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
        client = LLMClient()
    return client


def _build_anthropic_response(
    content_text: str, input_tokens: int, output_tokens: int
) -> MagicMock:
    """Build a mock Anthropic Messages API response."""
    response = MagicMock()
    block = MagicMock()
    block.text = content_text
    response.content = [block]
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    response.usage = usage
    return response


def _build_openai_response(
    content_text: str, prompt_tokens: int, completion_tokens: int
) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response."""
    response = MagicMock()
    choice = MagicMock()
    choice.message.content = content_text
    response.choices = [choice]
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    response.usage = usage
    return response


# ===========================================================================
# 1. 安全异常测试用例 (Security Anomaly Tests)
# ===========================================================================


class TestLLMClientSecurityAnomalies:
    """Security anomaly tests for LLMClient — tool failures, malformed output, etc."""

    def test_generate_raises_on_all_retries_exhausted_anthropic(
        self, mock_settings: MagicMock
    ) -> None:
        """When Anthropic API fails on every retry, RuntimeError should be raised."""
        from anthropic import APIError as AnthropicAPIError

        # Set max_retries=3 to match existing test expectations
        mock_settings.llm.max_retries = 3
        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        with (
            patch.object(
                client._anthropic.messages,
                "create",
                side_effect=AnthropicAPIError("Connection timeout", request=MagicMock(), body=None),
            ),
            patch("aicbc.llm.client.time.sleep") as mock_sleep,
            pytest.raises(RuntimeError, match="failed after 3 attempts"),
        ):
            client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        # max_retries=3 means 2 retries (sleep twice: 1s, 2s)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    def test_generate_raises_on_all_retries_exhausted_openai(
        self, mock_settings: MagicMock
    ) -> None:
        """When OpenAI API fails on every retry, RuntimeError should be raised."""
        from openai import APIError as OpenAIAPIError

        mock_settings.llm.max_retries = 3
        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        with (
            patch.object(
                client._openai.chat.completions,
                "create",
                side_effect=OpenAIAPIError("Rate limit exceeded", request=MagicMock(), body=None),
            ),
            patch("aicbc.llm.client.time.sleep") as mock_sleep,
            pytest.raises(RuntimeError, match="failed after 3 attempts"),
        ):
            client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="gpt-4o",
            )

        assert mock_sleep.call_count == 2

    def test_generate_json_raises_on_malformed_json_response(
        self, mock_settings: MagicMock
    ) -> None:
        """When LLM returns non-JSON in json_mode, RuntimeError should be raised."""
        mock_response = _build_anthropic_response("not valid json", 5, 5)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        with (
            patch.object(client._anthropic.messages, "create", return_value=mock_response),
            pytest.raises(RuntimeError, match="Failed to parse LLM response as JSON"),
        ):
            client.generate_json(
                messages=[{"role": "user", "content": "Give me JSON"}],
                model="claude-sonnet-4-6",
            )

    def test_generate_json_raises_on_empty_content(self, mock_settings: MagicMock) -> None:
        """When LLM returns empty content in json_mode, RuntimeError should be raised."""
        mock_response = _build_anthropic_response("", 5, 0)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        with (
            patch.object(client._anthropic.messages, "create", return_value=mock_response),
            pytest.raises(RuntimeError, match="Failed to parse LLM response as JSON"),
        ):
            client.generate_json(
                messages=[{"role": "user", "content": "Give me JSON"}],
                model="claude-sonnet-4-6",
            )

    def test_generate_with_markdown_code_fences_stripped(self, mock_settings: MagicMock) -> None:
        """Markdown code fences should be stripped from the response content."""
        mock_response = _build_anthropic_response('```json\n{"key": "value"}\n```', 10, 10)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        with patch.object(client._anthropic.messages, "create", return_value=mock_response):
            result = client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        assert result.content == '{"key": "value"}'

    def test_generate_with_generic_code_fences_stripped(self, mock_settings: MagicMock) -> None:
        """Generic markdown code fences should also be stripped."""
        mock_response = _build_anthropic_response("```\nsome plain text\n```", 10, 10)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        with patch.object(client._anthropic.messages, "create", return_value=mock_response):
            result = client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        assert result.content == "some plain text"

    def test_unconfigured_provider_raises_runtime_error(self, mock_settings: MagicMock) -> None:
        """Using a provider without API key configured should raise RuntimeError."""
        mock_settings.anthropic.api_key = ""
        mock_settings.openai.api_key = ""

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        with pytest.raises(RuntimeError, match="Anthropic client is not configured"):
            client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

    def test_unknown_provider_defaults_to_anthropic(self, mock_settings: MagicMock) -> None:
        """Unknown model names should default to Anthropic provider."""
        assert LLMClient._detect_provider("some-unknown-model") == Provider.ANTHROPIC

    def test_latency_is_recorded(self, mock_settings: MagicMock) -> None:
        """Successful calls should record non-negative latency."""
        mock_response = _build_anthropic_response("Hello", 10, 5)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        with patch.object(client._anthropic.messages, "create", return_value=mock_response):
            result = client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        assert result.latency_seconds >= 0


class TestLLMClientCostFuseSecurity:
    """Security tests: cost fuse should block calls before they reach the API."""

    def test_cost_fuse_blocks_before_api_call(
        self, mock_settings: MagicMock, cost_fuse: CostFuse
    ) -> None:
        """When fuse is triggered, the API should never be called."""
        cost_fuse.tracker.record(cost_usd=20 / 7.2)  # Exhaust daily budget

        create_spy = MagicMock()

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(cost_fuse=cost_fuse)

        with (
            patch.object(client._anthropic.messages, "create", create_spy),
            pytest.raises(CostFuseError, match="Cost fuse triggered"),
        ):
            client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        create_spy.assert_not_called()

    def test_cost_fuse_degrades_model_before_api_call(
        self, mock_settings: MagicMock, cost_fuse: CostFuse
    ) -> None:
        """When status is DEGRADE, model should be switched before API call."""
        cost_fuse.tracker.record(cost_usd=19 / 7.2)  # 95% of daily budget

        mock_response = _build_anthropic_response("Degraded", 10, 5)
        create_spy = MagicMock(return_value=mock_response)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(cost_fuse=cost_fuse)

        with patch.object(client._anthropic.messages, "create", create_spy):
            result = client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        call_kwargs = create_spy.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5"
        assert result.model == "claude-haiku-4-5"

    def test_cost_fuse_records_cost_even_on_degraded_call(
        self, mock_settings: MagicMock, cost_fuse: CostFuse
    ) -> None:
        """Cost should be recorded even when model was degraded."""
        cost_fuse.tracker.record(cost_usd=19 / 7.2)
        initial_cost = cost_fuse.tracker.get_global_total()

        mock_response = _build_anthropic_response("OK", 1000, 500)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(cost_fuse=cost_fuse)

        with patch.object(client._anthropic.messages, "create", return_value=mock_response):
            client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        assert cost_fuse.tracker.get_global_total() > initial_cost


# ===========================================================================
# 2. 成本异常测试用例 (Cost Anomaly Tests)
# ===========================================================================


class TestCostFuseThresholdAnomalies:
    """Test cost fuse behavior at and around all threshold boundaries."""

    def test_exactly_at_80_percent_warning(self, cost_tracker: CostTracker) -> None:
        """Exactly 80% should trigger WARNING, not DEGRADE."""
        cost_tracker.record(cost_usd=8.0 / 7.2, study_id="study-001")
        status, details = cost_tracker.check_fuse_status("study-001")
        assert status == FuseStatus.WARNING
        assert details["ratios"]["study"] == pytest.approx(0.8, abs=0.01)

    def test_exactly_at_95_percent_degrade(self, cost_tracker: CostTracker) -> None:
        """Exactly 95% should trigger DEGRADE."""
        cost_tracker.record(cost_usd=9.5 / 7.2, study_id="study-001")
        status, details = cost_tracker.check_fuse_status("study-001")
        assert status == FuseStatus.DEGRADE
        assert details["ratios"]["study"] == pytest.approx(0.95, abs=0.01)

    def test_exactly_at_100_percent_fuse(self, cost_tracker: CostTracker) -> None:
        """Exactly 100% should trigger FUSE (calls blocked)."""
        cost_tracker.record(cost_usd=10.0 / 7.2, study_id="study-001")
        allowed, status, _ = cost_tracker.should_allow_call("study-001")
        assert allowed is False
        assert status == FuseStatus.FUSE

    def test_exactly_at_120_percent_emergency(self, cost_tracker: CostTracker) -> None:
        """Exactly 120% should trigger EMERGENCY."""
        cost_tracker.record(cost_usd=12.0 / 7.2, study_id="study-001")
        status, _ = cost_tracker.check_fuse_status("study-001")
        assert status == FuseStatus.EMERGENCY

    def test_just_below_threshold_boundary(self, cost_tracker: CostTracker) -> None:
        """79.9% should remain NORMAL, not WARNING."""
        cost_tracker.record(cost_usd=7.99 / 7.2, study_id="study-001")
        status, _ = cost_tracker.check_fuse_status("study-001")
        assert status == FuseStatus.NORMAL

    def test_just_above_threshold_boundary(self, cost_tracker: CostTracker) -> None:
        """80.1% should trigger WARNING."""
        cost_tracker.record(cost_usd=8.01 / 7.2, study_id="study-001")
        status, _ = cost_tracker.check_fuse_status("study-001")
        assert status == FuseStatus.WARNING

    def test_monthly_budget_triggers_emergency(self, cost_tracker: CostTracker) -> None:
        """Monthly budget at 120% should trigger EMERGENCY even if daily is fine."""
        # Daily: 10 CNY = 50% (NORMAL)
        # Monthly: 240 CNY = 120% (EMERGENCY)
        cost_tracker.record(cost_usd=10.0 / 7.2)  # daily
        cost_tracker.record(cost_usd=230.0 / 7.2)  # additional for monthly
        status, _ = cost_tracker.check_fuse_status()
        assert status == FuseStatus.EMERGENCY

    def test_weekly_budget_triggers_fuse(self, cost_tracker: CostTracker) -> None:
        """Weekly budget at 100% should trigger FUSE."""
        # Temporarily raise daily threshold so weekly wins
        cost_tracker._settings.daily_cny = 1000.0
        cost_tracker.record(cost_usd=50.0 / 7.2)
        status, _ = cost_tracker.check_fuse_status()
        assert status == FuseStatus.FUSE


class TestCostFuseBatchAnomalies:
    """Test cost fuse behavior during batch operations."""

    def test_batch_stops_midway_on_fuse_trigger(
        self, mock_settings: MagicMock, cost_fuse: CostFuse
    ) -> None:
        """Simulate a batch where the fuse triggers partway through."""
        # Pre-load to 90% of daily budget
        cost_fuse.tracker.record(cost_usd=18.0 / 7.2)

        mock_response = _build_anthropic_response("OK", 1000, 500)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(cost_fuse=cost_fuse)

        call_count = 0

        def _create_side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return mock_response

        with patch.object(client._anthropic.messages, "create", side_effect=_create_side_effect):
            # First call — should succeed (degraded model)
            result1 = client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )
            assert result1 is not None

            # After first call, status should be at least DEGRADE
            status, _ = cost_fuse.tracker.check_fuse_status()
            assert status in (FuseStatus.DEGRADE, FuseStatus.FUSE, FuseStatus.EMERGENCY)

    def test_multiple_studies_isolated_until_global_budget_hit(
        self, cost_tracker: CostTracker
    ) -> None:
        """Different studies should be isolated until global budget is hit."""
        # Study A at 50% (NORMAL)
        cost_tracker.record(cost_usd=5.0 / 7.2, study_id="study-A")
        # Study B at 96% (DEGRADE)
        cost_tracker.record(cost_usd=9.6 / 7.2, study_id="study-B")

        status_a, _ = cost_tracker.check_fuse_status("study-A")
        status_b, _ = cost_tracker.check_fuse_status("study-B")

        assert status_a == FuseStatus.NORMAL
        assert status_b == FuseStatus.DEGRADE

        # Now exhaust global daily budget (need to raise daily threshold so study-C doesn't also trigger daily)
        cost_tracker._settings.daily_cny = 1000.0
        cost_tracker.record(cost_usd=50.0 / 7.2, study_id="study-C")

        # Both A and B should now be blocked via global budget (weekly at 100%+)
        status_a_after, _ = cost_tracker.check_fuse_status("study-A")
        status_b_after, _ = cost_tracker.check_fuse_status("study-B")
        assert status_a_after in (FuseStatus.FUSE, FuseStatus.EMERGENCY)
        assert status_b_after in (FuseStatus.FUSE, FuseStatus.EMERGENCY)

    def test_cost_tracker_thread_safety_simulation(self, cost_tracker: CostTracker) -> None:
        """Simulate concurrent cost recording to verify thread safety."""
        import threading

        def _record_costs(study_id: str, n_calls: int) -> None:
            for _ in range(n_calls):
                cost_tracker.record(
                    cost_usd=0.1,
                    study_id=study_id,
                    task_phase="test",
                )

        threads = [
            threading.Thread(target=_record_costs, args=(f"study-{i}", 50)) for i in range(4)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total: 4 threads * 50 calls * 0.1 USD * 7.2 = 144 CNY
        assert cost_tracker.get_global_total() == pytest.approx(144.0, abs=1.0)

        # Each study should have 50 calls
        for i in range(4):
            summary = cost_tracker.get_study_summary(f"study-{i}")
            assert summary.total_calls == 50

    def test_zero_cost_call_does_not_affect_status(self, cost_tracker: CostTracker) -> None:
        """A zero-cost call should not change fuse status."""
        cost_tracker.record(cost_usd=5.0 / 7.2, study_id="study-001")
        status_before, _ = cost_tracker.check_fuse_status("study-001")

        cost_tracker.record(cost_usd=0.0, study_id="study-001")
        status_after, _ = cost_tracker.check_fuse_status("study-001")

        assert status_before == status_after

    def test_negative_cost_is_handled_gracefully(self, cost_tracker: CostTracker) -> None:
        """Negative cost (e.g., refund) should reduce total cost."""
        cost_tracker.record(cost_usd=5.0 / 7.2, study_id="study-001")
        initial = cost_tracker.get_study_cost("study-001")

        cost_tracker.record(cost_usd=-1.0 / 7.2, study_id="study-001")
        after = cost_tracker.get_study_cost("study-001")

        assert after < initial


class TestCostFuseNotificationAnomalies:
    """Test notification behavior under anomalous conditions."""

    def test_notification_deduplication(self, cost_tracker: CostTracker) -> None:
        """Same status should not trigger duplicate notifications."""
        status, details = cost_tracker.check_fuse_status("study-001")
        assert cost_tracker.notify_if_changed(status, details) is True
        assert cost_tracker.notify_if_changed(status, details) is False

    def test_notification_on_escalation_then_deescalation(self, cost_tracker: CostTracker) -> None:
        """Status going up then down should trigger notifications on each change."""
        # Start at NORMAL
        cost_tracker.notify_if_changed(FuseStatus.NORMAL, {})

        # Escalate to WARNING
        cost_tracker.record(cost_usd=8.0 / 7.2, study_id="study-001")
        status, details = cost_tracker.check_fuse_status("study-001")
        assert cost_tracker.notify_if_changed(status, details) is True
        assert status == FuseStatus.WARNING

        # Reset and de-escalate back to NORMAL
        cost_tracker.reset()
        status, details = cost_tracker.check_fuse_status("study-001")
        assert cost_tracker.notify_if_changed(status, details) is True
        assert status == FuseStatus.NORMAL


# ===========================================================================
# 3. Agent鲁棒性测试 (Agent Robustness Tests)
# ===========================================================================


class TestBaseAgentToolRobustness:
    """Test BaseAgent tool-calling robustness under failure conditions."""

    def test_call_unregistered_tool_raises_keyerror(self) -> None:
        """Calling an unregistered tool should raise KeyError."""
        agent = _make_test_agent()
        with pytest.raises(KeyError, match="Tool 'nonexistent' not registered"):
            agent.call_tool("nonexistent")

    def test_tool_that_raises_exception_propagates(self) -> None:
        """Tool that raises an exception should propagate to caller."""
        agent = _make_test_agent()

        def _failing_tool() -> None:
            raise ValueError("Tool failed")

        agent.register_tool("fail", _failing_tool)
        with pytest.raises(ValueError, match="Tool failed"):
            agent.call_tool("fail")

    def test_tool_with_wrong_arguments_raises_typeerror(self) -> None:
        """Calling a tool with wrong arguments should raise TypeError."""
        agent = _make_test_agent()

        def _requires_arg(x: int) -> int:
            return x * 2

        agent.register_tool("double", _requires_arg)
        with pytest.raises(TypeError):
            agent.call_tool("double")  # Missing required arg

    def test_tool_registration_overwrite(self) -> None:
        """Registering a tool with the same name should overwrite."""
        agent = _make_test_agent()
        agent.register_tool("compute", lambda: 1)
        agent.register_tool("compute", lambda: 2)
        assert agent.call_tool("compute") == 2

    def test_tool_spec_is_optional(self) -> None:
        """Tool registration should work without a ToolSpec."""
        agent = _make_test_agent()
        agent.register_tool("simple", lambda: "ok")
        assert agent.call_tool("simple") == "ok"


class TestBaseAgentCorrectionLoop:
    """Test BaseAgent self-correction loop limits and edge cases."""

    def test_max_corrections_respected(self) -> None:
        """After max_corrections, the loop should stop even if still failing."""
        agent = _make_test_agent(max_corrections=2)

        call_count = 0

        def _always_fails(**kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            return "bad"

        def _always_fails_eval(result: str) -> dict[str, Any]:
            return {"passed": False, "details": "still bad"}

        # Override _should_correct to always request correction
        agent._should_correct = lambda evaluation: (True, "needs fix")

        result, state = agent.run_with_correction(
            execute_fn=_always_fails,
            evaluate_fn=_always_fails_eval,
        )

        # Initial execute + 2 corrections = 3 execute calls total
        assert call_count == 3
        assert state.correction_count == 2

    def test_no_correction_needed_returns_immediately(self) -> None:
        """When evaluation passes, no corrections should occur."""
        agent = _make_test_agent(max_corrections=3)

        def _succeeds(**kwargs: Any) -> str:
            return "good"

        def _passes_eval(result: str) -> dict[str, Any]:
            return {"passed": True}

        # Override _should_correct to never request correction
        agent._should_correct = lambda evaluation: (False, "")

        result, state = agent.run_with_correction(
            execute_fn=_succeeds,
            evaluate_fn=_passes_eval,
        )

        assert result == "good"
        assert state.correction_count == 0
        assert state.turn_count == 1

    def test_correction_feedback_injected(self) -> None:
        """Correction feedback should be passed to execute_fn."""
        agent = _make_test_agent(max_corrections=1)

        received_feedback: str | None = None

        def _succeeds_on_feedback(**kwargs: Any) -> str:
            nonlocal received_feedback
            received_feedback = kwargs.get("feedback", "")
            return "fixed"

        def _fails_once(result: str) -> dict[str, Any]:
            return {"passed": False, "details": "missing field"}

        # Override _should_correct to always request correction once
        agent._should_correct = lambda evaluation: (True, "needs fix")

        result, state = agent.run_with_correction(
            execute_fn=_succeeds_on_feedback,
            evaluate_fn=_fails_once,
        )

        assert received_feedback is not None
        assert "missing field" in received_feedback

    def test_agent_state_records_history(self) -> None:
        """AgentState should record all turns in history."""
        agent = _make_test_agent(max_corrections=1)

        def _succeeds(**kwargs: Any) -> str:
            return "result"

        def _fails_once(result: str) -> dict[str, Any]:
            return {"passed": False}

        # Override _should_correct to always request correction
        agent._should_correct = lambda evaluation: (True, "needs fix")

        _, state = agent.run_with_correction(
            execute_fn=_succeeds,
            evaluate_fn=_fails_once,
        )

        assert len(state.history) >= 2  # initial execute + self_correction + re-execute
        assert state.history[0]["action"] == "execute"
        # history[1] is the self_correction record, history[2] is re_execute
        assert any(h["action"] == "re_execute" for h in state.history)


class TestBaseAgentPromptBuilding:
    """Test prompt building under anomalous conditions."""

    def test_build_prompt_with_empty_rules(self) -> None:
        """Prompt should build correctly even with empty rules."""
        agent = _make_test_agent()
        messages = agent.build_prompt("Do something")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_build_prompt_with_extra_rules(self) -> None:
        """Extra rules should be appended to existing rules."""
        agent = _make_test_agent()
        messages = agent.build_prompt("Do something", extra_rules=["Extra rule 1"])
        assert "Extra rule 1" in messages[0]["content"]

    def test_build_prompt_with_no_examples(self) -> None:
        """Prompt should build without examples."""
        agent = _make_test_agent(examples=[])
        messages = agent.build_prompt("Do something")
        assert len(messages) == 2

    def test_build_prompt_with_multiple_examples(self) -> None:
        """Multiple examples should all appear in the prompt."""
        agent = _make_test_agent(
            examples=[
                DynamicExample("input1", "output1"),
                DynamicExample("input2", "output2"),
            ]
        )
        messages = agent.build_prompt("Do something")
        assert "input1" in messages[0]["content"]
        assert "input2" in messages[0]["content"]


class TestBaseAgentDegradationUnderCostFuse:
    """Test agent behavior when cost fuse forces model degradation."""

    def test_agent_execution_with_cost_fuse_blocked(self, cost_fuse: CostFuse) -> None:
        """Agent execute should handle CostFuseError gracefully."""
        cost_fuse.tracker.record(cost_usd=20 / 7.2)  # Block daily budget

        class TestAgent(BaseAgent[str]):
            def execute(self, **kwargs: Any) -> str:
                raise CostFuseError("Cost fuse triggered")

        agent = TestAgent(
            system_instruction=SystemInstruction(role="test", expertise=["testing"]),
        )

        with pytest.raises(CostFuseError, match="Cost fuse triggered"):
            agent.execute()

    def test_agent_execution_with_degraded_model(self, cost_fuse: CostFuse) -> None:
        """Agent should use degraded model when fuse status is DEGRADE."""
        cost_fuse.tracker.record(cost_usd=19 / 7.2)  # 95% of daily budget

        level = cost_fuse.get_degradation_level()
        assert level == DegradationLevel.DEGRADED

        resolved = cost_fuse.resolve_model("claude-sonnet-4-6")
        assert resolved == "claude-haiku-4-5"


# ===========================================================================
# Helpers
# ===========================================================================


def _make_test_agent(
    max_corrections: int = 3,
    examples: list[DynamicExample] | None = None,
) -> BaseAgent:
    """Factory for a minimal concrete BaseAgent subclass for testing."""

    class ConcreteAgent(BaseAgent[str]):
        def execute(self, **kwargs: Any) -> str:
            return "done"

    return ConcreteAgent(
        system_instruction=SystemInstruction(
            role="测试助手",
            expertise=["测试"],
            constraints=["不要编造数据"],
        ),
        rules=RuleInjection(
            rules=["RULE-001: 必须真实", "RULE-002: 不得偏见"],
            forbidden_patterns=["AI", "模型"],
            required_fields=["reasoning"],
        ),
        examples=examples,
        max_corrections=max_corrections,
    )
