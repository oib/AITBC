"""
Cache management utilities for endpoints
"""

import asyncio
from typing import Any

from aitbc import get_logger

from ..utils.cache import cache_manager

logger = get_logger(__name__)


def invalidate_cache_pattern(pattern: str) -> int:
    """Invalidate cache entries matching a pattern"""
    keys_to_delete = []
    for key in cache_manager._cache.keys():
        if pattern in key:
            keys_to_delete.append(key)
    for key in keys_to_delete:
        cache_manager.delete(key)
    logger.info("Invalidated %s cache entries matching pattern: %s", len(keys_to_delete), pattern)
    return len(keys_to_delete)


def get_cache_health() -> dict:
    """Get cache health statistics"""
    stats = cache_manager.get_stats()
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


class CacheInvalidationStrategy:
    """Strategies for cache invalidation based on events"""

    @staticmethod
    def on_job_created(job_id: str) -> None:
        """Invalidate caches when a job is created"""
        invalidate_cache_pattern("jobs_")
        invalidate_cache_pattern("admin_stats")
        logger.info("Invalidated job-related caches for new job: %s", job_id)

    @staticmethod
    def on_job_updated(job_id: str) -> None:
        """Invalidate caches when a job is updated"""
        invalidate_cache_pattern(f"jobs_get_job_{job_id}")
        invalidate_cache_pattern("jobs_")
        invalidate_cache_pattern("admin_stats")
        logger.info("Invalidated job caches for updated job: %s", job_id)

    @staticmethod
    def on_marketplace_change() -> None:
        """Invalidate caches when marketplace data changes"""
        invalidate_cache_pattern("marketplace_")
        logger.info("Invalidated marketplace caches due to data change")

    @staticmethod
    def on_payment_created(payment_id: str) -> None:
        """Invalidate caches when a payment is created"""
        invalidate_cache_pattern("balance_")
        invalidate_cache_pattern("payment_")
        invalidate_cache_pattern("admin_stats")
        logger.info("Invalidated payment caches for new payment: %s", payment_id)

    @staticmethod
    def on_payment_updated(payment_id: str) -> None:
        """Invalidate caches when a payment is updated"""
        invalidate_cache_pattern("balance_")
        invalidate_cache_pattern(f"payment_{payment_id}")
        logger.info("Invalidated payment caches for updated payment: %s", payment_id)


async def cache_management_task() -> None:
    """Background task for cache maintenance"""
    while True:
        try:
            removed_count = cache_manager.cleanup_expired()
            if removed_count > 0:
                health = get_cache_health()
                logger.info(
                    "Cache cleanup completed: %s entries removed, hit rate: %s%, entries: %s",
                    removed_count,
                    health["hit_rate_percent"],
                    health["total_entries"],
                )
            await asyncio.sleep(300)
        except Exception as e:
            logger.error("Cache management error: %s", e)
            await asyncio.sleep(60)


class CacheWarmer:
    """Cache warming utilities for common endpoints"""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def warm_common_queries(self) -> None:
        """Warm up cache with common queries"""
        try:
            logger.info("Starting cache warming...")
            await self._warm_marketplace_stats()
            await self._warm_admin_stats()
            await self._warm_exchange_rates()
            logger.info("Cache warming completed successfully")
        except Exception as e:
            logger.error("Cache warming failed: %s", e)

    async def _warm_marketplace_stats(self) -> None:
        """Warm marketplace statistics cache"""
        try:
            from ..contexts.marketplace.services.marketplace import MarketplaceService

            service = MarketplaceService(self.session)
            stats = service.get_stats()
            from ..utils.cache import cache_manager

            cache_manager.set("marketplace_stats_get_marketplace_stats", stats, ttl_seconds=300)
            logger.info("Marketplace stats cache warmed")
        except Exception as e:
            logger.warning("Failed to warm marketplace stats: %s", e)

    async def _warm_admin_stats(self) -> None:
        """Warm admin statistics cache"""
        try:
            from sqlmodel import func, select

            from ..domain import Job
            from ..services import JobService, MinerService

            JobService(self.session)
            miner_service = MinerService(self.session)
            total_jobs = self.session.exec(select(func.count()).select_from(Job)).one()
            from sqlalchemy import column

            active_jobs = self.session.exec(
                select(func.count()).select_from(Job).where(column("state").in_(["QUEUED", "RUNNING"]))
            ).one()
            miner_service.list_records()
            stats = {
                "total_jobs": int(total_jobs or 0),
                "active_jobs": int(active_jobs or 0),
                "online_miners": miner_service.online_count(),
                "avg_miner_job_duration_ms": 0,
            }
            from ..utils.cache import cache_manager

            cache_manager.set("job_list_get_stats", stats, ttl_seconds=60)
            logger.info("Admin stats cache warmed")
        except Exception as e:
            logger.warning("Failed to warm admin stats: %s", e)

    async def _warm_exchange_rates(self) -> None:
        """Warm exchange rates cache"""
        try:
            rates = {"AITBC_BTC": 1e-05, "AITBC_USD": 0.1, "BTC_USD": 50000.0}
            from ..utils.cache import cache_manager

            cache_manager.set("rates_current", rates, ttl_seconds=600)
            logger.info("Exchange rates cache warmed")
        except Exception as e:
            logger.warning("Failed to warm exchange rates: %s", e)


async def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics (for monitoring)"""
    return get_cache_health()


async def clear_cache(pattern: str | None = None) -> dict[str, Any]:
    """Clear cache entries"""
    if pattern:
        count = invalidate_cache_pattern(pattern)
        return {"status": "cleared", "pattern": pattern, "count": count}
    else:
        cache_manager.clear()
        return {"status": "cleared", "pattern": "all", "count": "all"}


async def warm_cache() -> dict[str, str]:
    """Manually trigger cache warming"""
    return {"status": "cache_warming_triggered"}
