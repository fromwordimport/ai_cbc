"""Tests for LLM async client path."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from aicbc.llm.client import LLMClient


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
    settings.llm.http_max_connections = 20
    settings.llm.http_max_keepalive = 10
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
    return settings


@pytest.mark.asyncio
async def test_llm_client_has_async_client(mock_settings) -> None:
    with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
        client = LLMClient()
        async_client = await client._get_async_client()
        assert isinstance(async_client, httpx.AsyncClient)
        await client.aclose()


@pytest.mark.asyncio
async def test_generate_async_does_not_block_event_loop(mock_settings) -> None:
    from anthropic import AuthenticationError

    with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
        client = LLMClient()

    # Mock the underlying sync call so we fail fast on auth (not after retries).
    mock_response = MagicMock()
    mock_response.status_code = 401
    auth_error = AuthenticationError(
        "invalid api key", response=mock_response, body=None
    )
    with patch.object(client, "_call_anthropic", side_effect=auth_error):
        # Without a real API key this will raise, but it should fail on auth/network,
        # not on "no running event loop" or thread-pool exhaustion.
        with pytest.raises(RuntimeError) as exc_info:
            await client.generate_async(messages=[{"role": "user", "content": "hello"}])
        assert "no running event loop" not in str(exc_info.value).lower()
        assert "AuthenticationError" in str(exc_info.value) or "invalid api key" in str(exc_info.value)
