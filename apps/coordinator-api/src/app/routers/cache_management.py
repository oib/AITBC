"""
Cache monitoring and management endpoints
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from ..deps import require_admin_key
from ..utils.cache_management import clear_cache, get_cache_stats, warm_cache

logger = get_logger(__name__)
router = APIRouter(prefix="/cache", tags=["cache-management"])


@router.get("/stats", summary="Get cache statistics")
@rate_limit(rate=200, per=60)
async def get_cache_statistics(request: Request, admin_key: str = Depends(require_admin_key())) -> dict[str, Any]:
    """Get cache performance statistics"""
    try:
        stats = get_cache_stats()
        return {"cache_health": stats, "status": "healthy" if stats["health_status"] in ["excellent", "good"] else "degraded"}  # type: ignore[index]
    except Exception as e:
        logger.error("Failed to get cache stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve cache statistics")


@router.post("/clear", summary="Clear cache entries")
@rate_limit(rate=20, per=60)
async def clear_cache_entries(
    request: Request, pattern: str | None = None, admin_key: str = Depends(require_admin_key())
) -> dict[str, Any]:
    """Clear cache entries (all or matching pattern)"""
    try:
        result = clear_cache(pattern)
        logger.info("Cache cleared by admin: pattern=%s, result=%s", pattern, result)
        return result  # type: ignore[return-value]
    except Exception as e:
        logger.error("Failed to clear cache: %s", e)
        raise HTTPException(status_code=500, detail="Failed to clear cache")


@router.post("/warm", summary="Warm up cache")
@rate_limit(rate=20, per=60)
async def warm_up_cache(request: Request, admin_key: str = Depends(require_admin_key())) -> dict[str, Any]:
    """Trigger cache warming for common queries"""
    try:
        result = warm_cache()
        logger.info("Cache warming triggered by admin")
        return result  # type: ignore[return-value]
    except Exception as e:
        logger.error("Failed to warm cache: %s", e)
        raise HTTPException(status_code=500, detail="Failed to warm cache")


@router.get("/health", summary="Get cache health status")
@rate_limit(rate=1000, per=60)
async def cache_health_check(request: Request, admin_key: str = Depends(require_admin_key())) -> dict[str, Any]:
    """Get detailed cache health information"""
    try:
        from ..utils.cache import cache_manager

        stats = get_cache_stats()
        cache_data = cache_manager.get_stats()
        return {"health": stats, "detailed_stats": cache_data, "recommendations": _get_cache_recommendations(stats)}  # type: ignore[arg-type]
    except Exception as e:
        logger.error("Failed to get cache health: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve cache health")


def _get_cache_recommendations(stats: dict) -> list:
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
