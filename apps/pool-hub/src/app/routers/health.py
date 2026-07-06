"""Health check routes for Pool Hub"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request

from aitbc.health_checks import HealthChecker, HealthStatus
from aitbc.rate_limiting import rate_limit

router = APIRouter(tags=["health"])

# Build health checker with async dependency checks
_health_checker = HealthChecker("pool-hub")


async def _check_database() -> tuple[HealthStatus, str, dict[str, Any]]:
    """Check database connectivity."""
    try:
        from sqlalchemy import text

        from ..database import get_engine  # type: ignore[import-not-found]

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return (HealthStatus.HEALTHY, "Database connection OK", {})
    except Exception as e:
        return (HealthStatus.UNHEALTHY, f"Database connection failed: {e}", {})


async def _check_redis() -> tuple[HealthStatus, str, dict[str, Any]]:
    """Check Redis connectivity."""
    try:
        from ..redis_cache import get_redis_client  # type: ignore[import-not-found]

        client = get_redis_client()
        await client.ping()
        return (HealthStatus.HEALTHY, "Redis connection OK", {})
    except Exception as e:
        return (HealthStatus.UNHEALTHY, f"Redis connection failed: {e}", {})


_health_checker.register_async_check("database", _check_database)
_health_checker.register_async_check("redis", _check_redis)


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
async def readiness_check(request: Request) -> dict[str, Any]:
    """Readiness check for Kubernetes."""
    result = await _health_checker.async_get_health_dict()
    all_ready = result["status"] == HealthStatus.HEALTHY.value
    checks = {name: details["status"] == HealthStatus.HEALTHY.value for name, details in (result.get("details") or {}).items()}
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
