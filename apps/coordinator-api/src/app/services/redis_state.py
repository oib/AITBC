"""
Redis-backed state manager for mock router state.

Provides persistent, shared state for:
- Training jobs (Redis hash + sorted set for ordering)
- Agent agents and messages (Redis hash + streams)
- Swarm configurations (Redis hash)

 Falls back to in-memory dict when Redis is unavailable.
"""

from __future__ import annotations

import json
from typing import Any

from app.config import settings


class RedisStateManager:
    """Manages router state with Redis backing and in-memory fallback."""

    _instance: RedisStateManager | None = None

    def __init__(self) -> None:
        self._redis: Any = None
        self._memory: dict[str, Any] = {}
        self._initialized = False
        self._cache_prefix = "aitbc:coordinator:cache"

    async def _invalidate_cache(self, namespace: str) -> None:
        """Invalidate cached entries for a namespace on state mutation."""
        cache_pattern = f"{self._cache_prefix}:{namespace}:*"
        if self._redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=cache_pattern, count=100)
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception:
                pass
        else:
            keys_to_remove = [k for k in self._memory if k.startswith(f"{self._cache_prefix}:{namespace}:")]
            for k in keys_to_remove:
                self._memory.pop(k, None)

    @classmethod
    async def get_instance(cls) -> RedisStateManager:
        """Get or create the singleton instance (async-safe)."""
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._init()
        return cls._instance

    @classmethod
    def get_instance_sync(cls) -> RedisStateManager:
        """Get or create the singleton instance (sync, for module-level use)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _init(self) -> None:
        """Initialize Redis connection if enabled."""
        if self._initialized:
            return

        if settings.redis.enabled:
            try:
                import redis.asyncio as aioredis

                self._redis = await aioredis.from_url(
                    settings.redis.url,
                    max_connections=settings.redis.max_connections,
                    socket_timeout=settings.redis.socket_timeout,
                    socket_connect_timeout=settings.redis.socket_connect_timeout,
                    retry_on_timeout=settings.redis.retry_on_timeout,
                    health_check_interval=settings.redis.health_check_interval,
                    decode_responses=True,
                )
                await self._redis.ping()
            except Exception:
                self._redis = None

        self._initialized = True

    def _key(self, namespace: str, key: str) -> str:
        """Build a Redis key with namespace prefix."""
        return f"aitbc:coordinator:{namespace}:{key}"

    def _ns_key(self, namespace: str) -> str:
        """Build a Redis key for a namespace hash."""
        return f"aitbc:coordinator:{namespace}"

    # ------------------------------------------------------------------
    # Hash operations (for training jobs, swarm configs, agents)
    # ------------------------------------------------------------------

    async def hset(self, namespace: str, key: str, value: dict[str, Any]) -> None:
        """Set a hash field and invalidate related cache."""
        if self._redis:
            await self._redis.hset(self._ns_key(namespace), key, json.dumps(value))
        else:
            if namespace not in self._memory:
                self._memory[namespace] = {}
            self._memory[namespace][key] = value
        await self._invalidate_cache(namespace)

    async def hget(self, namespace: str, key: str) -> dict[str, Any] | None:
        """Get a hash field."""
        if self._redis:
            raw: str | None = await self._redis.hget(self._ns_key(namespace), key)  # type: ignore[no-any-return]
            return json.loads(raw) if raw else None
        else:
            return self._memory.get(namespace, {}).get(key)

    async def hgetall(self, namespace: str) -> dict[str, dict[str, Any]]:
        """Get all hash fields."""
        if self._redis:
            raw: dict[str, str] = await self._redis.hgetall(self._ns_key(namespace))  # type: ignore[no-any-return]
            return {k: json.loads(v) for k, v in raw.items()}
        else:
            return self._memory.get(namespace, {}).copy()

    async def hdel(self, namespace: str, key: str) -> None:
        """Delete a hash field and invalidate related cache."""
        if self._redis:
            await self._redis.hdel(self._ns_key(namespace), key)
        else:
            if namespace in self._memory:
                self._memory[namespace].pop(key, None)
        await self._invalidate_cache(namespace)

    # ------------------------------------------------------------------
    # Counter operations (for job/message counters)
    # ------------------------------------------------------------------

    async def incr(self, namespace: str, key: str = "counter") -> int:
        """Increment a counter."""
        if self._redis:
            result: int = await self._redis.incr(self._key(namespace, key))  # type: ignore[no-any-return]
            return result
        else:
            mem_key = f"{namespace}:{key}"
            current = self._memory.get(mem_key, 0)
            current += 1
            self._memory[mem_key] = current
            return current

    # ------------------------------------------------------------------
    # List operations (for message queues)
    # ------------------------------------------------------------------

    async def lpush(self, namespace: str, key: str, value: dict[str, Any]) -> None:
        """Push to a list and invalidate related cache."""
        if self._redis:
            await self._redis.lpush(self._key(namespace, key), json.dumps(value))
        else:
            mem_key = f"{namespace}:{key}"
            if mem_key not in self._memory:
                self._memory[mem_key] = []
            self._memory[mem_key].insert(0, value)
        await self._invalidate_cache(namespace)

    async def lrange(self, namespace: str, key: str, start: int = 0, end: int = -1) -> list[dict[str, Any]]:
        """Get a range from a list."""
        if self._redis:
            raw: list[str] = await self._redis.lrange(self._key(namespace, key), start, end)
            return [json.loads(v) for v in raw]
        else:
            mem_key = f"{namespace}:{key}"
            items: list[dict[str, Any]] = self._memory.get(mem_key, [])
            return items[start:end] if end != -1 else items[start:]

    # ------------------------------------------------------------------
    # Cache operations with TTL
    # ------------------------------------------------------------------

    async def cache_set(self, namespace: str, key: str, value: Any, ttl: int = 300) -> None:
        """Set a cached value with TTL."""
        if self._redis:
            await self._redis.setex(self._key(namespace, key), ttl, json.dumps(value))
        else:
            self._memory[self._key(namespace, key)] = value

    async def cache_get(self, namespace: str, key: str) -> Any | None:
        """Get a cached value."""
        if self._redis:
            raw = await self._redis.get(self._key(namespace, key))
            return json.loads(raw) if raw else None
        else:
            return self._memory.get(self._key(namespace, key))

    async def cache_delete(self, namespace: str, key: str) -> None:
        """Delete a cached value."""
        if self._redis:
            await self._redis.delete(self._key(namespace, key))
        else:
            self._memory.pop(self._key(namespace, key), None)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def clear_namespace(self, namespace: str) -> None:
        """Clear all keys in a namespace."""
        if self._redis:
            pattern = f"aitbc:coordinator:{namespace}*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
        else:
            keys_to_remove = [k for k in self._memory if k.startswith(f"{namespace}:") or k == namespace]
            for k in keys_to_remove:
                self._memory.pop(k, None)


# Convenience: module-level getter for sync access (returns uninitialized manager)
# Callers should await manager._init() before use, or use get_instance().
state_manager = RedisStateManager.get_instance_sync()
