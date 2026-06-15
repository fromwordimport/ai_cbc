"""Rate limiting middleware for API endpoints.

Supports both in-memory and Redis-backed sliding-window rate limiting.
Redis is used automatically when ``USE_REDIS_RATE_LIMIT=true`` and a
``REDIS_URL`` is configured; otherwise the in-memory backend is used.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import ClassVar, Protocol

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = structlog.get_logger("aicbc.api.middleware.rate_limit")


@dataclass
class RateLimitConfig:
    """Configuration for a single rate limit rule."""

    requests: int = 60
    window_seconds: float = 60.0


@dataclass
class _BucketState:
    """Internal token bucket state."""

    tokens: float = 0.0
    last_update: float = field(default_factory=time.time)


class RateLimiterBackend(Protocol):
    """Abstract rate limiter backend."""

    async def is_allowed(self, key: str, config: RateLimitConfig) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        ...

    async def reset(self) -> None:
        """Clear all rate limit state."""
        ...


class InMemoryRateLimiter:
    """Simple in-memory token bucket rate limiter.

    Keyed by (client_ip, endpoint_path) for per-endpoint limits,
    and (client_ip, "global") for global limits.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _BucketState] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> tuple[bool, float]:
        async with self._lock:
            now = time.time()
            bucket = self._buckets.get(key)

            if bucket is None:
                self._buckets[key] = _BucketState(
                    tokens=config.requests - 1, last_update=now
                )
                return True, 0.0

            elapsed = now - bucket.last_update
            refill = elapsed * (config.requests / config.window_seconds)
            bucket.tokens = min(bucket.tokens + refill, config.requests)
            bucket.last_update = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0

            retry_after = (1.0 - bucket.tokens) / (
                config.requests / config.window_seconds
            )
            return False, retry_after

    def reset(self) -> None:
        """Clear all bucket state."""
        self._buckets.clear()

    def cleanup(self, max_age_seconds: float = 300.0) -> int:
        """Remove stale bucket entries. Returns number removed."""
        now = time.time()
        stale = [
            k for k, b in self._buckets.items() if now - b.last_update > max_age_seconds
        ]
        for k in stale:
            del self._buckets[k]
        return len(stale)


class RedisRateLimiter:
    """Redis-backed sliding-window rate limiter.

    Uses a sorted set per key where scores are request timestamps. Old entries
    outside the window are pruned on each request, and the cardinality enforces
    the limit. This backend works across multiple API worker processes.
    """

    def __init__(self, redis_url: str) -> None:
        from redis.asyncio import from_url

        self._redis_url = redis_url
        self._redis = from_url(redis_url, decode_responses=True)

    async def is_allowed(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> tuple[bool, float]:
        now = time.time()
        window_start = now - config.window_seconds

        async with self._redis.pipeline() as pipe:
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.pexpire(key, int(config.window_seconds * 1000) + 1000)
            _, current_count, _, _ = await pipe.execute()

        # current_count is the count before adding the current request
        if current_count < config.requests:
            return True, 0.0

        # Roll back the just-added timestamp since the request is over limit.
        await self._redis.zremrangebyscore(key, now, now)
        oldest = await self._redis.zrange(key, 0, 0, withscores=True)
        if oldest:
            retry_after = (oldest[0][1] + config.window_seconds) - now
            retry_after = max(retry_after, 1.0)
        else:
            retry_after = config.window_seconds
        return False, retry_after

    async def reset(self) -> None:
        keys = await self._redis.keys("rate_limit:*")
        if keys:
            await self._redis.delete(*keys)

    async def close(self) -> None:
        await self._redis.close()


# Module-level singleton limiter so tests can reset it
_global_limiter: RateLimiterBackend | None = None


def _create_limiter() -> RateLimiterBackend:
    """Create the best available rate limiter backend."""
    use_redis = os.environ.get("USE_REDIS_RATE_LIMIT", "").lower() in ("1", "true", "yes")
    redis_url = os.environ.get("REDIS_URL", "")

    if use_redis and redis_url:
        try:
            return RedisRateLimiter(redis_url)
        except Exception as exc:
            logger.warning(
                "redis_rate_limiter_unavailable",
                redis_url=redis_url,
                error=str(exc),
                fallback="in_memory",
            )
    return InMemoryRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware applying rate limits to all requests.

    Default limits:
      - Global: 120 requests / 60 seconds per IP
      - Sensitive endpoints (/personas/generate, /studies/*/simulate-responses): 10 / 60s
    """

    DEFAULT_GLOBAL: ClassVar[RateLimitConfig] = RateLimitConfig(
        requests=120, window_seconds=60.0
    )
    DEFAULT_SENSITIVE: ClassVar[RateLimitConfig] = RateLimitConfig(
        requests=10, window_seconds=60.0
    )

    _SENSITIVE_PATHS: ClassVar[tuple[str, ...]] = (
        "/personas/generate",
        "/simulate-responses",
        "/analyze",
    )

    def __init__(self, app, limiter: RateLimiterBackend | None = None) -> None:
        global _global_limiter
        super().__init__(app)
        self._limiter = limiter or (_global_limiter or _create_limiter())
        _global_limiter = self._limiter

    def reset_limits(self) -> None:
        """Reset all rate limit buckets. Useful for tests to prevent state leakage."""
        if isinstance(self._limiter, RedisRateLimiter):
            asyncio.create_task(self._limiter.reset())
        else:
            self._limiter.reset()

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        path = request.url.path

        is_sensitive = any(p in path for p in self._SENSITIVE_PATHS)
        config = self.DEFAULT_SENSITIVE if is_sensitive else self.DEFAULT_GLOBAL
        key = f"rate_limit:{client_ip}:{path}" if is_sensitive else f"rate_limit:{client_ip}:global"

        allowed, retry_after = await self._limiter.is_allowed(key, config)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=path,
                retry_after=round(retry_after, 1),
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after_seconds": round(retry_after, 1),
                },
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request headers or connection info."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        if request.client and request.client.host:
            return request.client.host
        return "unknown"


def reset_rate_limits() -> None:
    """Reset all rate limit buckets. Call from tests to prevent state leakage."""
    global _global_limiter
    if _global_limiter is None:
        return
    if isinstance(_global_limiter, RedisRateLimiter):
        try:
            asyncio.run(_global_limiter.reset())
        except RuntimeError:
            # Event loop already running; fire-and-forget is acceptable for tests.
            asyncio.create_task(_global_limiter.reset())
    else:
        _global_limiter.reset()
