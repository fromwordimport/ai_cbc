"""Tests for cache backend switching."""

from aicbc.core.cache import TimedCache, _MemoryBackend


def test_memory_backend() -> None:
    cache = TimedCache(ttl_seconds=10, backend=_MemoryBackend())
    cache.set("k", "v")
    assert cache.get("k") == "v"
    cache.clear()
    assert cache.get("k") is None


def test_cache_hit_ratio() -> None:
    cache = TimedCache(ttl_seconds=10, backend=_MemoryBackend())
    cache.set("k", "v")
    cache.get("k")
    cache.get("missing")
    assert cache.hit_ratio == 0.5
