"""Unified model pricing registry — single source of truth for LLM costs.

Previously LLMClient._COST_PER_1K and ModelRouter.DEFAULT_MODELS each
maintained independent pricing data.  This module consolidates them so
that cost tracking, model routing, and fuse decisions all use consistent
per-model pricing.

Update this file when provider pricing changes; all consumers pick up
the change automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
}

# Provider mapping (model_id → provider)
PROVIDER_MAP: dict[str, str] = {
    "claude-opus-4-6": "anthropic",
    "claude-sonnet-4-6": "anthropic",
    "claude-haiku-4-5": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-4-turbo": "openai",
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
}

# Maximum context window (tokens) — used for routing decisions
MAX_CONTEXT: dict[str, int] = {
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
}

# ── convenience helpers ─────────────────────────────────────────────────


def get_price(model: str) -> tuple[float, float]:
    """Return (input_usd_per_1k, output_usd_per_1k) for *model*."""
    if model not in PRICE_TABLE:
        raise KeyError(f"Unknown model '{model}'. Available: {list(PRICE_TABLE)}")
    return PRICE_TABLE[model]


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost of a single LLM call."""
    inp, out = get_price(model)
    return (prompt_tokens * inp + completion_tokens * out) / 1000.0


def get_provider(model: str) -> str:
    """Return provider name for *model*."""
    if model not in PROVIDER_MAP:
        raise KeyError(f"Unknown model '{model}'")
    return PROVIDER_MAP[model]
