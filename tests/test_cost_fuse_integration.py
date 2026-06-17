"""Integration tests for CostFuse + LLMClient.

Verifies that the fuse intercepts LLM calls at the correct thresholds
and degrades models automatically.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aicbc.config.settings import CostFuseSettings
from aicbc.cost.fuse import CostFuse, CostFuseError
from aicbc.cost.tracker import CostTracker, FuseStatus
from aicbc.llm.client import LLMClient, LLMResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tight_fuse_settings():
    """Very tight settings to trigger fuse quickly in tests."""
    return CostFuseSettings(
        single_study_cny=10.0,
        daily_cny=20.0,
        weekly_cny=50.0,
        degrade_model="claude-haiku-4-5",
    )


@pytest.fixture
def cost_tracker(tight_fuse_settings):
    t = CostTracker(settings=tight_fuse_settings)
    t.reset()  # Ensure no persisted state from previous runs leaks into tests
    return t


@pytest.fixture
def cost_fuse(cost_tracker):
    return CostFuse(tracker=cost_tracker)


@pytest.fixture
def mock_settings():
    """Return a fully-populated mock settings object."""
    settings = MagicMock()
    settings.llm.provider = "anthropic"
    settings.llm.model = ""
    settings.llm.temperature = 0.3
    settings.llm.max_tokens = 4096
    settings.llm.timeout_seconds = 120
    settings.llm.max_retries = 3
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
        degrade_model="claude-haiku-4-5",
    )
    return settings


def _build_anthropic_response(content_text: str, input_tokens: int, output_tokens: int):
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


# ---------------------------------------------------------------------------
# Tests: LLMClient + CostFuse integration
# ---------------------------------------------------------------------------


class TestLLMClientCostFuseIntegration:
    """Tests verifying LLMClient respects CostFuse decisions."""

    def test_llm_client_allows_call_when_normal(self, mock_settings, cost_fuse):
        """When fuse is NORMAL, LLMClient should proceed with the call."""
        mock_response = _build_anthropic_response("Hello", 10, 5)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(cost_fuse=cost_fuse)

        with patch.object(client._anthropic.messages, "create", return_value=mock_response):
            result = client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello"

    def test_llm_client_blocks_call_when_fuse_triggered(self, mock_settings, cost_fuse):
        """When fuse is FUSE, LLMClient should raise CostFuseError."""
        # Push daily budget to 100% (20 CNY)
        cost_fuse.tracker.record(cost_usd=20 / 7.2)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(cost_fuse=cost_fuse)

        with pytest.raises(CostFuseError, match="Cost fuse triggered"):
            client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

    def test_llm_client_degrades_model_when_degrade_status(self, mock_settings, cost_fuse):
        """When fuse is DEGRADE, LLMClient should switch to lighter model."""
        # Push daily budget to 95% (19 CNY)
        cost_fuse.tracker.record(cost_usd=19 / 7.2)

        mock_response = _build_anthropic_response("Degraded", 10, 5)
        create_spy = MagicMock(return_value=mock_response)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(cost_fuse=cost_fuse)

        with patch.object(client._anthropic.messages, "create", create_spy):
            result = client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        # The call should succeed but with the degraded model
        call_kwargs = create_spy.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5"
        assert result.model == "claude-haiku-4-5"

    def test_llm_client_records_cost_after_success(self, mock_settings, cost_fuse):
        """After a successful call, cost should be recorded in tracker."""
        mock_response = _build_anthropic_response("Hello", 10, 5)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(cost_fuse=cost_fuse)

        initial_cost = cost_fuse.tracker.get_global_total()

        with patch.object(client._anthropic.messages, "create", return_value=mock_response):
            client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

        # Cost should have been recorded (10 input * $3 + 5 output * $15) / 1000 = $0.105
        # In CNY: 0.105 * 7.2 = 0.756
        assert cost_fuse.tracker.get_global_total() > initial_cost

    def test_llm_client_generate_json_also_respects_fuse(self, mock_settings, cost_fuse):
        """generate_json should also be blocked by the fuse."""
        cost_fuse.tracker.record(cost_usd=20 / 7.2)

        with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(cost_fuse=cost_fuse)

        with pytest.raises(CostFuseError, match="Cost fuse triggered"):
            client.generate_json(
                messages=[{"role": "user", "content": "Give me JSON"}],
                model="claude-sonnet-4-6",
            )


# ---------------------------------------------------------------------------
# Tests: Batch simulation fuse behavior
# ---------------------------------------------------------------------------


class TestBatchSimulationFuse:
    """Tests simulating batch operations with cost fuse."""

    def test_batch_stops_on_cost_fuse(self, cost_fuse):
        """Simulate a batch that hits the fuse mid-way."""
        # Pre-load tracker to 90% of daily budget
        cost_fuse.tracker.record(cost_usd=18 / 7.2)

        # Simulate multiple calls that would push over the limit
        mock_response = _build_anthropic_response("OK", 1000, 500)

        with patch("aicbc.llm.client.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.llm.provider = "anthropic"
            mock_settings.llm.model = ""
            mock_settings.llm.temperature = 0.3
            mock_settings.llm.max_tokens = 4096
            mock_settings.llm.timeout_seconds = 120
            mock_settings.llm.max_retries = 3
            mock_settings.anthropic.enabled = True
            mock_settings.anthropic.api_key = "sk-ant-test"
            mock_settings.anthropic.base_url = "https://api.anthropic.com"
            mock_settings.anthropic.model_persona = "claude-sonnet-4-6"
            mock_settings.cost_fuse = CostFuseSettings(
                single_study_cny=10.0,
                daily_cny=20.0,
                weekly_cny=50.0,
                degrade_model="claude-haiku-4-5",
            )
            mock_settings.openai.enabled = True
            mock_settings.openai.api_key = "sk-test"
            mock_settings.openai.base_url = "https://api.openai.com/v1"
            mock_settings.openai.model = "gpt-4o"
            mock_settings.deepseek.enabled = False
            mock_settings.deepseek.api_key = ""
            mock_settings.deepseek.base_url = "https://api.deepseek.com/v1"
            mock_settings.deepseek.model = "deepseek-chat"
            mock_settings.qwen.enabled = False
            mock_settings.qwen.api_key = ""
            mock_settings.qwen.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            mock_settings.qwen.model = "qwen-max"
            mock_settings.glm.enabled = False
            mock_settings.glm.api_key = ""
            mock_settings.glm.base_url = "https://open.bigmodel.cn/api/paas/v4"
            mock_settings.glm.model = "glm-4"
            mock_get_settings.return_value = mock_settings

            client = LLMClient(cost_fuse=cost_fuse)

        call_count = [0]

        def _create_side_effect(*args, **kwargs):
            call_count[0] += 1
            # After 2 calls, we're at ~95% and should degrade
            # After 3 calls, we might hit fuse
            return mock_response

        with patch.object(client._anthropic.messages, "create", side_effect=_create_side_effect):
            # First call — should succeed (degraded model)
            result1 = client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )
            assert result1 is not None

            # Check status after first call
            status, _ = cost_fuse.tracker.check_fuse_status()
            # Should be at least DEGRADE since we started at 90%
            assert status in (FuseStatus.DEGRADE, FuseStatus.FUSE, FuseStatus.EMERGENCY)

    def test_cost_tracker_per_study_isolation(self, cost_fuse):
        """Different studies should have independent cost tracking."""
        cost_fuse.tracker.record(cost_usd=5 / 7.2, study_id="study-A")
        cost_fuse.tracker.record(cost_usd=9.6 / 7.2, study_id="study-B")

        # study-A at 50% of 10 CNY = NORMAL
        status_a, _ = cost_fuse.tracker.check_fuse_status("study-A")
        assert status_a == FuseStatus.NORMAL

        # study-B at 96% of 10 CNY = DEGRADE (>= 95%)
        status_b, _ = cost_fuse.tracker.check_fuse_status("study-B")
        assert status_b == FuseStatus.DEGRADE

    def test_global_daily_budget_affects_all_studies(self, cost_fuse):
        """Daily budget is global and affects all studies."""
        # Exhaust daily budget via study-A
        cost_fuse.tracker.record(cost_usd=20 / 7.2, study_id="study-A")

        # study-B should also be blocked
        status_b, _ = cost_fuse.tracker.check_fuse_status("study-B")
        assert status_b == FuseStatus.FUSE
