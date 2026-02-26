"""
Marketplace Caching & Optimization Service
Implements advanced caching, indexing, and data optimization for the AITBC marketplace.
"""

import json
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any, Union, Set
from collections import OrderedDict
from datetime import datetime

import redis.asyncio as redis

logger = logging.getLogger(__name__)

class LFU_LRU_Cache:
    """Hybrid Least-Frequently/Least-Recently Used Cache for in-memory optimization"""
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}
        self.frequencies = {}
        self.frequency_lists = {}
        self.min_freq = 0
        
    def get(self, key: str) -> Optional[Any]:
        if key not in self.cache:
            return None
            
        # Update frequency
        freq = self.frequencies[key]
        val = self.cache[key]
        
        # Remove from current frequency list
        self.frequency_lists[freq].remove(key)
        if not self.frequency_lists[freq] and self.min_freq == freq:
            self.min_freq += 1
            
        # Add to next frequency list
        new_freq = freq + 1
        self.frequencies[key] = new_freq
        if new_freq not in self.frequency_lists:
            self.frequency_lists[new_freq] = OrderedDict()
        self.frequency_lists[new_freq][key] = None
        
        return val
        
    def put(self, key: str, value: Any):
        if self.capacity == 0:
            return
            
        if key in self.cache:
            self.cache[key] = value
            self.get(key) # Update frequency
            return
            
        if len(self.cache) >= self.capacity:
            # Evict least frequently used item (if tie, least recently used)
            evict_key, _ = self.frequency_lists[self.min_freq].popitem(last=False)
            del self.cache[evict_key]
            del self.frequencies[evict_key]
            
        # Add new item
        self.cache[key] = value
        self.frequencies[key] = 1
        self.min_freq = 1
        
        if 1 not in self.frequency_lists:
            self.frequency_lists[1] = OrderedDict()
        self.frequency_lists[1][key] = None

class MarketplaceDataOptimizer:
    """Advanced optimization engine for marketplace data access"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis_client = None
        
        # Two-tier cache: Fast L1 (Memory), Slower L2 (Redis)
        self.l1_cache = LFU_LRU_Cache(capacity=1000)
        self.is_connected = False
        
        # Cache TTL defaults
        self.ttls = {
            'order_book': 5,          # Very dynamic, 5 seconds
            'provider_status': 15,    # 15 seconds
            'market_stats': 60,       # 1 minute
            'historical_data': 3600   # 1 hour
        }
        
    async def connect(self):
        """Establish connection to Redis L2 cache"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            self.is_connected = True
            logger.info("Connected to Redis L2 cache")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}. Falling back to L1 cache only.")
            self.is_connected = False
            
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self.is_connected = False
            
    def _generate_cache_key(self, namespace: str, params: Dict[str, Any]) -> str:
        """Generate a deterministic cache key from parameters"""
        param_str = json.dumps(params, sort_keys=True)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()
        return f"mkpt:{namespace}:{param_hash}"
        
    async def get_cached_data(self, namespace: str, params: Dict[str, Any]) -> Optional[Any]:
        """Retrieve data from the multi-tier cache"""
        key = self._generate_cache_key(namespace, params)
        
        # 1. Try L1 Memory Cache (fastest)
        l1_result = self.l1_cache.get(key)
        if l1_result is not None:
            # Check if expired
            if l1_result['expires_at'] > time.time():
                logger.debug(f"L1 Cache hit for {key}")
                return l1_result['data']
                
        # 2. Try L2 Redis Cache
        if self.is_connected:
            try:
                l2_result_str = await self.redis_client.get(key)
                if l2_result_str:
                    logger.debug(f"L2 Cache hit for {key}")
                    data = json.loads(l2_result_str)
                    
                    # Backfill L1 cache
                    ttl = self.ttls.get(namespace, 60)
                    self.l1_cache.put(key, {
                        'data': data,
                        'expires_at': time.time() + min(ttl, 10) # L1 expires sooner than L2
                    })
                    return data
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")
                
        return None
        
    async def set_cached_data(self, namespace: str, params: Dict[str, Any], data: Any, custom_ttl: int = None):
        """Store data in the multi-tier cache"""
        key = self._generate_cache_key(namespace, params)
        ttl = custom_ttl or self.ttls.get(namespace, 60)
        
        # 1. Update L1 Cache
        self.l1_cache.put(key, {
            'data': data,
            'expires_at': time.time() + ttl
        })
        
        # 2. Update L2 Redis Cache asynchronously
        if self.is_connected:
            try:
                # We don't await this to keep the main thread fast
                # In FastAPI we would use BackgroundTasks
                await self.redis_client.setex(
                    key, 
                    ttl, 
                    json.dumps(data)
                )
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")
                
    async def invalidate_namespace(self, namespace: str):
        """Invalidate all cached items for a specific namespace"""
        if self.is_connected:
            try:
                # Find all keys matching namespace pattern
                cursor = 0
                pattern = f"mkpt:{namespace}:*"
                
                while True:
                    cursor, keys = await self.redis_client.scan(cursor=cursor, match=pattern, count=100)
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
                        
                logger.info(f"Invalidated L2 cache namespace: {namespace}")
            except Exception as e:
                logger.error(f"Failed to invalidate namespace {namespace}: {e}")
                
        # L1 invalidation is harder without scanning the whole dict
        # We'll just let them naturally expire or get evicted
                
    async def precompute_market_stats(self, db_session) -> Dict[str, Any]:
        """Background task to precompute expensive market statistics and cache them"""
        # This would normally run periodically via Celery/Celery Beat
        start_time = time.time()
        
        # Simulated expensive DB aggregations
        # In reality: SELECT AVG(price), SUM(volume) FROM trades WHERE created_at > NOW() - 24h
        stats = {
            "24h_volume": 1250000.50,
            "active_providers": 450,
            "average_price_per_tflop": 0.005,
            "network_utilization": 0.76,
            "computed_at": datetime.utcnow().isoformat(),
            "computation_time_ms": int((time.time() - start_time) * 1000)
        }
        
        # Cache the precomputed stats
        await self.set_cached_data('market_stats', {'period': '24h'}, stats, custom_ttl=300)
        
        return stats
        
    def optimize_order_book_response(self, raw_orders: List[Dict], depth: int = 50) -> Dict[str, List]:
        """
        Optimize the raw order book for client delivery.
        Groups similar prices, limits depth, and formats efficiently.
        """
        buy_orders = [o for o in raw_orders if o['type'] == 'buy']
        sell_orders = [o for o in raw_orders if o['type'] == 'sell']
        
        # Aggregate by price level to reduce payload size
        agg_buys = {}
        for order in buy_orders:
            price = round(order['price'], 4)
            if price not in agg_buys:
                agg_buys[price] = 0
            agg_buys[price] += order['amount']
            
        agg_sells = {}
        for order in sell_orders:
            price = round(order['price'], 4)
            if price not in agg_sells:
                agg_sells[price] = 0
            agg_sells[price] += order['amount']
            
        # Format and sort
        formatted_buys = [[p, q] for p, q in sorted(agg_buys.items(), reverse=True)[:depth]]
        formatted_sells = [[p, q] for p, q in sorted(agg_sells.items())[:depth]]
        
        return {
            "bids": formatted_buys,
            "asks": formatted_sells,
            "timestamp": time.time()
        }
