from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as redis

from .settings import settings

_redis_client: redis.Redis | None = None


def create_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


def get_redis_client() -> redis.Redis:
    if _redis_client is None:
        return create_redis()
    return _redis_client


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    client = get_redis_client()
    yield client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
