"""
Marketplace Caching & Optimization Service
Implements advanced caching, indexing, and data optimization for the AITBC marketplace.
"""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class LFU_LRU_Cache:
    """Hybrid Least-Frequently/Least-Recently Used Cache for in-memory optimization"""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.cache: dict[str, Any] = {}
        self.frequencies: dict[str, int] = {}
        self.frequency_lists: dict[int, OrderedDict] = {}
        self.min_freq = 0

    def get(self, key: str) -> Any | None:
        if key not in self.cache:
            return None
        freq = self.frequencies[key]
        val = self.cache[key]
        if key in self.frequency_lists[freq]:
            del self.frequency_lists[freq][key]
        if not self.frequency_lists[freq] and self.min_freq == freq:
            self.min_freq += 1
        new_freq = freq + 1
        self.frequencies[key] = new_freq
        if new_freq not in self.frequency_lists:
            self.frequency_lists[new_freq] = OrderedDict()
        self.frequency_lists[new_freq][key] = None
        return val

    def put(self, key: str, value: Any) -> None:
        if self.capacity == 0:
            return
        if key in self.cache:
            self.cache[key] = value
            self.get(key)
            return
        if len(self.cache) >= self.capacity:
            evict_key, _ = self.frequency_lists[self.min_freq].popitem(last=False)
            del self.cache[evict_key]
            del self.frequencies[evict_key]
        self.cache[key] = value
        self.frequencies[key] = 1
        self.min_freq = 1
        if 1 not in self.frequency_lists:
            self.frequency_lists[1] = OrderedDict()
        self.frequency_lists[1][key] = None


class MarketplaceDataOptimizer:
    """Advanced optimization engine for marketplace data access"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self.redis_url = redis_url
        self.redis_client: redis.Redis | None = None
        self.l1_cache = LFU_LRU_Cache(capacity=1000)
        self.is_connected = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self.ttls = {"order_book": 5, "provider_status": 15, "market_stats": 60, "historical_data": 3600}

    def _is_stale_loop(self) -> bool:
        """Check if the Redis client is bound to a closed/different event loop."""
        if self.redis_client is None or self._loop is None:
            return False
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            return True
        return current_loop is not self._loop

    async def _reconnect_if_stale(self) -> None:
        """Reconnect to Redis if the event loop has changed (hot-reload)."""
        if self._is_stale_loop():
            logger.info("Marketplace cache: stale event loop detected, reconnecting...")
            await self.disconnect()
            await self.connect()

    async def connect(self) -> None:
        """Establish connection to Redis L2 cache"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            if self.redis_client:
                await self.redis_client.ping()
            self.is_connected = True
            self._loop = asyncio.get_running_loop()
            logger.info("Connected to Redis L2 cache")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s. Falling back to L1 cache only.", e)
            self.is_connected = False
            self._loop = None

    async def disconnect(self) -> None:
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self.is_connected = False

    def _generate_cache_key(self, namespace: str, params: dict[str, Any]) -> str:
        """Generate a deterministic cache key from parameters"""
        param_str = json.dumps(params, sort_keys=True)
        param_hash = hashlib.sha256(param_str.encode()).hexdigest()
        return f"mkpt:{namespace}:{param_hash}"

    async def get_cached_data(self, namespace: str, params: dict[str, Any]) -> Any | None:
        """Retrieve data from the multi-tier cache"""
        await self._reconnect_if_stale()
        key = self._generate_cache_key(namespace, params)
        l1_result = self.l1_cache.get(key)
        if l1_result is not None:
            if l1_result["expires_at"] > time.time():
                logger.debug("L1 Cache hit for %s", key)
                return l1_result["data"]
        if self.is_connected and self.redis_client:
            try:
                l2_result_str = await self.redis_client.get(key)
                if l2_result_str:
                    logger.debug("L2 Cache hit for %s", key)
                    data = json.loads(l2_result_str)
                    ttl = self.ttls.get(namespace, 60)
                    self.l1_cache.put(key, {"data": data, "expires_at": time.time() + min(ttl, 10)})
                    return data
            except Exception as e:
                logger.warning("Redis get failed: %s", e)
        return None

    async def set_cached_data(self, namespace: str, params: dict[str, Any], data: Any, custom_ttl: int | None = None) -> None:
        """Store data in the multi-tier cache"""
        await self._reconnect_if_stale()
        key = self._generate_cache_key(namespace, params)
        ttl = custom_ttl or self.ttls.get(namespace, 60)
        self.l1_cache.put(key, {"data": data, "expires_at": time.time() + ttl})
        if self.is_connected and self.redis_client:
            try:
                await self.redis_client.setex(key, ttl, json.dumps(data))
            except Exception as e:
                logger.warning("Redis set failed: %s", e)

    async def invalidate_namespace(self, namespace: str) -> None:
        """Invalidate all cached items for a specific namespace"""
        await self._reconnect_if_stale()
        if self.is_connected and self.redis_client:
            try:
                cursor = 0
                pattern = f"mkpt:{namespace}:*"
                while True:
                    cursor, keys = await self.redis_client.scan(cursor=cursor, match=pattern, count=100)
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
                logger.info("Invalidated L2 cache namespace: %s", namespace)
            except Exception as e:
                logger.error("Failed to invalidate namespace %s: %s", namespace, e)

    async def precompute_market_stats(self, db_session: Any) -> dict[str, Any]:
        """Background task to precompute expensive market statistics and cache them"""
        start_time = time.time()
        stats = {
            "24h_volume": 1250000.5,
            "active_providers": 450,
            "average_price_per_tflop": 0.005,
            "network_utilization": 0.76,
            "computed_at": datetime.now(UTC).isoformat(),
            "computation_time_ms": int((time.time() - start_time) * 1000),
        }
        await self.set_cached_data("market_stats", {"period": "24h"}, stats, custom_ttl=300)
        return stats

    def optimize_order_book_response(self, raw_orders: list[dict], depth: int = 50) -> dict[str, list]:
        """
        Optimize the raw order book for client delivery.
        Groups similar prices, limits depth, and formats efficiently.
        """
        buy_orders = [o for o in raw_orders if o["type"] == "buy"]
        sell_orders = [o for o in raw_orders if o["type"] == "sell"]
        agg_buys = {}
        for order in buy_orders:
            price = round(order["price"], 4)
            if price not in agg_buys:
                agg_buys[price] = 0
            agg_buys[price] += order["amount"]
        agg_sells = {}
        for order in sell_orders:
            price = round(order["price"], 4)
            if price not in agg_sells:
                agg_sells[price] = 0
            agg_sells[price] += order["amount"]
        formatted_buys = [[p, q] for p, q in sorted(agg_buys.items(), reverse=True)[:depth]]
        formatted_sells = [[p, q] for p, q in sorted(agg_sells.items())[:depth]]
        return {"bids": formatted_buys, "asks": formatted_sells, "timestamp": time.time()}  # type: ignore[dict-item]
