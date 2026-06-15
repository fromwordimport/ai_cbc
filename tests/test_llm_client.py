"""Unit tests for the unified LLM client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from aicbc.llm.client import LLMClient, LLMResponse, Provider, _estimate_cost

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    """Return a fully-populated mock settings object."""
    settings = MagicMock()
    settings.llm.temperature = 0.3
    settings.llm.max_tokens = 4096
    settings.llm.timeout_seconds = 120
    settings.llm.max_retries = 3
    settings.anthropic.api_key = "sk-ant-test"
    settings.anthropic.base_url = "https://api.anthropic.com"
    settings.anthropic.model_persona = "claude-sonnet-4-6"
    settings.openai.api_key = "sk-test"
    settings.openai.base_url = "https://api.openai.com/v1"
    settings.openai.model = "gpt-4o"
    return settings


@pytest.fixture
def client(mock_settings):
    """Return an LLMClient with patched settings."""
    with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
        yield LLMClient()


# ---------------------------------------------------------------------------
# Helper builders
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


def _build_openai_response(content_text: str, prompt_tokens: int, completion_tokens: int):
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


# ---------------------------------------------------------------------------
# Tests: _estimate_cost
# ---------------------------------------------------------------------------


def test_estimate_cost_known_model():
    """Cost estimation should return a positive float for known models."""
    cost = _estimate_cost(Provider.ANTHROPIC, "claude-sonnet-4-6", 1000, 500)
    assert cost > 0


def test_estimate_cost_unknown_model():
    """Cost estimation should return 0.0 for unknown models."""
    cost = _estimate_cost(Provider.OPENAI, "unknown-model", 1000, 500)
    assert cost == 0.0


# ---------------------------------------------------------------------------
# Tests: provider detection
# ---------------------------------------------------------------------------


def test_detect_provider_anthropic():
    """Model names starting with 'claude-' should map to Anthropic."""
    assert LLMClient._detect_provider("claude-sonnet-4-6") == Provider.ANTHROPIC


def test_detect_provider_openai():
    """Model names starting with 'gpt-' should map to OpenAI."""
    assert LLMClient._detect_provider("gpt-4o") == Provider.OPENAI


def test_detect_provider_default():
    """Unknown model names should default to Anthropic."""
    assert LLMClient._detect_provider("some-random-model") == Provider.ANTHROPIC


# ---------------------------------------------------------------------------
# Tests: Anthropic generate
# ---------------------------------------------------------------------------


def test_generate_anthropic_success(client, mock_settings):
    """Successful Anthropic call should return a populated LLMResponse."""
    mock_response = _build_anthropic_response("Hello", 10, 5)

    with patch.object(client._anthropic.messages, "create", return_value=mock_response):
        result = client.generate(
            messages=[{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-6",
            temperature=0.5,
            max_tokens=100,
        )

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello"
    assert result.model == "claude-sonnet-4-6"
    assert result.provider == Provider.ANTHROPIC
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.total_tokens == 15
    assert result.latency_seconds >= 0


def test_generate_anthropic_with_system_message(client):
    """System messages should be extracted and passed to Anthropic correctly."""
    mock_response = _build_anthropic_response("Done", 8, 4)
    create_spy = MagicMock(return_value=mock_response)

    with patch.object(client._anthropic.messages, "create", create_spy):
        client.generate(
            messages=[
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user", "content": "Go"},
            ],
            model="claude-sonnet-4-6",
        )

    call_kwargs = create_spy.call_args.kwargs
    # system is a list of content blocks (Anthropic prompt caching format)
    system_blocks = call_kwargs["system"]
    assert isinstance(system_blocks, list)
    assert any("You are a test assistant." in b.get("text", "") for b in system_blocks)
    assert call_kwargs["messages"] == [{"role": "user", "content": "Go"}]


def test_generate_anthropic_json_mode(client):
    """JSON mode should append a system instruction for Anthropic."""
    mock_response = _build_anthropic_response('{"key":"val"}', 6, 6)
    create_spy = MagicMock(return_value=mock_response)

    with patch.object(client._anthropic.messages, "create", create_spy):
        client.generate(
            messages=[{"role": "user", "content": "Give me JSON"}],
            model="claude-sonnet-4-6",
            json_mode=True,
        )

    call_kwargs = create_spy.call_args.kwargs
    # system is a list of content blocks; check all block texts for the JSON instruction
    system_blocks = call_kwargs["system"]
    assert isinstance(system_blocks, list)
    assert any("You must respond with valid JSON only" in b.get("text", "") for b in system_blocks)


# ---------------------------------------------------------------------------
# Tests: OpenAI generate
# ---------------------------------------------------------------------------


def test_generate_openai_success(client, mock_settings):
    """Successful OpenAI call should return a populated LLMResponse."""
    mock_response = _build_openai_response("World", 20, 10)

    with patch.object(client._openai.chat.completions, "create", return_value=mock_response):
        result = client.generate(
            messages=[{"role": "user", "content": "Hi"}],
            model="gpt-4o",
            temperature=0.7,
            max_tokens=200,
        )

    assert isinstance(result, LLMResponse)
    assert result.content == "World"
    assert result.model == "gpt-4o"
    assert result.provider == Provider.OPENAI
    assert result.prompt_tokens == 20
    assert result.completion_tokens == 10
    assert result.total_tokens == 30


def test_generate_openai_json_mode(client):
    """JSON mode should set response_format for OpenAI."""
    mock_response = _build_openai_response('{"a":1}', 5, 5)
    create_spy = MagicMock(return_value=mock_response)

    with patch.object(client._openai.chat.completions, "create", create_spy):
        client.generate(
            messages=[{"role": "user", "content": "JSON"}],
            model="gpt-4o",
            json_mode=True,
        )

    call_kwargs = create_spy.call_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# Tests: retry / backoff
# ---------------------------------------------------------------------------


def test_generate_retries_and_raises(client, mock_settings):
    """After max_retries failures the client should raise RuntimeError."""
    from anthropic import APIError as AnthropicAPIError

    with (
        patch.object(
            client._anthropic.messages,
            "create",
            side_effect=AnthropicAPIError("Boom", request=MagicMock(), body=None),
        ),
        patch("aicbc.llm.client.time.sleep") as mock_sleep,
        pytest.raises(RuntimeError, match="failed after 3 attempts"),
    ):
        client.generate(
            messages=[{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-6",
        )

    # Exponential backoff: 1s, 2s (2^(1), 2^(2) ... attempt-1)
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)
    mock_sleep.assert_any_call(2)


def test_generate_success_after_retry(client):
    """A transient failure followed by success should return the successful response."""
    from anthropic import APIError as AnthropicAPIError

    mock_response = _build_anthropic_response("Recovered", 4, 4)

    with patch.object(
        client._anthropic.messages,
        "create",
        side_effect=[AnthropicAPIError("Boom", request=MagicMock(), body=None), mock_response],
    ), patch("aicbc.llm.client.time.sleep") as mock_sleep:
        result = client.generate(
            messages=[{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-6",
        )

    assert result.content == "Recovered"
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Tests: generate_json convenience wrapper
# ---------------------------------------------------------------------------


def test_generate_json_parses_response(client):
    """generate_json should parse valid JSON and return a dict."""
    payload = {"name": "Alice", "age": 30}
    mock_response = _build_openai_response(json.dumps(payload), 10, 10)

    with patch.object(client._openai.chat.completions, "create", return_value=mock_response):
        result = client.generate_json(
            messages=[{"role": "user", "content": "Info"}],
            model="gpt-4o",
        )

    assert result == payload


def test_generate_json_raises_on_bad_json(client):
    """generate_json should raise RuntimeError when content is not valid JSON."""
    mock_response = _build_openai_response("not json", 5, 5)

    with (
        patch.object(
            client._openai.chat.completions, "create", return_value=mock_response
        ),
        pytest.raises(RuntimeError, match="Failed to parse LLM response as JSON"),
    ):
        client.generate_json(
            messages=[{"role": "user", "content": "Info"}],
            model="gpt-4o",
        )


# ---------------------------------------------------------------------------
# Tests: unconfigured provider
# ---------------------------------------------------------------------------


def test_unconfigured_anthropic(mock_settings):
    """Using Anthropic without an API key should raise RuntimeError."""
    mock_settings.anthropic.api_key = ""
    with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
        client = LLMClient()

    with pytest.raises(RuntimeError, match="Anthropic client is not configured"):
        client.generate(
            messages=[{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-6",
        )


def test_unconfigured_openai(mock_settings):
    """Using OpenAI without an API key should raise RuntimeError."""
    mock_settings.openai.api_key = ""
    with patch("aicbc.llm.client.get_settings", return_value=mock_settings):
        client = LLMClient()

    with pytest.raises(RuntimeError, match="OpenAI client is not configured"):
        client.generate(
            messages=[{"role": "user", "content": "Hi"}],
            model="gpt-4o",
        )
