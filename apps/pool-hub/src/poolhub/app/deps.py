from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, Header
from sqlalchemy import select

from ..database import get_session
from ..models import Miner
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


async def get_miner_from_token(
    session: Annotated[Any, Depends(get_session)],
    authorization: str | None = Header(default=None),
) -> Miner:
    """Resolve the authenticated miner from the Authorization header.

    Expects ``Authorization: Bearer <api_key>``.  Looks up the miner by
    matching the API key hash.  Falls back to the configured ``miner_id``
    when no Authorization header is present (local/dev mode).
    """
    miner_id = getattr(settings, "miner_id", "default")
    if authorization and authorization.startswith("Bearer "):
        import hashlib

        api_key = authorization[7:]
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        result = await session.execute(select(Miner).where(Miner.api_key_hash == key_hash))
        miner = result.scalars().first()
        if miner is not None:
            return miner
    # Fallback: look up by configured miner_id
    result = await session.execute(select(Miner).where(Miner.miner_id == miner_id))
    miner = result.scalars().first()
    if miner is not None:
        return miner
    # No miner registered yet — return a minimal stub so endpoints don't crash.
    # This allows the hardware-profile endpoint to report empty data rather
    # than 500.  Once a miner registers via the pools router, real data is used.
    return Miner(
        miner_id=miner_id,
        api_key_hash="",
        addr="",
        proto="",
        gpu_vram_gb=0.0,
        gpu_name=None,
        cpu_cores=0,
        ram_gb=0.0,
        max_parallel=1,
        base_price=Decimal("0"),
        tags={},
        capabilities=[],
    )


# FastAPI dependency wrappers — get_session and get_redis are already async
# generators suitable for direct use with Depends().  Wrapping them with
# ``async for`` on the already-resolved value crashes (AsyncSession has no
# __aiter__), so we expose them directly.
db_session_dep = get_session
redis_dep = get_redis
