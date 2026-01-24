"""Health check routes for Pool Hub"""

from fastapi import APIRouter
from datetime import datetime

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {
        "status": "ok",
        "service": "pool-hub",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/ready")
async def readiness_check():
    """Readiness check for Kubernetes."""
    # Check dependencies
    checks = {
        "database": await check_database(),
        "redis": await check_redis()
    }
    
    all_ready = all(checks.values())
    
    return {
        "ready": all_ready,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/live")
async def liveness_check():
    """Liveness check for Kubernetes."""
    return {"live": True}


async def check_database() -> bool:
    """Check database connectivity."""
    try:
        # TODO: Implement actual database check
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    """Check Redis connectivity."""
    try:
        # TODO: Implement actual Redis check
        return True
    except Exception:
        return False
