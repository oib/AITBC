"""
Caching strategy for expensive queries

.. note::
    This module provides app-specific caching features (memory limits,
    cache warming, FastAPI middleware). The canonical caching
    implementation lives in ``aitbc.cache``.
"""

import asyncio
import gc
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.caching import generate_cache_key
from sqlalchemy.exc import SQLAlchemyError

logger = get_logger(__name__)

# Expected failure surface for the best-effort cache paths below:
# filesystem errors, data-shape errors from the deep size estimator, lazy
# import failures, and DB errors from service calls made while warming.
# RuntimeError covers abort-style raises; genuine BaseExceptions still
# propagate (#1862).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    SQLAlchemyError,
)

# COORD-CACHE-MEM-1 (#1689): bounds for the deep-size estimator. Cached values
# are arbitrary payloads (lists/dicts/ORM-derived objects); recursion is
# capped so a pathological self-referential or huge structure cannot turn
# set() into an unbounded walk. Elements beyond the visit cap are charged a
# flat per-item estimate instead of being walked.
_SIZE_MAX_DEPTH = 8
_SIZE_MAX_ITEMS = 2048
_SIZE_ATOMIC_TYPES = (str, bytes, bytearray, int, float, bool, type(None))


def _estimate_obj_size(obj: Any, depth: int = 0, seen: set[int] | None = None) -> int:
    """Approximate in-memory size of ``obj`` in bytes.

    sys.getsizeof alone measures only the container shell — the #1689 defect.
    This walks dict/list/tuple/set/frozenset up to bounded depth/item counts
    and charges sys.getsizeof for everything else (strings/bytes report
    their real payload; arbitrary objects report their shallow shell).
    """
    if seen is None:
        seen = set()
    oid = id(obj)
    if oid in seen:
        return 0
    seen.add(oid)
    try:
        size = sys.getsizeof(obj)
        if isinstance(obj, _SIZE_ATOMIC_TYPES) or depth >= _SIZE_MAX_DEPTH:
            return size
        if isinstance(obj, dict):
            items = list(obj.items())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            items = [(None, v) for v in obj]
        else:
            return size
        visited = 0
        for k, v in items:
            if visited >= _SIZE_MAX_ITEMS:
                size += 64  # flat charge per unvisited item
                continue
            visited += 1
            if k is not None:
                size += _estimate_obj_size(k, depth + 1, seen)
            size += _estimate_obj_size(v, depth + 1, seen)
        return size
    finally:
        seen.discard(oid)


class CacheManager:
    """Simple in-memory cache with TTL support and memory management"""

    def __init__(self, max_size: int = 1000, max_memory_mb: int = 100) -> None:
        self._cache: dict[str, dict[str, Any]] = {}
        self._stats = {"hits": 0, "misses": 0, "sets": 0, "evictions": 0}
        self.max_size = max_size
        self.max_memory_mb = max_memory_mb
        # COORD-CACHE-MEM-1 (#1689): running estimate of cached payload bytes,
        # maintained incrementally on set/delete/evict/expiry. Replaces the
        # old sys.getsizeof(self._cache) shell measurement that never saw
        # the values.
        self._estimated_bytes = 0
        self._max_memory_bytes = max_memory_mb * 1024 * 1024

    def get(self, key: str) -> Any | None:
        """Get value from cache"""
        if key not in self._cache:
            self._stats["misses"] += 1
            return None
        cache_entry = self._cache[key]
        if datetime.now(UTC) > cache_entry["expires_at"]:
            self._remove_entry(key)
            self._stats["evictions"] += 1
            self._stats["misses"] += 1
            return None
        self._stats["hits"] += 1
        logger.debug("Cache hit for key: %s", key)
        return cache_entry["value"]

    def _entry_cost(self, key: str, value: Any) -> int:
        """Estimated bytes charged for one cache entry (key + value)."""
        return _estimate_obj_size(key) + _estimate_obj_size(value)

    def _remove_entry(self, key: str) -> None:
        """Delete an entry and decrement the running byte estimate."""
        entry = self._cache.pop(key, None)
        if entry is not None:
            self._estimated_bytes -= entry.get("cost", 0)
            if self._estimated_bytes < 0:
                self._estimated_bytes = 0

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set value in cache with TTL and enforce size/memory limits"""
        cost = self._entry_cost(key, value)
        # Overwriting an existing key releases its old charge first.
        if key in self._cache:
            self._remove_entry(key)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        # Enforce the memory cap on EVERY set (#1689): evict oldest until the
        # new entry fits. A single entry larger than the whole cap evicts
        # everything else and is still stored — the bound is best-effort for
        # oversized singletons, exact for aggregate growth.
        while self._estimated_bytes + cost > self._max_memory_bytes and self._cache:
            self._evict_oldest()
        if len(self._cache) >= self.max_size:
            self._evict_oldest()
        self._cache[key] = {
            "value": value,
            "expires_at": expires_at,
            "created_at": datetime.now(UTC),
            "ttl": ttl_seconds,
            "cost": cost,
        }
        self._estimated_bytes += cost
        self._stats["sets"] += 1
        logger.debug("Cache set for key: %s, TTL: %ss", key, ttl_seconds)

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if key in self._cache:
            self._remove_entry(key)
            return True
        return False

    def clear(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()
        self._estimated_bytes = 0
        logger.info("Cache cleared")

    def cleanup_expired(self) -> int:
        """Remove expired entries and return count removed"""
        now = datetime.now(UTC)
        expired_keys = [key for key, entry in self._cache.items() if now > entry["expires_at"]]
        for key in expired_keys:
            self._remove_entry(key)
        self._stats["evictions"] += len(expired_keys)
        if expired_keys:
            logger.info("Cleaned up %s expired cache entries", len(expired_keys))
        return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total_requests * 100 if total_requests > 0 else 0
        return {
            **self._stats,
            "total_entries": len(self._cache),
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total_requests,
            "max_size": self.max_size,
            "max_memory_mb": self.max_memory_mb,
        }

    def _evict_oldest(self) -> None:
        """Evict the oldest cache entry"""
        if not self._cache:
            return
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]["created_at"])
        self._remove_entry(oldest_key)
        self._stats["evictions"] += 1
        logger.debug("Evicted oldest cache entry: %s", oldest_key)

    def _check_memory_limit(self) -> None:
        """Check if cache exceeds memory limit and evict if needed.

        Retained for compatibility; enforcement now happens on every set()
        via the incremental byte estimate (#1689). This drains any residual
        overage (e.g. entries stored before an estimate correction).
        """
        while self._estimated_bytes > self._max_memory_bytes and self._cache:
            self._evict_oldest()
        if self._estimated_bytes > self._max_memory_bytes:
            logger.warning(
                "Cache memory limit still exceeded after evicting all entries (estimate %s bytes > %s bytes)",
                self._estimated_bytes,
                self._max_memory_bytes,
            )
        gc.collect()


cache_manager = CacheManager(max_size=1000, max_memory_mb=100)


def cached(ttl_seconds: int = 300, key_prefix: str = "") -> Callable[[Any], Any]:
    """Decorator for caching function results"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = f"{key_prefix}{func.__name__}_{generate_cache_key(func.__name__, *args, **kwargs)}"
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            result = await func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl_seconds)  # noqa: unawaited-async — sync CacheManager.set
            return result

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = f"{key_prefix}{func.__name__}_{generate_cache_key(func.__name__, *args, **kwargs)}"
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl_seconds)
            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


CACHE_CONFIGS = {
    "market_stats": {"ttl_seconds": 300, "key_prefix": "market_"},
    "job_list": {"ttl_seconds": 60, "key_prefix": "jobs_"},
    "miner_list": {"ttl_seconds": 120, "key_prefix": "miners_"},
    "user_balance": {"ttl_seconds": 30, "key_prefix": "balance_"},
    "exchange_rates": {"ttl_seconds": 600, "key_prefix": "rates_"},
}


def get_cache_config(cache_type: str) -> dict[str, Any]:
    """Get cache configuration for a specific type"""
    return CACHE_CONFIGS.get(cache_type, {"ttl_seconds": 300, "key_prefix": ""})


async def cleanup_expired_cache() -> None:
    """Background task to clean up expired cache entries"""
    while True:
        try:
            removed_count = cache_manager.cleanup_expired()
            if removed_count > 0:
                logger.info("Background cleanup removed %s expired entries", removed_count)
            await asyncio.sleep(300)
        except _OPS_ERRORS as e:
            logger.error("Cache cleanup error: %s", e)
            await asyncio.sleep(60)


class CacheWarmer:
    """Utility class for warming up cache with common queries"""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def warm_market_stats(self) -> None:
        """Warm up market statistics cache"""
        try:
            from ..contexts.market.services.market import MarketService

            service = MarketService(self.session)
            stats = service.get_stats()
            cache_manager.set("market_stats_overview", stats, ttl_seconds=300)  # noqa: unawaited-async — sync CacheManager.set
            logger.info("Market stats cache warmed up")
        except _OPS_ERRORS as e:
            logger.error("Failed to warm market stats cache: %s", e)

    async def warm_exchange_rates(self) -> None:
        """Warm up exchange rates cache"""
        try:
            rates = {"AITBC_ETH": 1e-05, "AITBC_USD": 0.1}
            cache_manager.set("exchange_rates_current", rates, ttl_seconds=600)  # noqa: unawaited-async — sync CacheManager.set
            logger.info("Exchange rates cache warmed up")
        except _OPS_ERRORS as e:
            logger.error("Failed to warm exchange rates cache: %s", e)


async def cache_middleware(request: Any, call_next: Any) -> Any:
    """FastAPI middleware to add cache headers and track cache performance"""
    response = await call_next(request)
    stats = cache_manager.get_stats()
    response.headers["X-Cache-Hits"] = str(stats["hits"])
    response.headers["X-Cache-Misses"] = str(stats["misses"])
    response.headers["X-Cache-Hit-Rate"] = f"{stats['hit_rate_percent']}%"
    return response
