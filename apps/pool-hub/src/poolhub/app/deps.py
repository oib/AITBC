from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends

from ..database import get_session
from ..redis_cache import get_redis


def get_db_session() -> AsyncGenerator[Any]:
    return get_session()


def get_redis_client() -> AsyncGenerator[Any]:
    return get_redis()


# FastAPI dependency wrappers
async def db_session_dep(session: Annotated[Any, Depends(get_session)]) -> AsyncGenerator[Any]:
    async for s in session:
        yield s


async def redis_dep(client: Annotated[Any, Depends(get_redis)]) -> AsyncGenerator[Any]:
    async for c in client:
        yield c
