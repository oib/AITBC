from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from poolhub.repositories.miner_repository import MinerRepository

from ..deps import db_session_dep, redis_dep
from ..prometheus import miners_online_gauge
from ..schemas import HealthResponse

# No prefix here (V23-96).  ``main.py`` includes this router with no prefix of its
# own, and every other service in the repo answers /health at the root — a health
# check is infrastructure, not versioned API surface.  This router carried
# prefix="/v1" while the include added nothing, which is the one combination that
# leaves /health returning 404.
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Pool Hub health status")
# /v1/health is the path the deployed service has been answering on; kept working
# so existing probes do not break, but out of the schema so it is not advertised.
@router.get("/v1/health", response_model=HealthResponse, include_in_schema=False)
async def health_endpoint(
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session_dep)],
    redis: Annotated[Redis, Depends(redis_dep)],
) -> HealthResponse:
    db_ok = True
    redis_ok = True
    db_error: str | None = None
    redis_error: str | None = None

    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    try:
        await redis.ping()
    except Exception as exc:
        redis_ok = False
        redis_error = str(exc)

    # This is another query against the same session, so it fails whenever the
    # SELECT 1 above failed.  Guarding it is the whole point: unguarded, the
    # handler raised past the db_error it had just recorded and answered 500 with
    # no body, in exactly the outage this endpoint exists to describe (V23-96).
    miners_online: int | None = None
    miners_error: str | None = None
    try:
        active_miners = await MinerRepository(session, redis).list_active_miners()
    except Exception as exc:
        miners_error = str(exc)
    else:
        miners_online = len(active_miners)
        # Only on success: setting the gauge to 0 on failure is indistinguishable
        # from every miner having left.
        miners_online_gauge.set(miners_online)

    healthy = db_ok and redis_ok and miners_error is None
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if healthy else "degraded",
        db=db_ok,
        redis=redis_ok,
        miners_online=miners_online,
        db_error=db_error,
        redis_error=redis_error,
        miners_error=miners_error,
    )
