"""
Event-Driven Redis Caching Strategy for Distributed Edge Nodes

Implements a distributed caching system with event-driven cache invalidation
for GPU availability and pricing data that changes on booking/cancellation.
"""

import json
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timedelta
import hashlib
import uuid

import redis.asyncio as redis
from redis.asyncio import ConnectionPool

logger = logging.getLogger(__name__)


class CacheEventType(Enum):
    """Types of cache events"""
    GPU_AVAILABILITY_CHANGED = "gpu_availability_changed"
    PRICING_UPDATED = "pricing_updated"
    BOOKING_CREATED = "booking_created"
    BOOKING_CANCELLED = "booking_cancelled"
    PROVIDER_STATUS_CHANGED = "provider_status_changed"
    MARKET_STATS_UPDATED = "market_stats_updated"
    ORDER_BOOK_UPDATED = "order_book_updated"
    MANUAL_INVALIDATION = "manual_invalidation"


@dataclass
class CacheEvent:
    """Cache invalidation event"""
    event_type: CacheEventType
    resource_id: str
    data: Dict[str, Any]
    timestamp: float
    source_node: str
    event_id: str
    affected_namespaces: List[str]


@dataclass
class CacheConfig:
    """Cache configuration for different data types"""
    namespace: str
    ttl_seconds: int
    event_driven: bool
    critical_data: bool  # Data that needs immediate propagation
    max_memory_mb: int


class EventDrivenCacheManager:
    """
    Event-driven cache manager for distributed edge nodes
    
    Features:
    - Redis pub/sub for real-time cache invalidation
    - Multi-tier caching (L1 memory + L2 Redis)
    - Event-driven updates for critical data
    - Automatic failover and recovery
    - Distributed cache coordination
    """
    
    def __init__(self, 
                 redis_url: str = "redis://localhost:6379/0",
                 node_id: str = None,
                 edge_node_region: str = "default"):
        self.redis_url = redis_url
        self.node_id = node_id or f"edge_node_{uuid.uuid4().hex[:8]}"
        self.edge_node_region = edge_node_region
        
        # Redis connections
        self.redis_client = None
        self.pubsub = None
        self.connection_pool = None
        
        # Event handling
        self.event_handlers: Dict[CacheEventType, List[Callable]] = {}
        self.event_queue = asyncio.Queue()
        self.is_running = False
        
        # Local L1 cache for critical data
        self.l1_cache: Dict[str, Dict] = {}
        self.l1_max_size = 1000
        
        # Cache configurations
        self.cache_configs = self._init_cache_configs()
        
        # Statistics
        self.stats = {
            'events_processed': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'invalidations': 0,
            'last_event_time': None
        }
    
    def _init_cache_configs(self) -> Dict[str, CacheConfig]:
        """Initialize cache configurations for different data types"""
        return {
            # GPU availability - changes frequently, needs immediate propagation
            'gpu_availability': CacheConfig(
                namespace='gpu_avail',
                ttl_seconds=30,  # Short TTL, but event-driven invalidation
                event_driven=True,
                critical_data=True,
                max_memory_mb=100
            ),
            
            # GPU pricing - changes on booking/cancellation
            'gpu_pricing': CacheConfig(
                namespace='gpu_pricing',
                ttl_seconds=60,  # Medium TTL with event-driven updates
                event_driven=True,
                critical_data=True,
                max_memory_mb=50
            ),
            
            # Order book - very dynamic
            'order_book': CacheConfig(
                namespace='order_book',
                ttl_seconds=5,   # Very short TTL
                event_driven=True,
                critical_data=True,
                max_memory_mb=200
            ),
            
            # Provider status - changes on provider state changes
            'provider_status': CacheConfig(
                namespace='provider_status',
                ttl_seconds=120,  # Longer TTL with event-driven updates
                event_driven=True,
                critical_data=False,
                max_memory_mb=50
            ),
            
            # Market statistics - computed periodically
            'market_stats': CacheConfig(
                namespace='market_stats',
                ttl_seconds=300,  # 5 minutes
                event_driven=True,
                critical_data=False,
                max_memory_mb=100
            ),
            
            # Historical data - static, longer TTL
            'historical_data': CacheConfig(
                namespace='historical',
                ttl_seconds=3600,  # 1 hour
                event_driven=False,
                critical_data=False,
                max_memory_mb=500
            )
        }
    
    async def connect(self):
        """Connect to Redis and setup pub/sub"""
        try:
            # Create connection pool
            self.connection_pool = ConnectionPool.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=20
            )
            
            # Create Redis client
            self.redis_client = redis.Redis(connection_pool=self.connection_pool)
            
            # Test connection
            await self.redis_client.ping()
            
            # Setup pub/sub for cache invalidation events
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe('cache_invalidation_events')
            
            # Start event processing
            self.is_running = True
            asyncio.create_task(self._process_events())
            asyncio.create_task(self._listen_for_events())
            
            logger.info(f"Connected to Redis cache manager. Node ID: {self.node_id}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Redis and cleanup"""
        self.is_running = False
        
        if self.pubsub:
            await self.pubsub.unsubscribe('cache_invalidation_events')
            await self.pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        if self.connection_pool:
            await self.connection_pool.disconnect()
        
        logger.info("Disconnected from Redis cache manager")
    
    def _generate_cache_key(self, namespace: str, params: Dict[str, Any]) -> str:
        """Generate deterministic cache key"""
        param_str = json.dumps(params, sort_keys=True)
        param_hash = hashlib.sha256(param_str.encode()).hexdigest()
        return f"{namespace}:{param_hash}"
    
    async def get(self, cache_type: str, params: Dict[str, Any]) -> Optional[Any]:
        """Get data from cache with L1/L2 fallback"""
        config = self.cache_configs.get(cache_type)
        if not config:
            raise ValueError(f"Unknown cache type: {cache_type}")
        
        cache_key = self._generate_cache_key(config.namespace, params)
        
        # 1. Try L1 memory cache first (fastest)
        if cache_key in self.l1_cache:
            cache_entry = self.l1_cache[cache_key]
            if cache_entry['expires_at'] > time.time():
                self.stats['cache_hits'] += 1
                logger.debug(f"L1 cache hit for {cache_key}")
                return cache_entry['data']
            else:
                # Expired, remove from L1
                del self.l1_cache[cache_key]
        
        # 2. Try L2 Redis cache
        if self.redis_client:
            try:
                cached_data = await self.redis_client.get(cache_key)
                if cached_data:
                    self.stats['cache_hits'] += 1
                    logger.debug(f"L2 cache hit for {cache_key}")
                    
                    data = json.loads(cached_data)
                    
                    # Backfill L1 cache for critical data
                    if config.critical_data and len(self.l1_cache) < self.l1_max_size:
                        self.l1_cache[cache_key] = {
                            'data': data,
                            'expires_at': time.time() + min(config.ttl_seconds, 60)
                        }
                    
                    return data
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")
        
        self.stats['cache_misses'] += 1
        return None
    
    async def set(self, cache_type: str, params: Dict[str, Any], data: Any, 
                   custom_ttl: int = None, publish_event: bool = True):
        """Set data in cache with optional event publishing"""
        config = self.cache_configs.get(cache_type)
        if not config:
            raise ValueError(f"Unknown cache type: {cache_type}")
        
        cache_key = self._generate_cache_key(config.namespace, params)
        ttl = custom_ttl or config.ttl_seconds
        
        # 1. Set L1 cache for critical data
        if config.critical_data:
            self._update_l1_cache(cache_key, data, ttl)
        
        # 2. Set L2 Redis cache
        if self.redis_client:
            try:
                serialized_data = json.dumps(data, default=str)
                await self.redis_client.setex(cache_key, ttl, serialized_data)
                
                # Publish invalidation event if event-driven
                if publish_event and config.event_driven:
                    await self._publish_invalidation_event(
                        CacheEventType.MANUAL_INVALIDATION,
                        cache_type,
                        {'cache_key': cache_key, 'action': 'updated'},
                        [config.namespace]
                    )
                
            except Exception as e:
                logger.error(f"Redis set failed: {e}")
    
    def _update_l1_cache(self, cache_key: str, data: Any, ttl: int):
        """Update L1 cache with size management"""
        # Remove oldest entries if cache is full
        while len(self.l1_cache) >= self.l1_max_size:
            oldest_key = min(self.l1_cache.keys(), 
                           key=lambda k: self.l1_cache[k]['expires_at'])
            del self.l1_cache[oldest_key]
        
        self.l1_cache[cache_key] = {
            'data': data,
            'expires_at': time.time() + ttl
        }
    
    async def invalidate_cache(self, cache_type: str, resource_id: str = None, 
                              reason: str = "manual"):
        """Invalidate cache entries and publish event"""
        config = self.cache_configs.get(cache_type)
        if not config:
            raise ValueError(f"Unknown cache type: {cache_type}")
        
        # Invalidate L1 cache
        keys_to_remove = []
        for key in self.l1_cache:
            if key.startswith(config.namespace):
                if resource_id is None or resource_id in key:
                    keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.l1_cache[key]
        
        # Invalidate L2 Redis cache
        if self.redis_client:
            try:
                pattern = f"{config.namespace}:*"
                if resource_id:
                    pattern = f"{config.namespace}:*{resource_id}*"
                
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
                
                self.stats['invalidations'] += 1
                
                # Publish invalidation event
                await self._publish_invalidation_event(
                    CacheEventType.MANUAL_INVALIDATION,
                    cache_type,
                    {'resource_id': resource_id, 'reason': reason},
                    [config.namespace]
                )
                
                logger.info(f"Invalidated {cache_type} cache: {reason}")
                
            except Exception as e:
                logger.error(f"Cache invalidation failed: {e}")
    
    async def _publish_invalidation_event(self, event_type: CacheEventType, 
                                         resource_id: str, data: Dict[str, Any],
                                         affected_namespaces: List[str]):
        """Publish cache invalidation event to Redis pub/sub"""
        event = CacheEvent(
            event_type=event_type,
            resource_id=resource_id,
            data=data,
            timestamp=time.time(),
            source_node=self.node_id,
            event_id=str(uuid.uuid4()),
            affected_namespaces=affected_namespaces
        )
        
        try:
            event_json = json.dumps(asdict(event), default=str)
            await self.redis_client.publish('cache_invalidation_events', event_json)
            logger.debug(f"Published invalidation event: {event_type.value}")
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
    
    async def _listen_for_events(self):
        """Listen for cache invalidation events from other nodes"""
        while self.is_running:
            try:
                message = await self.pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    await self._handle_invalidation_event(message['data'])
            except Exception as e:
                logger.error(f"Event listener error: {e}")
                await asyncio.sleep(1)
    
    async def _handle_invalidation_event(self, event_json: str):
        """Handle incoming cache invalidation event"""
        try:
            event_data = json.loads(event_json)
            
            # Ignore events from this node
            if event_data.get('source_node') == self.node_id:
                return
            
            # Queue event for processing
            await self.event_queue.put(event_data)
            
        except Exception as e:
            logger.error(f"Failed to handle invalidation event: {e}")
    
    async def _process_events(self):
        """Process queued invalidation events"""
        while self.is_running:
            try:
                event_data = await asyncio.wait_for(
                    self.event_queue.get(), timeout=1.0
                )
                
                await self._process_invalidation_event(event_data)
                self.stats['events_processed'] += 1
                self.stats['last_event_time'] = time.time()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Event processing error: {e}")
    
    async def _process_invalidation_event(self, event_data: Dict[str, Any]):
        """Process a single invalidation event"""
        event_type = CacheEventType(event_data['event_type'])
        affected_namespaces = event_data['affected_namespaces']
        
        # Invalidate L1 cache entries
        for namespace in affected_namespaces:
            keys_to_remove = []
            for key in self.l1_cache:
                if key.startswith(namespace):
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self.l1_cache[key]
        
        # Invalidate L2 cache entries
        if self.redis_client:
            try:
                for namespace in affected_namespaces:
                    pattern = f"{namespace}:*"
                    cursor = 0
                    while True:
                        cursor, keys = await self.redis_client.scan(
                            cursor=cursor, match=pattern, count=100
                        )
                        if keys:
                            await self.redis_client.delete(*keys)
                        if cursor == 0:
                            break
                            
                logger.debug(f"Processed invalidation event: {event_type.value}")
                
            except Exception as e:
                logger.error(f"Failed to process invalidation event: {e}")
    
    # Event-specific methods for common operations
    
    async def notify_gpu_availability_change(self, gpu_id: str, new_status: str):
        """Notify about GPU availability change"""
        await self._publish_invalidation_event(
            CacheEventType.GPU_AVAILABILITY_CHANGED,
            f"gpu_{gpu_id}",
            {'gpu_id': gpu_id, 'status': new_status},
            ['gpu_avail']
        )
    
    async def notify_pricing_update(self, gpu_type: str, new_price: float):
        """Notify about GPU pricing update"""
        await self._publish_invalidation_event(
            CacheEventType.PRICING_UPDATED,
            f"price_{gpu_type}",
            {'gpu_type': gpu_type, 'price': new_price},
            ['gpu_pricing']
        )
    
    async def notify_booking_created(self, booking_id: str, gpu_id: str):
        """Notify about new booking creation"""
        await self._publish_invalidation_event(
            CacheEventType.BOOKING_CREATED,
            f"booking_{booking_id}",
            {'booking_id': booking_id, 'gpu_id': gpu_id},
            ['gpu_avail', 'gpu_pricing', 'order_book']
        )
    
    async def notify_booking_cancelled(self, booking_id: str, gpu_id: str):
        """Notify about booking cancellation"""
        await self._publish_invalidation_event(
            CacheEventType.BOOKING_CANCELLED,
            f"booking_{booking_id}",
            {'booking_id': booking_id, 'gpu_id': gpu_id},
            ['gpu_avail', 'gpu_pricing', 'order_book']
        )
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        stats = self.stats.copy()
        
        # Add L1 cache size
        stats['l1_cache_size'] = len(self.l1_cache)
        stats['l1_cache_max_size'] = self.l1_max_size
        
        # Add Redis info if available
        if self.redis_client:
            try:
                info = await self.redis_client.info('memory')
                stats['redis_memory_used_mb'] = info['used_memory'] / (1024 * 1024)
                stats['redis_connected_clients'] = info.get('connected_clients', 0)
            except Exception as e:
                logger.warning(f"Failed to get Redis info: {e}")
        
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check of the cache system"""
        health = {
            'status': 'healthy',
            'redis_connected': False,
            'pubsub_active': False,
            'event_queue_size': 0,
            'last_event_age': None
        }
        
        try:
            # Check Redis connection
            if self.redis_client:
                await self.redis_client.ping()
                health['redis_connected'] = True
            
            # Check pub/sub
            if self.pubsub and self.is_running:
                health['pubsub_active'] = True
            
            # Check event queue
            health['event_queue_size'] = self.event_queue.qsize()
            
            # Check last event time
            if self.stats['last_event_time']:
                health['last_event_age'] = time.time() - self.stats['last_event_time']
            
            # Overall status
            if not health['redis_connected']:
                health['status'] = 'degraded'
            if not health['pubsub_active']:
                health['status'] = 'unhealthy'
                
        except Exception as e:
            health['status'] = 'unhealthy'
            health['error'] = str(e)
        
        return health


# Global cache manager instance
cache_manager = EventDrivenCacheManager()


# Decorator for automatic cache management
def cached_result(cache_type: str, ttl: int = None, key_params: List[str] = None):
    """
    Decorator to automatically cache function results
    
    Args:
        cache_type: Type of cache to use
        ttl: Custom TTL override
        key_params: List of parameter names to include in cache key
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate cache key from specified parameters
            if key_params:
                cache_key_params = {}
                for i, param_name in enumerate(key_params):
                    if i < len(args):
                        cache_key_params[param_name] = args[i]
                    elif param_name in kwargs:
                        cache_key_params[param_name] = kwargs[param_name]
            else:
                cache_key_params = {'args': args, 'kwargs': kwargs}
            
            # Try to get from cache
            cached_result = await cache_manager.get(cache_type, cache_key_params)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache_manager.set(cache_type, cache_key_params, result, ttl)
            
            return result
        return wrapper
    return decorator
