"""
Cache management utilities for endpoints
"""

import logging

from ..utils.cache import cache_manager, cleanup_expired_cache

logger = logging.getLogger(__name__)


def invalidate_cache_pattern(pattern: str):
    """Invalidate cache entries matching a pattern"""
    keys_to_delete = []

    for key in cache_manager._cache.keys():
        if pattern in key:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        cache_manager.delete(key)

    logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching pattern: {pattern}")
    return len(keys_to_delete)


def get_cache_health() -> dict:
    """Get cache health statistics"""
    stats = cache_manager.get_stats()

    # Determine health status
    total_requests = stats["total_requests"]
    if total_requests == 0:
        hit_rate = 0
        health_status = "unknown"
    else:
        hit_rate = stats["hit_rate_percent"]
        if hit_rate >= 80:
            health_status = "excellent"
        elif hit_rate >= 60:
            health_status = "good"
        elif hit_rate >= 40:
            health_status = "fair"
        else:
            health_status = "poor"

    return {
        "health_status": health_status,
        "hit_rate_percent": hit_rate,
        "total_entries": stats["total_entries"],
        "total_requests": total_requests,
        "memory_usage_mb": round(len(str(cache_manager._cache)) / 1024 / 1024, 2),
        "last_cleanup": stats.get("last_cleanup", "never"),
    }


# Cache invalidation strategies for different events
class CacheInvalidationStrategy:
    """Strategies for cache invalidation based on events"""

    @staticmethod
    def on_job_created(job_id: str):
        """Invalidate caches when a job is created"""
        # Invalidate job list caches
        invalidate_cache_pattern("jobs_")
        invalidate_cache_pattern("admin_stats")
        logger.info(f"Invalidated job-related caches for new job: {job_id}")

    @staticmethod
    def on_job_updated(job_id: str):
        """Invalidate caches when a job is updated"""
        # Invalidate specific job cache and lists
        invalidate_cache_pattern(f"jobs_get_job_{job_id}")
        invalidate_cache_pattern("jobs_")
        invalidate_cache_pattern("admin_stats")
        logger.info(f"Invalidated job caches for updated job: {job_id}")

    @staticmethod
    def on_marketplace_change():
        """Invalidate caches when marketplace data changes"""
        invalidate_cache_pattern("marketplace_")
        logger.info("Invalidated marketplace caches due to data change")

    @staticmethod
    def on_payment_created(payment_id: str):
        """Invalidate caches when a payment is created"""
        invalidate_cache_pattern("balance_")
        invalidate_cache_pattern("payment_")
        invalidate_cache_pattern("admin_stats")
        logger.info(f"Invalidated payment caches for new payment: {payment_id}")

    @staticmethod
    def on_payment_updated(payment_id: str):
        """Invalidate caches when a payment is updated"""
        invalidate_cache_pattern("balance_")
        invalidate_cache_pattern(f"payment_{payment_id}")
        logger.info(f"Invalidated payment caches for updated payment: {payment_id}")


# Background task for cache management
async def cache_management_task():
    """Background task for cache maintenance"""
    while True:
        try:
            # Clean up expired entries
            removed_count = cleanup_expired_cache()

            # Log cache health periodically
            if removed_count > 0:
                health = get_cache_health()
                logger.info(
                    f"Cache cleanup completed: {removed_count} entries removed, "
                    f"hit rate: {health['hit_rate_percent']}%, "
                    f"entries: {health['total_entries']}"
                )

            # Run cache management every 5 minutes
            import asyncio

            await asyncio.sleep(300)

        except Exception as e:
            logger.error(f"Cache management error: {e}")
            await asyncio.sleep(60)  # Retry after 1 minute on error


# Cache warming utilities for startup
class CacheWarmer:
    """Cache warming utilities for common endpoints"""

    def __init__(self, session):
        self.session = session

    async def warm_common_queries(self):
        """Warm up cache with common queries"""
        try:
            logger.info("Starting cache warming...")

            # Warm marketplace stats (most commonly accessed)
            await self._warm_marketplace_stats()

            # Warm admin stats
            await self._warm_admin_stats()

            # Warm exchange rates
            await self._warm_exchange_rates()

            logger.info("Cache warming completed successfully")

        except Exception as e:
            logger.error(f"Cache warming failed: {e}")

    async def _warm_marketplace_stats(self):
        """Warm marketplace statistics cache"""
        try:
            from ..services.marketplace import MarketplaceService

            service = MarketplaceService(self.session)
            stats = service.get_stats()

            # Manually cache the result
            from ..utils.cache import cache_manager

            cache_manager.set("marketplace_stats_get_marketplace_stats", stats, ttl_seconds=300)

            logger.info("Marketplace stats cache warmed")

        except Exception as e:
            logger.warning(f"Failed to warm marketplace stats: {e}")

    async def _warm_admin_stats(self):
        """Warm admin statistics cache"""
        try:
            from sqlmodel import func, select

            from ..domain import Job
            from ..services import JobService, MinerService

            JobService(self.session)
            miner_service = MinerService(self.session)

            # Simulate admin stats query
            total_jobs = self.session.exec(select(func.count()).select_from(Job)).one()
            active_jobs = self.session.exec(
                select(func.count()).select_from(Job).where(Job.state.in_(["QUEUED", "RUNNING"]))
            ).one()
            miner_service.list_records()

            stats = {
                "total_jobs": int(total_jobs or 0),
                "active_jobs": int(active_jobs or 0),
                "online_miners": miner_service.online_count(),
                "avg_miner_job_duration_ms": 0,
            }

            # Manually cache the result
            from ..utils.cache import cache_manager

            cache_manager.set("job_list_get_stats", stats, ttl_seconds=60)

            logger.info("Admin stats cache warmed")

        except Exception as e:
            logger.warning(f"Failed to warm admin stats: {e}")

    async def _warm_exchange_rates(self):
        """Warm exchange rates cache"""
        try:
            # Mock exchange rates - in production this would call an exchange API
            rates = {"AITBC_BTC": 0.00001, "AITBC_USD": 0.10, "BTC_USD": 50000.0}

            # Manually cache the result
            from ..utils.cache import cache_manager

            cache_manager.set("rates_current", rates, ttl_seconds=600)

            logger.info("Exchange rates cache warmed")

        except Exception as e:
            logger.warning(f"Failed to warm exchange rates: {e}")


# FastAPI endpoints for cache management
async def get_cache_stats():
    """Get cache statistics (for monitoring)"""
    return get_cache_health()


async def clear_cache(pattern: str = None):
    """Clear cache entries"""
    if pattern:
        count = invalidate_cache_pattern(pattern)
        return {"status": "cleared", "pattern": pattern, "count": count}
    else:
        cache_manager.clear()
        return {"status": "cleared", "pattern": "all", "count": "all"}


async def warm_cache():
    """Manually trigger cache warming"""
    # This would need to be called with a session
    # For now, just return status
    return {"status": "cache_warming_triggered"}
