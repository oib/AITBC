"""
GPU Marketplace Cache Manager

Specialized cache manager for GPU marketplace data with event-driven invalidation
for availability and pricing changes on booking/cancellation.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
import json

from .event_driven_cache import (
    EventDrivenCacheManager, 
    CacheEventType,
    cached_result
)

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """GPU information structure"""
    gpu_id: str
    provider_id: str
    gpu_type: str
    memory_gb: int
    cuda_cores: int
    base_price_per_hour: float
    current_price_per_hour: float
    availability_status: str  # 'available', 'busy', 'offline', 'maintenance'
    region: str
    performance_score: float
    last_updated: datetime


@dataclass
class BookingInfo:
    """Booking information structure"""
    booking_id: str
    gpu_id: str
    user_id: str
    start_time: datetime
    end_time: datetime
    status: str  # 'active', 'completed', 'cancelled'
    total_cost: float
    created_at: datetime


@dataclass
class MarketStats:
    """Market statistics structure"""
    total_gpus: int
    available_gpus: int
    busy_gpus: int
    average_price_per_hour: float
    total_bookings_24h: int
    total_volume_24h: float
    utilization_rate: float
    last_updated: datetime


class GPUMarketplaceCacheManager:
    """
    Specialized cache manager for GPU marketplace
    
    Features:
    - Real-time GPU availability tracking
    - Dynamic pricing with immediate propagation
    - Event-driven cache invalidation on booking changes
    - Regional cache optimization
    - Performance-based GPU ranking
    """
    
    def __init__(self, cache_manager: EventDrivenCacheManager):
        self.cache = cache_manager
        self.regions = set()
        self.gpu_types = set()
        
        # Register event handlers
        self._register_event_handlers()
    
    def _register_event_handlers(self):
        """Register handlers for cache invalidation events"""
        # These handlers will be called when events are received
        self.cache.event_handlers[CacheEventType.GPU_AVAILABILITY_CHANGED] = [
            self._handle_gpu_availability_change
        ]
        self.cache.event_handlers[CacheEventType.PRICING_UPDATED] = [
            self._handle_pricing_update
        ]
        self.cache.event_handlers[CacheEventType.BOOKING_CREATED] = [
            self._handle_booking_created
        ]
        self.cache.event_handlers[CacheEventType.BOOKING_CANCELLED] = [
            self._handle_booking_cancelled
        ]
    
    # GPU Availability Methods
    
    async def get_gpu_availability(self, 
                                 region: str = None,
                                 gpu_type: str = None,
                                 include_busy: bool = False) -> List[GPUInfo]:
        """Get GPU availability with filtering options"""
        params = {
            'region': region,
            'gpu_type': gpu_type,
            'include_busy': include_busy,
            'timestamp': datetime.now(datetime.UTC).isoformat()
        }
        
        cached_data = await self.cache.get('gpu_availability', params)
        if cached_data:
            return [GPUInfo(**gpu) for gpu in cached_data]
        
        # In real implementation, this would query the database
        # For now, return empty list to be populated by real data
        return []
    
    async def set_gpu_availability(self, gpus: List[GPUInfo]):
        """Set GPU availability data"""
        gpu_data = [asdict(gpu) for gpu in gpus]
        
        # Update regions and GPU types tracking
        for gpu in gpus:
            self.regions.add(gpu.region)
            self.gpu_types.add(gpu.gpu_type)
        
        # Cache with different parameter combinations
        await self.cache.set('gpu_availability', {}, gpu_data)
        
        # Cache filtered views
        for region in self.regions:
            region_gpus = [asdict(gpu) for gpu in gpus if gpu.region == region]
            await self.cache.set('gpu_availability', 
                               {'region': region}, region_gpus)
        
        for gpu_type in self.gpu_types:
            type_gpus = [asdict(gpu) for gpu in gpus if gpu.gpu_type == gpu_type]
            await self.cache.set('gpu_availability',
                               {'gpu_type': gpu_type}, type_gpus)
    
    async def update_gpu_status(self, gpu_id: str, new_status: str):
        """Update individual GPU status and notify"""
        # Get current GPU data
        gpus = await self.get_gpu_availability()
        updated_gpu = None
        
        for gpu in gpus:
            if gpu.gpu_id == gpu_id:
                gpu.availability_status = new_status
                gpu.last_updated = datetime.now(datetime.UTC)
                updated_gpu = gpu
                break
        
        if updated_gpu:
            # Update cache
            await self.set_gpu_availability(gpus)
            
            # Publish event for immediate propagation
            await self.cache.notify_gpu_availability_change(gpu_id, new_status)
            
            logger.info(f"Updated GPU {gpu_id} status to {new_status}")
    
    # Pricing Methods
    
    async def get_gpu_pricing(self, 
                            gpu_type: str = None,
                            region: str = None) -> Dict[str, float]:
        """Get current GPU pricing"""
        params = {
            'gpu_type': gpu_type,
            'region': region,
            'timestamp': datetime.now(datetime.UTC).isoformat()
        }
        
        cached_data = await self.cache.get('gpu_pricing', params)
        if cached_data:
            return cached_data
        
        # Return empty pricing to be populated by real data
        return {}
    
    async def update_gpu_pricing(self, gpu_type: str, new_price: float, region: str = None):
        """Update GPU pricing and notify"""
        # Get current pricing
        current_pricing = await self.get_gpu_pricing(gpu_type, region)
        
        pricing_key = f"{gpu_type}_{region}" if region else gpu_type
        current_pricing[pricing_key] = new_price
        
        # Update cache
        await self.cache.set('gpu_pricing', 
                           {'gpu_type': gpu_type, 'region': region},
                           current_pricing)
        
        # Publish event for immediate propagation
        await self.cache.notify_pricing_update(gpu_type, new_price)
        
        logger.info(f"Updated {gpu_type} pricing to {new_price}")
    
    async def get_dynamic_pricing(self, gpu_id: str) -> float:
        """Get dynamic pricing for a specific GPU"""
        params = {'gpu_id': gpu_id}
        
        cached_price = await self.cache.get('gpu_pricing', params)
        if cached_price:
            return cached_price
        
        # Calculate dynamic pricing based on demand and availability
        gpus = await self.get_gpu_availability()
        target_gpu = next((gpu for gpu in gpus if gpu.gpu_id == gpu_id), None)
        
        if not target_gpu:
            return 0.0
        
        # Simple dynamic pricing logic
        base_price = target_gpu.base_price_per_hour
        availability_multiplier = 1.0
        
        # Increase price based on demand (lower availability)
        total_gpus = len(gpus)
        available_gpus = len([g for g in gpus if g.availability_status == 'available'])
        
        if total_gpus > 0:
            availability_ratio = available_gpus / total_gpus
            if availability_ratio < 0.1:  # Less than 10% available
                availability_multiplier = 2.0
            elif availability_ratio < 0.3:  # Less than 30% available
                availability_multiplier = 1.5
            elif availability_ratio < 0.5:  # Less than 50% available
                availability_multiplier = 1.2
        
        dynamic_price = base_price * availability_multiplier
        
        # Cache the calculated price
        await self.cache.set('gpu_pricing', params, {'price': dynamic_price})
        
        return dynamic_price
    
    # Booking Methods
    
    async def create_booking(self, booking: BookingInfo) -> bool:
        """Create a new booking and update caches"""
        try:
            # In real implementation, save to database first
            # For now, just update caches
            
            # Update GPU availability
            await self.update_gpu_status(booking.gpu_id, 'busy')
            
            # Update pricing (might change due to reduced availability)
            gpus = await self.get_gpu_availability()
            target_gpu = next((gpu for gpu in gpus if gpu.gpu_id == booking.gpu_id), None)
            
            if target_gpu:
                new_price = await self.get_dynamic_pricing(booking.gpu_id)
                await self.update_gpu_pricing(target_gpu.gpu_type, new_price, target_gpu.region)
            
            # Publish booking creation event
            await self.cache.notify_booking_created(booking.booking_id, booking.gpu_id)
            
            # Invalidate relevant caches
            await self.cache.invalidate_cache('order_book')
            await self.cache.invalidate_cache('market_stats')
            
            logger.info(f"Created booking {booking.booking_id} for GPU {booking.gpu_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create booking: {e}")
            return False
    
    async def cancel_booking(self, booking_id: str, gpu_id: str) -> bool:
        """Cancel a booking and update caches"""
        try:
            # Update GPU availability
            await self.update_gpu_status(gpu_id, 'available')
            
            # Update pricing (might change due to increased availability)
            gpus = await self.get_gpu_availability()
            target_gpu = next((gpu for gpu in gpus if gpu.gpu_id == gpu_id), None)
            
            if target_gpu:
                new_price = await self.get_dynamic_pricing(gpu_id)
                await self.update_gpu_pricing(target_gpu.gpu_type, new_price, target_gpu.region)
            
            # Publish booking cancellation event
            await self.cache.notify_booking_cancelled(booking_id, gpu_id)
            
            # Invalidate relevant caches
            await self.cache.invalidate_cache('order_book')
            await self.cache.invalidate_cache('market_stats')
            
            logger.info(f"Cancelled booking {booking_id} for GPU {gpu_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel booking: {e}")
            return False
    
    # Market Statistics
    
    async def get_market_stats(self) -> MarketStats:
        """Get current market statistics"""
        params = {'timestamp': datetime.now(datetime.UTC).isoformat()}
        
        cached_data = await self.cache.get('market_stats', params)
        if cached_data:
            return MarketStats(**cached_data)
        
        # Calculate statistics from current data
        gpus = await self.get_gpu_availability()
        
        total_gpus = len(gpus)
        available_gpus = len([g for g in gpus if g.availability_status == 'available'])
        busy_gpus = len([g for g in gpus if g.availability_status == 'busy'])
        
        # Calculate average price
        prices = [g.current_price_per_hour for g in gpus if g.availability_status == 'available']
        avg_price = sum(prices) / len(prices) if prices else 0.0
        
        utilization_rate = busy_gpus / total_gpus if total_gpus > 0 else 0.0
        
        stats = MarketStats(
            total_gpus=total_gpus,
            available_gpus=available_gpus,
            busy_gpus=busy_gpus,
            average_price_per_hour=avg_price,
            total_bookings_24h=0,  # Would be calculated from database
            total_volume_24h=0.0,  # Would be calculated from database
            utilization_rate=utilization_rate,
            last_updated=datetime.now(datetime.UTC)
        )
        
        # Cache the statistics
        await self.cache.set('market_stats', params, asdict(stats))
        
        return stats
    
    # Event Handlers
    
    async def _handle_gpu_availability_change(self, event_data: Dict[str, Any]):
        """Handle GPU availability change event"""
        gpu_id = event_data['data']['gpu_id']
        new_status = event_data['data']['status']
        
        # Invalidate GPU availability cache
        await self.cache.invalidate_cache('gpu_availability')
        
        # Invalidate market stats
        await self.cache.invalidate_cache('market_stats')
        
        logger.debug(f"Handled GPU availability change: {gpu_id} -> {new_status}")
    
    async def _handle_pricing_update(self, event_data: Dict[str, Any]):
        """Handle pricing update event"""
        gpu_type = event_data['data']['gpu_type']
        new_price = event_data['data']['price']
        
        # Invalidate pricing cache
        await self.cache.invalidate_cache('gpu_pricing')
        
        # Invalidate market stats
        await self.cache.invalidate_cache('market_stats')
        
        logger.debug(f"Handled pricing update: {gpu_type} -> {new_price}")
    
    async def _handle_booking_created(self, event_data: Dict[str, Any]):
        """Handle booking creation event"""
        booking_id = event_data['data']['booking_id']
        gpu_id = event_data['data']['gpu_id']
        
        # Invalidate caches affected by new booking
        await self.cache.invalidate_cache('gpu_availability')
        await self.cache.invalidate_cache('gpu_pricing')
        await self.cache.invalidate_cache('order_book')
        await self.cache.invalidate_cache('market_stats')
        
        logger.debug(f"Handled booking creation: {booking_id}")
    
    async def _handle_booking_cancelled(self, event_data: Dict[str, Any]):
        """Handle booking cancellation event"""
        booking_id = event_data['data']['booking_id']
        gpu_id = event_data['data']['gpu_id']
        
        # Invalidate caches affected by cancellation
        await self.cache.invalidate_cache('gpu_availability')
        await self.cache.invalidate_cache('gpu_pricing')
        await self.cache.invalidate_cache('order_book')
        await self.cache.invalidate_cache('market_stats')
        
        logger.debug(f"Handled booking cancellation: {booking_id}")
    
    # Utility Methods
    
    async def get_top_performing_gpus(self, limit: int = 10) -> List[GPUInfo]:
        """Get top performing GPUs by performance score"""
        gpus = await self.get_gpu_availability()
        
        # Filter available GPUs and sort by performance score
        available_gpus = [gpu for gpu in gpus if gpu.availability_status == 'available']
        sorted_gpus = sorted(available_gpus, 
                           key=lambda gpu: gpu.performance_score, 
                           reverse=True)
        
        return sorted_gpus[:limit]
    
    async def get_cheapest_gpus(self, limit: int = 10, gpu_type: str = None) -> List[GPUInfo]:
        """Get cheapest available GPUs"""
        gpus = await self.get_gpu_availability(gpu_type=gpu_type)
        
        # Filter available GPUs and sort by price
        available_gpus = [gpu for gpu in gpus if gpu.availability_status == 'available']
        sorted_gpus = sorted(available_gpus,
                           key=lambda gpu: gpu.current_price_per_hour)
        
        return sorted_gpus[:limit]
    
    async def search_gpus(self, 
                         min_memory: int = None,
                         min_cuda_cores: int = None,
                         max_price: float = None,
                         region: str = None) -> List[GPUInfo]:
        """Search GPUs with specific criteria"""
        gpus = await self.get_gpu_availability(region=region)
        
        filtered_gpus = []
        for gpu in gpus:
            if gpu.availability_status != 'available':
                continue
            
            if min_memory and gpu.memory_gb < min_memory:
                continue
            
            if min_cuda_cores and gpu.cuda_cores < min_cuda_cores:
                continue
            
            if max_price and gpu.current_price_per_hour > max_price:
                continue
            
            filtered_gpus.append(gpu)
        
        return filtered_gpus
    
    async def get_cache_health(self) -> Dict[str, Any]:
        """Get comprehensive cache health report"""
        health = await self.cache.health_check()
        
        # Add marketplace-specific metrics
        marketplace_metrics = {
            'regions_count': len(self.regions),
            'gpu_types_count': len(self.gpu_types),
            'last_gpu_update': None,
            'last_pricing_update': None
        }
        
        # Get last update times from cache stats
        stats = await self.cache.get_cache_stats()
        if stats['last_event_time']:
            marketplace_metrics['last_event_age'] = time.time() - stats['last_event_time']
        
        health['marketplace_metrics'] = marketplace_metrics
        health['cache_stats'] = stats
        
        return health


# Global marketplace cache manager instance
marketplace_cache = None


async def init_marketplace_cache(redis_url: str = "redis://localhost:6379/0",
                               node_id: str = None,
                               region: str = "default") -> GPUMarketplaceCacheManager:
    """Initialize the global marketplace cache manager"""
    global marketplace_cache
    
    # Initialize cache manager
    cache_manager = EventDrivenCacheManager(redis_url, node_id, region)
    await cache_manager.connect()
    
    # Initialize marketplace cache manager
    marketplace_cache = GPUMarketplaceCacheManager(cache_manager)
    
    logger.info("GPU Marketplace Cache Manager initialized")
    return marketplace_cache


async def get_marketplace_cache() -> GPUMarketplaceCacheManager:
    """Get the global marketplace cache manager"""
    if marketplace_cache is None:
        raise RuntimeError("Marketplace cache not initialized. Call init_marketplace_cache() first.")
    return marketplace_cache
