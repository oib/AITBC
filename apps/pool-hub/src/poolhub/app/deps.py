from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends

from ..database import get_session
from ..redis_cache import get_redis
from ..settings import settings


def get_db_session() -> AsyncGenerator[Any]:
    return get_session()


# Alias for routers that import get_db
get_db = get_db_session


def get_redis_client() -> AsyncGenerator[Any]:
    return get_redis()


def get_miner_id() -> str:
    """Return the configured miner ID for this pool-hub instance."""
    return getattr(settings, "miner_id", "default")


def get_miner_from_token(token: str = "") -> str:
    """Extract miner ID from authorization token (simple implementation)."""
    # For now, just return the configured miner_id
    # A real implementation would validate the token
    return getattr(settings, "miner_id", "default")


# FastAPI dependency wrappers
async def db_session_dep(session: Annotated[Any, Depends(get_session)]) -> AsyncGenerator[Any]:
    async for s in session:
        yield s


async def redis_dep(client: Annotated[Any, Depends(get_redis)]) -> AsyncGenerator[Any]:
    async for c in client:
        yield c
