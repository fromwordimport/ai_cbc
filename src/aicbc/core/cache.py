"""Simple in-memory TTL cache for single-worker deployments.

Render free tier runs a single uvicorn worker, so a process-local cache is
sufficient for reducing MongoDB round-trips on read-heavy endpoints without
introducing Redis complexity.
"""

from __future__ import annotations

import time
from typing import Any

from aicbc.config.settings import get_settings


class TimedCache:
    """Dict-based cache with per-entry TTL."""

    def __init__(self, ttl_seconds: float) -> None:
        self.ttl = ttl_seconds
        self._store: dict[Any, tuple[Any, float]] = {}

    def _enabled(self) -> bool:
        """Disable caching in test environments to avoid stale-state flakes."""
        env = get_settings().environment.lower()
        return env not in ("testing", "test") and self.ttl > 0

    def get(self, key: Any) -> Any | None:
        """Return cached value if still fresh."""
        if not self._enabled():
            return None
        value, expires = self._store.get(key, (None, 0.0))
        if time.monotonic() < expires:
            return value
        self._store.pop(key, None)
        return None

    def set(self, key: Any, value: Any) -> None:
        """Store value with TTL."""
        if not self._enabled():
            return
        self._store[key] = (value, time.monotonic() + self.ttl)

    def clear(self) -> None:
        """Evict all entries."""
        self._store.clear()


# Process-local caches for high-traffic read endpoints.
_dashboard_summary_cache = TimedCache(ttl_seconds=10)
_studies_list_cache = TimedCache(ttl_seconds=10)
_personas_list_cache = TimedCache(ttl_seconds=10)


def get_dashboard_summary_cache() -> TimedCache:
    return _dashboard_summary_cache


def get_studies_list_cache() -> TimedCache:
    return _studies_list_cache


def get_personas_list_cache() -> TimedCache:
    return _personas_list_cache


def invalidate_dashboard_summary() -> None:
    _dashboard_summary_cache.clear()


def invalidate_studies_list() -> None:
    _studies_list_cache.clear()


def invalidate_personas_list() -> None:
    _personas_list_cache.clear()
