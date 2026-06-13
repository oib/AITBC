"""Health check routes for Pool Hub"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from aitbc.rate_limiting import rate_limit

router = APIRouter(tags=["health"])


@router.get("/health")
@rate_limit(rate=1000, per=60)
async def health_check(request: Request) -> dict[str, str]:
    """Basic health check."""
    return {
        "status": "ok",
        "service": "pool-hub",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/ready")
@rate_limit(rate=1000, per=60)
async def readiness_check(request: Request) -> dict[str, bool | dict[str, bool] | str]:
    """Readiness check for Kubernetes."""
    # Check dependencies
    checks = {"database": await check_database(), "redis": await check_redis()}

    all_ready = all(checks.values())

    return {
        "ready": all_ready,
        "checks": checks,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/live")
@rate_limit(rate=1000, per=60)
async def liveness_check(request: Request) -> dict[str, bool]:
    """Liveness check for Kubernetes."""
    return {"live": True}


async def check_database() -> bool:
    """Check database connectivity."""
    try:
        from sqlalchemy import text

        from ..database import get_engine  # type: ignore[import-not-found]

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    """Check Redis connectivity."""
    try:
        from ..redis_cache import get_redis_client  # type: ignore[import-not-found]

        client = get_redis_client()
        await client.ping()
        return True
    except Exception:
        return False
