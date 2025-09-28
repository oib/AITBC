from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import db_session_dep, redis_dep
from ..prometheus import miners_online_gauge
from poolhub.repositories.miner_repository import MinerRepository
from ..schemas import HealthResponse

router = APIRouter(tags=["health"], prefix="/v1")


@router.get("/health", response_model=HealthResponse, summary="Pool Hub health status")
async def health_endpoint(
    session: AsyncSession = Depends(db_session_dep),
    redis: Redis = Depends(redis_dep),
) -> HealthResponse:
    db_ok = True
    redis_ok = True
    db_error: str | None = None
    redis_error: str | None = None

    try:
        await session.execute("SELECT 1")
    except Exception as exc:  # pragma: no cover
        db_ok = False
        db_error = str(exc)

    try:
        await redis.ping()
    except Exception as exc:  # pragma: no cover
        redis_ok = False
        redis_error = str(exc)

    miner_repo = MinerRepository(session, redis)
    active_miners = await miner_repo.list_active_miners()
    miners_online = len(active_miners)
    miners_online_gauge.set(miners_online)

    status = "ok" if db_ok and redis_ok else "degraded"
    return HealthResponse(
        status=status,
        db=db_ok,
        redis=redis_ok,
        miners_online=miners_online,
        db_error=db_error,
        redis_error=redis_error,
    )
