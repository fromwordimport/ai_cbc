"""Pluggable TTL cache for single-worker or multi-worker deployments."""

from __future__ import annotations

import time
from typing import Any, Protocol

from aicbc.config.settings import get_settings


class CacheBackend(Protocol):
    """Cache backend protocol."""

    def get(self, key: Any) -> Any | None: ...
    def set(self, key: Any, value: Any, ttl_seconds: float) -> None: ...
    def clear(self) -> None: ...


class _MemoryBackend:
    """Process-local dict-based cache."""

    def __init__(self) -> None:
        self._store: dict[Any, tuple[Any, float]] = {}

    def get(self, key: Any) -> Any | None:
        value, expires = self._store.get(key, (None, 0.0))
        if time.monotonic() < expires:
            return value
        self._store.pop(key, None)
        return None

    def set(self, key: Any, value: Any, ttl_seconds: float) -> None:
        self._store[key] = (value, time.monotonic() + ttl_seconds)

    def clear(self) -> None:
        self._store.clear()


class _RedisBackend:
    """Redis-backed shared cache."""

    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.from_url(redis_url, decode_responses=True)

    def _encode(self, key: Any) -> str:
        return f"aicbc:cache:{hash(key)}"

    def get(self, key: Any) -> Any | None:
        import json

        raw = self._client.get(self._encode(key))
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, key: Any, value: Any, ttl_seconds: float) -> None:
        import json

        self._client.setex(self._encode(key), int(ttl_seconds), json.dumps(value))

    def clear(self) -> None:
        for key in self._client.scan_iter(match="aicbc:cache:*"):
            self._client.delete(key)


class TimedCache:
    """Cache with pluggable backend."""

    def __init__(self, ttl_seconds: float, backend: CacheBackend | None = None) -> None:
        self.ttl = ttl_seconds
        self._backend = backend or _MemoryBackend()
        self._hits = 0
        self._misses = 0

    @property
    def hit_ratio(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def _enabled(self) -> bool:
        env = get_settings().environment.lower()
        return env not in ("testing", "test") and self.ttl > 0

    def get(self, key: Any) -> Any | None:
        if not self._enabled():
            return None
        value = self._backend.get(key)
        if value is None:
            self._misses += 1
        else:
            self._hits += 1
        return value

    def set(self, key: Any, value: Any) -> None:
        if not self._enabled():
            return
        self._backend.set(key, value, self.ttl)

    def clear(self) -> None:
        self._backend.clear()


def _create_default_backend() -> CacheBackend:
    settings = get_settings()
    if settings.use_redis_cache:
        return _RedisBackend(settings.database.redis_url)
    return _MemoryBackend()


# Process-local caches for high-traffic read endpoints.
_dashboard_summary_cache = TimedCache(ttl_seconds=30, backend=_create_default_backend())
_studies_list_cache = TimedCache(ttl_seconds=30, backend=_create_default_backend())
_personas_list_cache = TimedCache(ttl_seconds=30, backend=_create_default_backend())


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
