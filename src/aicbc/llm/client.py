"""Unified LLM client with retry, logging, and cost tracking."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog
from anthropic import Anthropic
from anthropic import APIError as AnthropicAPIError
from openai import APIError as OpenAIAPIError
from openai import OpenAI

from aicbc.config.settings import get_settings

logger = structlog.get_logger("aicbc.llm")


class Provider(StrEnum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


# Approximate cost per 1K tokens (USD) — update as pricing changes.
_COST_PER_1K: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-haiku-4-5": (0.25, 1.25),
        "claude-opus-4-6": (15.0, 75.0),
    },
    "openai": {
        "gpt-4o": (5.0, 15.0),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.0, 30.0),
    },
}


def _estimate_cost(provider: Provider, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate API call cost in USD."""
    pricing = _COST_PER_1K.get(provider.value, {}).get(model)
    if pricing is None:
        return 0.0
    input_price, output_price = pricing
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1000.0


@dataclass(frozen=True)
class LLMResponse:
    """Structured LLM response."""

    content: str
    model: str
    provider: Provider
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    latency_seconds: float
    raw_response: Any | None = None


class LLMClient:
    """Unified LLM client supporting Anthropic and OpenAI with retries and logging."""

    def __init__(self) -> None:
        """Initialize clients from settings."""
        settings = get_settings()
        self._anthropic: Anthropic | None = None
        self._openai: OpenAI | None = None

        if settings.anthropic.api_key:
            self._anthropic = Anthropic(
                api_key=settings.anthropic.api_key,
                base_url=settings.anthropic.base_url,
                timeout=settings.llm.timeout_seconds,
            )
        if settings.openai.api_key:
            self._openai = OpenAI(
                api_key=settings.openai.api_key,
                base_url=settings.openai.base_url,
                timeout=settings.llm.timeout_seconds,
            )

    def _get_client(self, provider: Provider) -> Anthropic | OpenAI:
        """Return the underlying SDK client for a provider."""
        if provider == Provider.ANTHROPIC:
            if self._anthropic is None:
                raise RuntimeError("Anthropic client is not configured. Set ANTHROPIC_API_KEY.")
            return self._anthropic
        if provider == Provider.OPENAI:
            if self._openai is None:
                raise RuntimeError("OpenAI client is not configured. Set OPENAI_API_KEY.")
            return self._openai
        raise ValueError(f"Unknown provider: {provider}")

    @staticmethod
    def _detect_provider(model: str) -> Provider:
        """Detect provider from model name."""
        model_lower = model.lower()
        if model_lower.startswith("claude-"):
            return Provider.ANTHROPIC
        if model_lower.startswith("gpt-"):
            return Provider.OPENAI
        # Default to anthropic for unknown models to preserve backward compat.
        return Provider.ANTHROPIC

    def _call_anthropic(
        self,
        client: Anthropic,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> LLMResponse:
        """Execute a single Anthropic API call."""
        start = time.perf_counter()

        # Anthropic uses "user" / "assistant" roles natively.
        system_msg = ""
        chat_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                chat_messages.append({"role": msg["role"], "content": msg["content"]})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_msg:
            kwargs["system"] = system_msg
        if json_mode:
            kwargs["system"] = (kwargs.get("system", "") + "\nYou must respond with valid JSON only.").strip()

        response = client.messages.create(**kwargs)
        latency = time.perf_counter() - start

        content = ""
        if response.content:
            content = response.content[0].text if hasattr(response.content[0], "text") else str(response.content[0])

        usage = response.usage
        prompt_tokens = usage.input_tokens if usage else 0
        completion_tokens = usage.output_tokens if usage else 0

        return LLMResponse(
            content=content,
            model=model,
            provider=Provider.ANTHROPIC,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_usd=_estimate_cost(Provider.ANTHROPIC, model, prompt_tokens, completion_tokens),
            latency_seconds=latency,
            raw_response=response,
        )

    def _call_openai(
        self,
        client: OpenAI,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> LLMResponse:
        """Execute a single OpenAI API call."""
        start = time.perf_counter()

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - start

        choice = response.choices[0]
        content = choice.message.content or ""

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        return LLMResponse(
            content=content,
            model=model,
            provider=Provider.OPENAI,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_usd=_estimate_cost(Provider.OPENAI, model, prompt_tokens, completion_tokens),
            latency_seconds=latency,
            raw_response=response,
        )

    def generate(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        provider: Provider | None = None,
    ) -> LLMResponse:
        """Generate a completion with unified interface and exponential backoff retries.

        Args:
            messages: List of message dicts with "role" and "content" keys.
            model: Model identifier. Defaults to ANTHROPIC_MODEL_PERSONA from settings.
            temperature: Sampling temperature. Defaults to LLM_TEMPERATURE from settings.
            max_tokens: Max tokens to generate. Defaults to LLM_MAX_TOKENS from settings.
            json_mode: Whether to request JSON-only output.
            provider: Explicit provider override. Auto-detected from model name if omitted.

        Returns:
            Structured LLMResponse.

        Raises:
            RuntimeError: If the API call fails after all retries.
        """
        settings = get_settings()
        resolved_model = model or settings.anthropic.model_persona
        resolved_temperature = temperature if temperature is not None else settings.llm.temperature
        resolved_max_tokens = max_tokens if max_tokens is not None else settings.llm.max_tokens
        resolved_provider = provider or self._detect_provider(resolved_model)

        client = self._get_client(resolved_provider)
        max_retries = settings.llm.max_retries
        last_exception: Exception | None = None

        log = logger.bind(
            provider=resolved_provider.value,
            model=resolved_model,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            json_mode=json_mode,
        )

        for attempt in range(1, max_retries + 1):
            try:
                log.info("llm_request_start", attempt=attempt, message_count=len(messages))

                if resolved_provider == Provider.ANTHROPIC:
                    result = self._call_anthropic(
                        client=client,  # type: ignore[arg-type]
                        model=resolved_model,
                        messages=messages,
                        temperature=resolved_temperature,
                        max_tokens=resolved_max_tokens,
                        json_mode=json_mode,
                    )
                else:
                    result = self._call_openai(
                        client=client,  # type: ignore[arg-type]
                        model=resolved_model,
                        messages=messages,
                        temperature=resolved_temperature,
                        max_tokens=resolved_max_tokens,
                        json_mode=json_mode,
                    )

                log.info(
                    "llm_request_success",
                    attempt=attempt,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.total_tokens,
                    estimated_cost_usd=round(result.estimated_cost_usd, 6),
                    latency_seconds=round(result.latency_seconds, 3),
                )
                return result

            except (AnthropicAPIError, OpenAIAPIError) as exc:
                last_exception = exc
                log.warning(
                    "llm_request_error",
                    attempt=attempt,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                if attempt < max_retries:
                    sleep_seconds = 2 ** (attempt - 1)
                    log.info("llm_retry_backoff", sleep_seconds=sleep_seconds)
                    time.sleep(sleep_seconds)

        raise RuntimeError(
            f"LLM API call failed after {max_retries} attempts: {last_exception}"
        ) from last_exception

    def generate_json(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        provider: Provider | None = None,
    ) -> dict[str, Any]:
        """Convenience wrapper that parses the response content as JSON.

        Args:
            messages: List of message dicts.
            model: Model identifier.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate.
            provider: Explicit provider override.

        Returns:
            Parsed JSON dict.

        Raises:
            RuntimeError: If the API call fails or JSON parsing fails.
        """
        response = self.generate(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            provider=provider,
        )
        try:
            return json.loads(response.content)
        except json.JSONDecodeError as exc:
            logger.error(
                "llm_json_parse_error",
                content=response.content[:500],
                error=str(exc),
            )
            raise RuntimeError(f"Failed to parse LLM response as JSON: {exc}") from exc
