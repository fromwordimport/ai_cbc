"""Unified model pricing registry — single source of truth for LLM costs.

Previously LLMClient._COST_PER_1K and ModelRouter.DEFAULT_MODELS each
maintained independent pricing data.  This module consolidates them so
that cost tracking, model routing, and fuse decisions all use consistent
per-model pricing.

Update this file when provider pricing changes; all consumers pick up
the change automatically.
"""

from __future__ import annotations

from typing import Literal

import structlog

logger = structlog.get_logger("aicbc.config.pricing")

# ── per-1K-token prices in USD ──────────────────────────────────────────
# Format: { model_id: (input_price_per_1k, output_price_per_1k) }
# Prices are per 1 000 tokens as quoted by the provider.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.25, 1.25),
    # OpenAI
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    # OpenAI-compatible providers (placeholder pricing — update when official)
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.55, 2.19),
    "qwen-max": (0.50, 1.00),
    "glm-4": (0.50, 1.00),
}

# Provider mapping (model_id → provider)
PROVIDER_MAP: dict[str, str] = {
    "claude-opus-4-6": "anthropic",
    "claude-sonnet-4-6": "anthropic",
    "claude-haiku-4-5": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-4-turbo": "openai",
    "deepseek-chat": "deepseek",
    "deepseek-reasoner": "deepseek",
    "qwen-max": "qwen",
    "glm-4": "glm",
}

# Quality tier — used by ModelRouter for degradation decisions
QualityTier = Literal["highest", "high", "medium", "fallback"]

QUALITY_TIER: dict[str, QualityTier] = {
    "claude-opus-4-6": "highest",
    "claude-sonnet-4-6": "high",
    "gpt-4o": "high",
    "claude-haiku-4-5": "medium",
    "gpt-4o-mini": "medium",
    "gpt-4-turbo": "medium",
    "deepseek-chat": "high",
    "deepseek-reasoner": "high",
    "qwen-max": "high",
    "glm-4": "high",
}

# Maximum context window (tokens) — used for routing decisions
MAX_CONTEXT: dict[str, int] = {
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "deepseek-chat": 64_000,
    "deepseek-reasoner": 64_000,
    "qwen-max": 32_000,
    "glm-4": 128_000,
}

# ── convenience helpers ─────────────────────────────────────────────────


def get_price(model: str) -> tuple[float, float]:
    """Return (input_usd_per_1k, output_usd_per_1k) for *model*."""
    if model not in PRICE_TABLE:
        raise KeyError(f"Unknown model '{model}'. Available: {list(PRICE_TABLE)}")
    return PRICE_TABLE[model]


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost of a single LLM call.

    Falls back to 0 for unknown models rather than raising, so custom or
    newly-added models do not block the pipeline.
    """
    try:
        inp, out = get_price(model)
    except KeyError:
        logger.warning("unknown_model_price", model=model, fallback=0.0)
        return 0.0
    return (prompt_tokens * inp + completion_tokens * out) / 1000.0


def get_provider(model: str) -> str:
    """Return provider name for *model*."""
    if model not in PROVIDER_MAP:
        raise KeyError(f"Unknown model '{model}'")
    return PROVIDER_MAP[model]
