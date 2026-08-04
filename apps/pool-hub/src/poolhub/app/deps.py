from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated, Any, cast

from fastapi import Depends, Header, HTTPException, status
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
    matching the API key hash.  Missing, malformed, or non-matching headers
    raise 401 — no fallback to a configured or stub miner is allowed.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or malformed Authorization header")

    import hashlib

    api_key = authorization[7:]
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    result = await session.execute(select(Miner).where(Miner.api_key_hash == key_hash))
    miner = result.scalars().first()
    if miner is not None:
        return cast(Miner, miner)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or unknown API key")


# FastAPI dependency wrappers — get_session and get_redis are already async
# generators suitable for direct use with Depends().  Wrapping them with
# ``async for`` on the already-resolved value crashes (AsyncSession has no
# __aiter__), so we expose them directly.
db_session_dep = get_session
redis_dep = get_redis
