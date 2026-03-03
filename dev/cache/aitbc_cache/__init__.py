"""
AITBC Event-Driven Cache Package

Provides distributed caching with event-driven invalidation for GPU marketplace
and other real-time data that needs immediate propagation across edge nodes.
"""

from .event_driven_cache import (
    EventDrivenCacheManager,
    CacheEventType,
    CacheEvent,
    CacheConfig,
    cache_manager,
    cached_result
)

from .gpu_marketplace_cache import (
    GPUMarketplaceCacheManager,
    GPUInfo,
    BookingInfo,
    MarketStats,
    init_marketplace_cache,
    get_marketplace_cache,
    marketplace_cache
)

__version__ = "1.0.0"
__author__ = "AITBC Team"

__all__ = [
    # Core event-driven caching
    "EventDrivenCacheManager",
    "CacheEventType", 
    "CacheEvent",
    "CacheConfig",
    "cache_manager",
    "cached_result",
    
    # GPU marketplace caching
    "GPUMarketplaceCacheManager",
    "GPUInfo",
    "BookingInfo", 
    "MarketStats",
    "init_marketplace_cache",
    "get_marketplace_cache",
    "marketplace_cache"
]
