from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends

from ..database import get_session
from ..redis_cache import get_redis


def get_db_session() -> AsyncGenerator:
    return get_session()


def get_redis_client() -> AsyncGenerator:
    return get_redis()


# FastAPI dependency wrappers
async def db_session_dep(session=Depends(get_session)):
    async for s in session:
        yield s


async def redis_dep(client=Depends(get_redis)):
    async for c in client:
        yield c
