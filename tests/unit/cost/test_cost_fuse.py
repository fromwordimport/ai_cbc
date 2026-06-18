"""Unit tests for CostFuse and LLMClient cost integration.

All LLM calls are mocked — no real API requests are made.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from unittest.mock import MagicMock, patch

from aicbc.config.settings import CostFuseSettings
from aicbc.cost.fuse import CostFuse, CostFuseError, DegradationLevel
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
    """Fresh CostTracker with tight settings."""
    t = CostTracker(settings=tight_fuse_settings)
    t.reset()
    return t


@pytest.fixture
def cost_fuse(cost_tracker):
    """Fresh CostFuse wrapping the tracker."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
# Tests: CostFuse high-level wrapper
# ---------------------------------------------------------------------------


class TestCostFuse:
    """Tests for CostFuse high-level wrapper."""

    def test_pre_call_check_normal(self, cost_fuse):
        """Normal state should allow call with requested model."""
        allowed, status, model = cost_fuse.pre_call_check(
            study_id="study-001",
            requested_model="claude-sonnet-4-6",
        )
        assert allowed is True
        assert status == FuseStatus.NORMAL
        assert model == "claude-sonnet-4-6"

    def test_pre_call_check_degrade(self, cost_fuse):
        """DEGRADE state should allow call but switch model."""
        # Push to 95%
        cost_fuse.tracker.record(cost_usd=95 / 7.2, study_id="study-001")
        allowed, status, model = cost_fuse.pre_call_check(
            study_id="study-001",
            requested_model="claude-sonnet-4-6",
        )
        assert allowed is True
        assert status == FuseStatus.DEGRADE
        assert model == "claude-haiku-4-5"  # degraded model

    def test_pre_call_check_fuse_blocks(self, cost_fuse):
        """FUSE state should block calls."""
        cost_fuse.tracker.record(cost_usd=100 / 7.2, study_id="study-001")
        allowed, status, model = cost_fuse.pre_call_check(
            study_id="study-001",
            requested_model="claude-sonnet-4-6",
        )
        assert allowed is False
        assert status == FuseStatus.FUSE

    def test_pre_call_check_emergency_blocks(self, cost_fuse):
        """EMERGENCY state should block calls."""
        cost_fuse.tracker.record(cost_usd=120 / 7.2, study_id="study-001")
        allowed, status, model = cost_fuse.pre_call_check(
            study_id="study-001",
            requested_model="claude-sonnet-4-6",
        )
        assert allowed is False
        assert status == FuseStatus.EMERGENCY

    def test_record_call(self, cost_fuse):
        """record_call should extract data from mock response."""
        response = _make_mock_response(cost_usd=0.01)
        cost_fuse.record_call(
            response,
            study_id="study-001",
            persona_id="persona-001",
            task_phase="generation",
        )

        assert cost_fuse.tracker.get_study_cost("study-001") > 0

    def test_get_degradation_level(self, cost_fuse):
        """Degradation level should match fuse status."""
        assert cost_fuse.get_degradation_level("study-001") == DegradationLevel.STANDARD

        cost_fuse.tracker.record(cost_usd=95 / 7.2, study_id="study-001")
        assert cost_fuse.get_degradation_level("study-001") == DegradationLevel.DEGRADED

        cost_fuse.tracker.record(cost_usd=30 / 7.2, study_id="study-001")  # now 125%
        assert cost_fuse.get_degradation_level("study-001") == DegradationLevel.EMERGENCY

    def test_resolve_model_normal(self, cost_fuse):
        """Normal state should return requested model."""
        model = cost_fuse.resolve_model("claude-sonnet-4-6", study_id="study-001")
        assert model == "claude-sonnet-4-6"

    def test_resolve_model_degraded(self, cost_fuse):
        """Degraded state should return degrade_model."""
        cost_fuse.tracker.record(cost_usd=95 / 7.2, study_id="study-001")
        model = cost_fuse.resolve_model("claude-sonnet-4-6", study_id="study-001")
        assert model == "claude-haiku-4-5"


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
