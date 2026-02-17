"""Health check routes for Pool Hub"""

from fastapi import APIRouter
from datetime import datetime
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {
        "status": "ok",
        "service": "pool-hub",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/ready")
async def readiness_check():
    """Readiness check for Kubernetes."""
    # Check dependencies
    checks = {"database": await check_database(), "redis": await check_redis()}

    all_ready = all(checks.values())

    return {
        "ready": all_ready,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/live")
async def liveness_check():
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
