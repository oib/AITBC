"""Health check routes for Pool Hub"""

from fastapi import APIRouter, Request
from datetime import datetime, timezone
from sqlalchemy import text

from aitbc.rate_limiting import rate_limit

router = APIRouter(tags=["health"])


@router.get("/health")
@rate_limit(rate=1000, per=60)
async def health_check(request: Request):
    """Basic health check."""
    return {
        "status": "ok",
        "service": "pool-hub",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
@rate_limit(rate=1000, per=60)
async def readiness_check(request: Request):
    """Readiness check for Kubernetes."""
    # Check dependencies
    checks = {"database": await check_database(), "redis": await check_redis()}

    all_ready = all(checks.values())

    return {
        "ready": all_ready,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/live")
@rate_limit(rate=1000, per=60)
async def liveness_check(request: Request):
    """Liveness check for Kubernetes."""
    return {"live": True}


async def check_database() -> bool:
    """Check database connectivity."""
    try:
        from ..database import get_engine
        from sqlalchemy import text

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    """Check Redis connectivity."""
    try:
        from ..redis_cache import get_redis_client

        client = get_redis_client()
        await client.ping()
        return True
    except Exception:
        return False
