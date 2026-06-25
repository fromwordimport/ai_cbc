"""Unified LLM client with retry, logging, cost tracking, and LRU response cache."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
import structlog
from anthropic import Anthropic
from anthropic import APIError as AnthropicAPIError
from openai import APIError as OpenAIAPIError
from openai import OpenAI

from aicbc.config.pricing import estimate_cost_usd
from aicbc.config.settings import get_settings
from aicbc.cost.fuse import CostFuse, CostFuseError

logger = structlog.get_logger("aicbc.llm")

# Default LRU cache size
_DEFAULT_CACHE_SIZE = 128


class Provider(StrEnum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    GLM = "glm"


# Leakage indicators that suggest system prompt content escaped into output
_LEAKAGE_INDICATORS = (
    "你是",
    "系统指令",
    "You are a helpful",
    "System instruction",
    "Constraints:",
    "约束条件",
    "虚拟消费者生成专家",
    "角色定义",
    "张力组合",
)


def _estimate_cost(
    provider: Provider, model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """Estimate API call cost in USD — reads from unified pricing registry."""
    try:
        return estimate_cost_usd(model, prompt_tokens, completion_tokens)
    except KeyError:
        return 0.0


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
    """Unified LLM client supporting Anthropic and OpenAI-compatible providers."""

    def __init__(self, cost_fuse: CostFuse | None = None) -> None:
        """Initialize clients from settings.

        Args:
            cost_fuse: Optional CostFuse instance for cost tracking and
                automatic model degradation. If None, a default fuse is used.
        """
        settings = get_settings()
        self._http_client = httpx.Client(
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            timeout=httpx.Timeout(settings.llm.timeout_seconds),
        )
        self._anthropic: Anthropic | None = None
        self._openai_clients: dict[str, OpenAI] = {}
        self._cost_fuse = cost_fuse or CostFuse()
        self._async_http_client: httpx.AsyncClient | None = None
        self._async_client_lock = asyncio.Lock()

        # LRU response cache (thread-safe)
        self._cache: OrderedDict[str, LLMResponse] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_hits: int = 0
        self._cache_misses: int = 0

        self._refresh_clients()

    def _refresh_clients(self) -> None:
        """Rebuild SDK clients from current settings."""
        settings = get_settings()

        if settings.anthropic.enabled and settings.anthropic.api_key:
            self._anthropic = Anthropic(
                api_key=settings.anthropic.api_key,
                base_url=settings.anthropic.base_url,
                timeout=settings.llm.timeout_seconds,
                http_client=self._http_client,
            )
        else:
            self._anthropic = None

        self._openai_clients = {}
        openai_compatible = {
            Provider.OPENAI: settings.openai,
            Provider.DEEPSEEK: settings.deepseek,
            Provider.QWEN: settings.qwen,
            Provider.GLM: settings.glm,
        }
        for provider, cfg in openai_compatible.items():
            if cfg.enabled and cfg.api_key:
                self._openai_clients[provider.value] = OpenAI(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    timeout=settings.llm.timeout_seconds,
                    http_client=self._http_client,
                )

    def reconfigure(self) -> None:
        """Refresh SDK clients after runtime settings changes."""
        self._refresh_clients()

    def _get_client(self, provider: Provider) -> Anthropic | OpenAI:
        """Return the underlying SDK client for a provider."""
        if provider == Provider.ANTHROPIC:
            if self._anthropic is None:
                raise RuntimeError("Anthropic client is not configured. Set ANTHROPIC_API_KEY.")
            return self._anthropic
        if provider.value in self._openai_clients:
            return self._openai_clients[provider.value]
        raise RuntimeError(
            f"{provider.value} client is not configured. Set the corresponding API key."
        )

    async def _get_async_client(self) -> httpx.AsyncClient:
        """Return a lazily initialized async HTTP client."""
        async with self._async_client_lock:
            if self._async_http_client is None or self._async_http_client.is_closed:
                settings = get_settings()
                self._async_http_client = httpx.AsyncClient(
                    limits=httpx.Limits(
                        max_connections=settings.llm.http_max_connections,
                        max_keepalive_connections=settings.llm.http_max_keepalive,
                    ),
                    timeout=httpx.Timeout(settings.llm.timeout_seconds),
                )
            return self._async_http_client

    async def aclose(self) -> None:
        """Close the async HTTP client if initialized."""
        if self._async_http_client is not None and not self._async_http_client.is_closed:
            await self._async_http_client.aclose()

    @staticmethod
    def _detect_provider(model: str) -> Provider:
        """Detect provider from model name or active settings."""
        model_lower = model.lower()
        if model_lower.startswith("claude-"):
            return Provider.ANTHROPIC
        if model_lower.startswith("gpt-"):
            return Provider.OPENAI
        if "deepseek" in model_lower:
            return Provider.DEEPSEEK
        if "qwen" in model_lower:
            return Provider.QWEN
        if "glm" in model_lower:
            return Provider.GLM

        # Fall back to the user's explicit provider choice.
        settings = get_settings()
        active = settings.llm.provider.lower()
        if active in {p.value for p in Provider}:
            return Provider(active)
        # Preserve backward compatibility for unknown models.
        return Provider.ANTHROPIC

    @staticmethod
    def _default_model_for_provider(provider: Provider) -> str:
        """Return the default model for a provider from settings."""
        settings = get_settings()
        if provider == Provider.ANTHROPIC:
            return settings.anthropic.model_persona
        if provider == Provider.OPENAI:
            return settings.openai.model
        if provider == Provider.DEEPSEEK:
            return settings.deepseek.model
        if provider == Provider.QWEN:
            return settings.qwen.model
        if provider == Provider.GLM:
            return settings.glm.model
        return settings.anthropic.model_persona

    @property
    def _openai(self) -> OpenAI | None:
        """Backward-compatible accessor for the OpenAI SDK client."""
        return self._openai_clients.get(Provider.OPENAI.value)

    # ------------------------------------------------------------------
    # Response cache (LRU, thread-safe)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(
        provider: Provider,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        """Build a deterministic cache key from provider, model, and message content.

        Only hashes system and user prompts -- completion content and metadata
        (temperature, max_tokens) are intentionally excluded so that identical
        prompts from different call sites share cache entries.
        """
        system_prompts: list[str] = []
        user_prompts: list[str] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_prompts.append(content)
            elif role == "user":
                user_prompts.append(content)

        seed = f"{provider.value}|{model}|{hashlib.sha256('|'.join(system_prompts).encode()).hexdigest()}|{hashlib.sha256('|'.join(user_prompts).encode()).hexdigest()}"
        return hashlib.sha256(seed.encode()).hexdigest()

    @property
    def cache_hits(self) -> int:
        """Number of cache hits since initialization or last clear."""
        return self._cache_hits

    @property
    def cache_misses(self) -> int:
        """Number of cache misses since initialization or last clear."""
        return self._cache_misses

    @property
    def cache_size(self) -> int:
        """Current number of entries in the cache."""
        with self._cache_lock:
            return len(self._cache)

    def _store_in_cache(self, cache_key: str, response: LLMResponse) -> None:
        """Store an LLMResponse in the LRU cache (thread-safe).

        Evicts the oldest entry if the cache has reached max_size.
        """
        with self._cache_lock:
            if cache_key in self._cache:
                # Already cached (possible race); move to end
                self._cache.move_to_end(cache_key)
                return
            if len(self._cache) >= _DEFAULT_CACHE_SIZE:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug("llm_cache_evicted", evicted_key=evicted_key[:16])
            self._cache[cache_key] = response

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
            # Ephemeral cache: CBC system prompts (~2000 tokens) repeat
            # across choice sets.  Caching saves 60-80% of system-prompt cost.
            kwargs["system"] = [
                {"type": "text", "text": system_msg, "cache_control": {"type": "ephemeral"}}
            ]
        if json_mode:
            extra = "\nYou must respond with valid JSON only."
            if system_msg:
                kwargs["system"].append(
                    {"type": "text", "text": extra, "cache_control": {"type": "ephemeral"}}
                )
            else:
                kwargs["system"] = [
                    {"type": "text", "text": extra, "cache_control": {"type": "ephemeral"}}
                ]
            # Prefill the assistant response with "{" to force valid JSON output
            # instead of relying on a textual instruction alone.
            chat_messages.append({"role": "assistant", "content": "{"})

        response = client.messages.create(**kwargs)
        latency = time.perf_counter() - start

        content = ""
        if response.content:
            raw = response.content[0]
            content = raw.text if hasattr(raw, "text") else str(raw)
            # Strip markdown code fences if present
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

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
            estimated_cost_usd=_estimate_cost(
                Provider.ANTHROPIC, model, prompt_tokens, completion_tokens
            ),
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
            estimated_cost_usd=_estimate_cost(
                Provider.OPENAI, model, prompt_tokens, completion_tokens
            ),
            latency_seconds=latency,
            raw_response=response,
        )

    async def _call_anthropic_async(
        self,
        client: Anthropic,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> LLMResponse:
        """Async Anthropic API call via thread-pool offload of the synchronous path."""
        from anthropic import AsyncAnthropic

        settings = get_settings()
        async_client = AsyncAnthropic(  # noqa: F841
            api_key=settings.anthropic.api_key,
            base_url=settings.anthropic.base_url,
            timeout=settings.llm.timeout_seconds,
            http_client=await self._get_async_client(),
        )
        return await asyncio.to_thread(
            self._call_anthropic,
            client=client,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    async def _call_openai_async(
        self,
        client: OpenAI,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> LLMResponse:
        """Async OpenAI-compatible API call via thread-pool offload of the synchronous path."""
        return await asyncio.to_thread(
            self._call_openai,
            client=client,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    def _execute_generate_attempt(
        self,
        resolved_provider: Provider,
        resolved_model: str,
        messages: list[dict[str, str]],
        resolved_temperature: float,
        resolved_max_tokens: int,
        json_mode: bool,
        study_id: str | None,
        model: str | None,
        active_model: str,
        cache_key: str,
        max_retries: int,
        call_provider: Callable[[], LLMResponse],
        sleep_fn: Callable[[float], None],
    ) -> LLMResponse:
        """Common retry logic for generate (sync path)."""
        log = logger.bind(
            provider=resolved_provider.value,
            model=resolved_model,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            json_mode=json_mode,
        )
        last_exception: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                log.info("llm_request_start", attempt=attempt, message_count=len(messages))

                result = call_provider()

                log.info(
                    "llm_request_success",
                    attempt=attempt,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.total_tokens,
                    estimated_cost_usd=round(result.estimated_cost_usd, 6),
                    latency_seconds=round(result.latency_seconds, 3),
                )
                # SEC-011: Detect prompt leakage in response content
                leaked, indicator = self._detect_prompt_leakage(result.content)
                if leaked:
                    log.warning(
                        "prompt_leakage_detected",
                        indicator=indicator,
                        content_preview=result.content[:200],
                    )
                    # Return a sanitized response instead of the leaked content
                    return LLMResponse(
                        content="[SECURITY: Response contained potentially leaked system instructions and was blocked. Please retry.]",
                        model=result.model,
                        provider=result.provider,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=0,
                        total_tokens=result.prompt_tokens,
                        estimated_cost_usd=result.estimated_cost_usd,
                        latency_seconds=result.latency_seconds,
                        raw_response=None,  # Do not propagate leaked response
                    )

                # Post-call cost recording
                self._cost_fuse.record_call(
                    result,
                    study_id=study_id,
                    task_phase="llm_generate",
                    degraded=(resolved_model != (model or active_model)),
                )
                # Store in LRU cache
                self._store_in_cache(cache_key, result)
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
                    sleep_fn(sleep_seconds)

        raise RuntimeError(
            f"LLM API call failed after {max_retries} attempts: {last_exception}"
        ) from last_exception

    async def _execute_generate_attempt_async(
        self,
        resolved_provider: Provider,
        resolved_model: str,
        messages: list[dict[str, str]],
        resolved_temperature: float,
        resolved_max_tokens: int,
        json_mode: bool,
        study_id: str | None,
        model: str | None,
        active_model: str,
        cache_key: str,
        max_retries: int,
        call_provider: Callable[[], Awaitable[LLMResponse]],
        sleep_fn: Callable[[float], Awaitable[None]],
    ) -> LLMResponse:
        """Common retry logic for generate (async path)."""
        log = logger.bind(
            provider=resolved_provider.value,
            model=resolved_model,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            json_mode=json_mode,
        )
        last_exception: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                log.info("llm_request_start", attempt=attempt, message_count=len(messages))

                result = await call_provider()

                log.info(
                    "llm_request_success",
                    attempt=attempt,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.total_tokens,
                    estimated_cost_usd=round(result.estimated_cost_usd, 6),
                    latency_seconds=round(result.latency_seconds, 3),
                )
                # SEC-011: Detect prompt leakage in response content
                leaked, indicator = self._detect_prompt_leakage(result.content)
                if leaked:
                    log.warning(
                        "prompt_leakage_detected",
                        indicator=indicator,
                        content_preview=result.content[:200],
                    )
                    # Return a sanitized response instead of the leaked content
                    return LLMResponse(
                        content="[SECURITY: Response contained potentially leaked system instructions and was blocked. Please retry.]",
                        model=result.model,
                        provider=result.provider,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=0,
                        total_tokens=result.prompt_tokens,
                        estimated_cost_usd=result.estimated_cost_usd,
                        latency_seconds=result.latency_seconds,
                        raw_response=None,  # Do not propagate leaked response
                    )

                # Post-call cost recording
                self._cost_fuse.record_call(
                    result,
                    study_id=study_id,
                    task_phase="llm_generate",
                    degraded=(resolved_model != (model or active_model)),
                )
                # Store in LRU cache
                self._store_in_cache(cache_key, result)
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
                    await sleep_fn(sleep_seconds)

        raise RuntimeError(
            f"LLM API call failed after {max_retries} attempts: {last_exception}"
        ) from last_exception

    def generate(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        provider: Provider | None = None,
        study_id: str | None = None,
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
        active_provider = self._detect_provider(settings.llm.model or "")
        active_model = self._default_model_for_provider(active_provider)
        resolved_model = model or settings.llm.model or active_model
        resolved_temperature = temperature if temperature is not None else settings.llm.temperature
        resolved_max_tokens = max_tokens if max_tokens is not None else settings.llm.max_tokens
        resolved_provider = provider or self._detect_provider(resolved_model)

        # ------------------------------------------------------------------
        # Cache check (before cost fuse -- cached responses incur no new cost)
        # ------------------------------------------------------------------
        cache_key = self._make_cache_key(resolved_provider, resolved_model, messages)
        with self._cache_lock:
            if cache_key in self._cache:
                self._cache_hits += 1
                cached = self._cache[cache_key]
                # Move to end (LRU promotion)
                self._cache.move_to_end(cache_key)
                logger.debug(
                    "llm_cache_hit",
                    provider=resolved_provider.value,
                    model=resolved_model,
                    total_hits=self._cache_hits,
                    total_misses=self._cache_misses,
                )
                return cached
            self._cache_misses += 1

        # ------------------------------------------------------------------
        # Cost fuse check (pre-call)
        # ------------------------------------------------------------------
        allowed, fuse_status, effective_model = self._cost_fuse.pre_call_check(
            study_id=study_id,
            requested_model=resolved_model,
        )
        if not allowed:
            raise CostFuseError(
                f"Cost fuse triggered ({fuse_status.value}): LLM call blocked. "
                "Please contact project lead (小P) to review budget."
            )
        # Use degraded model if fuse returned one
        if effective_model and effective_model != resolved_model:
            resolved_model = effective_model
            resolved_provider = self._detect_provider(resolved_model)
            log_degrade = logger.bind(
                original_model=model,
                degraded_model=resolved_model,
                fuse_status=fuse_status.value,
            )
            log_degrade.warning("llm_model_degraded_by_cost_fuse")

        client = self._get_client(resolved_provider)
        max_retries = settings.llm.max_retries

        def _call_provider() -> LLMResponse:
            if resolved_provider == Provider.ANTHROPIC:
                return self._call_anthropic(
                    client=client,  # type: ignore[arg-type]
                    model=resolved_model,
                    messages=messages,
                    temperature=resolved_temperature,
                    max_tokens=resolved_max_tokens,
                    json_mode=json_mode,
                )
            return self._call_openai(
                client=client,  # type: ignore[arg-type]
                model=resolved_model,
                messages=messages,
                temperature=resolved_temperature,
                max_tokens=resolved_max_tokens,
                json_mode=json_mode,
            )

        return self._execute_generate_attempt(
            resolved_provider=resolved_provider,
            resolved_model=resolved_model,
            messages=messages,
            resolved_temperature=resolved_temperature,
            resolved_max_tokens=resolved_max_tokens,
            json_mode=json_mode,
            study_id=study_id,
            model=model,
            active_model=active_model,
            cache_key=cache_key,
            max_retries=max_retries,
            call_provider=_call_provider,
            sleep_fn=time.sleep,
        )

    async def generate_async(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        provider: Provider | None = None,
        study_id: str | None = None,
    ) -> LLMResponse:
        """Generate a completion asynchronously with unified interface and retries.

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
        active_provider = self._detect_provider(settings.llm.model or "")
        active_model = self._default_model_for_provider(active_provider)
        resolved_model = model or settings.llm.model or active_model
        resolved_temperature = temperature if temperature is not None else settings.llm.temperature
        resolved_max_tokens = max_tokens if max_tokens is not None else settings.llm.max_tokens
        resolved_provider = provider or self._detect_provider(resolved_model)

        # ------------------------------------------------------------------
        # Cache check (before cost fuse -- cached responses incur no new cost)
        # ------------------------------------------------------------------
        cache_key = self._make_cache_key(resolved_provider, resolved_model, messages)
        with self._cache_lock:
            if cache_key in self._cache:
                self._cache_hits += 1
                cached = self._cache[cache_key]
                # Move to end (LRU promotion)
                self._cache.move_to_end(cache_key)
                logger.debug(
                    "llm_cache_hit",
                    provider=resolved_provider.value,
                    model=resolved_model,
                    total_hits=self._cache_hits,
                    total_misses=self._cache_misses,
                )
                return cached
            self._cache_misses += 1

        # ------------------------------------------------------------------
        # Cost fuse check (pre-call)
        # ------------------------------------------------------------------
        allowed, fuse_status, effective_model = self._cost_fuse.pre_call_check(
            study_id=study_id,
            requested_model=resolved_model,
        )
        if not allowed:
            raise CostFuseError(
                f"Cost fuse triggered ({fuse_status.value}): LLM call blocked. "
                "Please contact project lead (小P) to review budget."
            )
        # Use degraded model if fuse returned one
        if effective_model and effective_model != resolved_model:
            resolved_model = effective_model
            resolved_provider = self._detect_provider(resolved_model)
            log_degrade = logger.bind(
                original_model=model,
                degraded_model=resolved_model,
                fuse_status=fuse_status.value,
            )
            log_degrade.warning("llm_model_degraded_by_cost_fuse")

        client = self._get_client(resolved_provider)
        max_retries = settings.llm.max_retries

        async def _call_provider() -> LLMResponse:
            if resolved_provider == Provider.ANTHROPIC:
                return await self._call_anthropic_async(
                    client=client,  # type: ignore[arg-type]
                    model=resolved_model,
                    messages=messages,
                    temperature=resolved_temperature,
                    max_tokens=resolved_max_tokens,
                    json_mode=json_mode,
                )
            return await self._call_openai_async(
                client=client,  # type: ignore[arg-type]
                model=resolved_model,
                messages=messages,
                temperature=resolved_temperature,
                max_tokens=resolved_max_tokens,
                json_mode=json_mode,
            )

        return await self._execute_generate_attempt_async(
            resolved_provider=resolved_provider,
            resolved_model=resolved_model,
            messages=messages,
            resolved_temperature=resolved_temperature,
            resolved_max_tokens=resolved_max_tokens,
            json_mode=json_mode,
            study_id=study_id,
            model=model,
            active_model=active_model,
            cache_key=cache_key,
            max_retries=max_retries,
            call_provider=_call_provider,
            sleep_fn=asyncio.sleep,
        )

    def _detect_prompt_leakage(self, content: str) -> tuple[bool, str | None]:
        """Detect if the LLM response contains leaked system prompt content.

        Returns (leaked, matched_indicator).
        """
        if not content:
            return False, None
        content_lower = content.lower()
        for indicator in _LEAKAGE_INDICATORS:
            if indicator.lower() in content_lower:
                return True, indicator
        return False, None

    def generate_json(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        provider: Provider | None = None,
        study_id: str | None = None,
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
            study_id=study_id,
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
