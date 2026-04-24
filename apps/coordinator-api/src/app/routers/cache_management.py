"""
Cache monitoring and management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from aitbc import get_logger
from ..config import settings
from ..deps import require_admin_key
from ..utils.cache_management import clear_cache, get_cache_stats, warm_cache

logger = get_logger(__name__)


limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/cache", tags=["cache-management"])


@router.get("/stats", summary="Get cache statistics")
@limiter.limit(lambda: settings.rate_limit_admin_stats)
async def get_cache_statistics(request: Request, admin_key: str = Depends(require_admin_key())):
    """Get cache performance statistics"""
    try:
        stats = get_cache_stats()
        return {"cache_health": stats, "status": "healthy" if stats["health_status"] in ["excellent", "good"] else "degraded"}
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cache statistics")


@router.post("/clear", summary="Clear cache entries")
@limiter.limit(lambda: settings.rate_limit_admin_stats)
async def clear_cache_entries(request: Request, pattern: str = None, admin_key: str = Depends(require_admin_key())):
    """Clear cache entries (all or matching pattern)"""
    try:
        result = clear_cache(pattern)
        logger.info(f"Cache cleared by admin: pattern={pattern}, result={result}")
        return result
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache")


@router.post("/warm", summary="Warm up cache")
@limiter.limit(lambda: settings.rate_limit_admin_stats)
async def warm_up_cache(request: Request, admin_key: str = Depends(require_admin_key())):
    """Trigger cache warming for common queries"""
    try:
        result = warm_cache()
        logger.info("Cache warming triggered by admin")
        return result
    except Exception as e:
        logger.error(f"Failed to warm cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to warm cache")


@router.get("/health", summary="Get cache health status")
@limiter.limit(lambda: settings.rate_limit_admin_stats)
async def cache_health_check(request: Request, admin_key: str = Depends(require_admin_key())):
    """Get detailed cache health information"""
    try:
        from ..utils.cache import cache_manager

        stats = get_cache_stats()
        cache_data = cache_manager.get_stats()

        return {"health": stats, "detailed_stats": cache_data, "recommendations": _get_cache_recommendations(stats)}
    except Exception as e:
        logger.error(f"Failed to get cache health: {e}")
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
