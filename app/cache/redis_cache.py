"""Redis cache layer with TTL support and cache-aside pattern."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RedisCache:
    """Async Redis wrapper for the addon's caching needs.

    Provides ``get_or_fetch`` (cache-aside) and direct ``get``/``set``/``delete``.
    All values are JSON-serialised automatically.
    """

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._redis: aioredis.Redis | None = None

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Open the Redis connection pool."""
        self._redis = aioredis.from_url(
            self._url,
            decode_responses=True,
            retry_on_error=[ConnectionError, TimeoutError],
        )
        # Verify connectivity
        await self._redis.ping()
        logger.info("Connected to Redis at %s", self._url)

    async def disconnect(self) -> None:
        """Close the Redis connection pool."""
        if self._redis:
            await self._redis.aclose()
            logger.info("Disconnected from Redis")

    @property
    def client(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("RedisCache not connected — call connect() first")
        return self._redis

    # ── Core operations ─────────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """Fetch a cached value, returning ``None`` on miss."""
        raw = await self.client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value in the cache with an optional TTL in seconds."""
        serialised = json.dumps(value, ensure_ascii=False, default=str)
        if ttl:
            await self.client.setex(key, ttl, serialised)
        else:
            await self.client.set(key, serialised)

    async def delete(self, key: str) -> None:
        """Remove a key from the cache."""
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check whether a key exists."""
        return bool(await self.client.exists(key))

    async def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Awaitable[T]],
        ttl: int = 3600,
    ) -> T:
        """Cache-aside pattern: return cached data or call *fetch_fn* on miss.

        The fetched result is stored in Redis with the given TTL.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        logger.debug("Cache miss for key=%s — fetching", key)
        result = await fetch_fn()
        await self.set(key, result, ttl=ttl)
        return result

    # ── Bulk helpers ────────────────────────────────────────────────────

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob *pattern*. Returns count deleted."""
        count = 0
        async for key in self.client.scan_iter(match=pattern, count=200):
            await self.client.delete(key)
            count += 1
        return count
