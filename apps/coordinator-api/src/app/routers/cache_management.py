"""
Cache monitoring and management endpoints
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ..auth import AdminDep  # NEW: JWT auth

# from ..deps import require_admin_key  # OLD: API key auth (deprecated)
from ..utils.cache_management import clear_cache, get_cache_stats, warm_cache

logger = get_logger(__name__)
router = APIRouter(prefix="/cache", tags=["cache-management"])


@router.get("/stats", summary="Get cache statistics")
@rate_limit(rate=200, per=60)
async def get_cache_statistics(
    request: Request,
    # OLD: admin_key: Annotated[str, Depends(require_admin_key())],
    # NEW: JWT auth with admin role
    user: AdminDep,
) -> dict[str, Any]:
    """Get cache performance statistics"""
    try:
        stats = get_cache_stats()
        return {"cache_health": stats, "status": "healthy" if stats["health_status"] in ["excellent", "good"] else "degraded"}  # type: ignore[index]
    except Exception as e:
        logger.error("Failed to get cache stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve cache statistics") from e


@router.post("/clear", summary="Clear cache entries")
@rate_limit(rate=20, per=60)
async def clear_cache_entries(
    request: Request,
    # OLD: admin_key: Annotated[str, Depends(require_admin_key())],
    # NEW: JWT auth with admin role
    user: AdminDep,
    pattern: str | None = None,
) -> dict[str, Any]:
    """Clear cache entries (all or matching pattern)"""
    try:
        result = clear_cache(pattern)
        logger.info("Cache cleared by admin: pattern=%s, result=%s", pattern, result)
        return result  # type: ignore[return-value]
    except Exception as e:
        logger.error("Failed to clear cache: %s", e)
        raise HTTPException(status_code=500, detail="Failed to clear cache") from e


@router.post("/warm", summary="Warm up cache")
@rate_limit(rate=20, per=60)
async def warm_up_cache(
    request: Request,
    # OLD: admin_key: Annotated[str, Depends(require_admin_key())],
    # NEW: JWT auth with admin role
    user: AdminDep,
) -> dict[str, Any]:
    """Trigger cache warming for common queries"""
    try:
        result = warm_cache()
        logger.info("Cache warming triggered by admin")
        return result  # type: ignore[return-value]
    except Exception as e:
        logger.error("Failed to warm cache: %s", e)
        raise HTTPException(status_code=500, detail="Failed to warm cache") from e


@router.get("/health", summary="Get cache health status")
@rate_limit(rate=1000, per=60)
async def cache_health_check(
    request: Request,
    # OLD: admin_key: Annotated[str, Depends(require_admin_key())],
    # NEW: JWT auth with admin role
    user: AdminDep,
) -> dict[str, Any]:
    """Get detailed cache health information"""
    try:
        from ..utils.cache import cache_manager

        stats = get_cache_stats()
        cache_data = cache_manager.get_stats()
        return {"health": stats, "detailed_stats": cache_data, "recommendations": _get_cache_recommendations(stats)}  # type: ignore[arg-type]
    except Exception as e:
        logger.error("Failed to get cache health: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve cache health") from e


def _get_cache_recommendations(stats: dict[str, Any]) -> list[str]:
    """Get cache performance recommendations"""
    recommendations = []
    hit_rate = stats["hit_rate_percent"]
    total_entries = stats["total_entries"]
    if hit_rate < 40:
        recommendations.append("Low hit rate detected. Consider increasing cache TTL or warming cache more frequently.")
    if total_entries > 10000:
        recommendations.append(
            "High number of cache entries. Consider implementing cache size limits or more aggressive cleanup."
        )
    if hit_rate > 95:
        recommendations.append("Very high hit rate. Cache TTL might be too long, consider reducing for fresher data.")
    if not recommendations:
        recommendations.append("Cache performance is optimal.")
    return recommendations


# ============================================================================
# MIGRATION NOTES: API Key to JWT Auth
# ============================================================================
#
# Migration completed: 2025-01-XX
#
# Changes made:
# 1. Import change:
#    OLD: from ..deps import require_admin_key
#    NEW: from ..auth import AdminDep
#
# 2. Dependency changes (4 endpoints):
#    - get_cache_statistics: admin_key -> user: AdminDep
#    - clear_cache_entries: admin_key -> user: AdminDep
#    - warm_up_cache: admin_key -> user: AdminDep
#    - cache_health_check: admin_key -> user: AdminDep
#
# 3. JWT benefits:
#    - user["sub"]: Admin user ID
#    - user["role"]: Role verification (admin)
#    - user["exp"]: Token expiration
#    - Centralized auth via security matrix
#
# 4. Client code change:
#    OLD: headers = {"X-Api-Key": "your-api-key"}
#    NEW: headers = {"Authorization": f"Bearer {token}"}
#
# ============================================================================
