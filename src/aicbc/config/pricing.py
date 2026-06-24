"""Unified model pricing registry — single source of truth for LLM costs.

Previously LLMClient._COST_PER_1K and ModelRouter.DEFAULT_MODELS each
maintained independent pricing data.  This module consolidates them so
that cost tracking and model routing all use consistent per-model pricing.

Update this file when provider pricing changes; all consumers pick up the
change automatically.
"""

from __future__ import annotations

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
