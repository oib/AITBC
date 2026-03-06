"""
Tests for Event-Driven Redis Cache System

Comprehensive test suite for distributed caching with event-driven invalidation
ensuring immediate propagation of GPU availability and pricing changes.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from aitbc_cache.event_driven_cache import (
    EventDrivenCacheManager,
    CacheEventType,
    CacheEvent,
    CacheConfig,
    cached_result
)

from aitbc_cache.gpu_marketplace_cache import (
    GPUMarketplaceCacheManager,
    GPUInfo,
    BookingInfo,
    MarketStats,
    init_marketplace_cache,
    get_marketplace_cache
)


class TestEventDrivenCacheManager:
    """Test the core event-driven cache manager"""
    
    @pytest.fixture
    async def cache_manager(self):
        """Create a cache manager for testing"""
        manager = EventDrivenCacheManager(
            redis_url="redis://localhost:6379/1",  # Use different DB for testing
            node_id="test_node_123"
        )
        
        # Mock Redis connection for testing
        with patch('redis.asyncio.Redis') as mock_redis:
            mock_client = AsyncMock()
            mock_redis.return_value = mock_client
            
            # Mock ping response
            mock_client.ping.return_value = True
            
            # Mock pubsub
            mock_pubsub = AsyncMock()
            mock_client.pubsub.return_value = mock_pubsub
            
            await manager.connect()
            
            yield manager
            
            await manager.disconnect()
    
    @pytest.mark.asyncio
    async def test_cache_connection(self, cache_manager):
        """Test cache manager connection"""
        assert cache_manager.is_connected is True
        assert cache_manager.node_id == "test_node_123"
    
    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, cache_manager):
        """Test basic cache set and get operations"""
        test_data = {"gpu_id": "gpu_123", "status": "available"}
        
        # Set data
        await cache_manager.set('gpu_availability', {'gpu_id': 'gpu_123'}, test_data)
        
        # Get data
        result = await cache_manager.get('gpu_availability', {'gpu_id': 'gpu_123'})
        
        assert result is not None
        assert result['gpu_id'] == 'gpu_123'
        assert result['status'] == 'available'
    
    @pytest.mark.asyncio
    async def test_l1_cache_fallback(self, cache_manager):
        """Test L1 cache fallback when Redis is unavailable"""
        test_data = {"message": "test data"}
        
        # Mock Redis failure
        cache_manager.redis_client = None
        
        # Should still work with L1 cache
        await cache_manager.set('test_cache', {'key': 'value'}, test_data)
        result = await cache_manager.get('test_cache', {'key': 'value'})
        
        assert result is not None
        assert result['message'] == 'test data'
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self, cache_manager):
        """Test cache invalidation"""
        test_data = {"gpu_id": "gpu_456", "status": "busy"}
        
        # Set data
        await cache_manager.set('gpu_availability', {'gpu_id': 'gpu_456'}, test_data)
        
        # Verify it's cached
        result = await cache_manager.get('gpu_availability', {'gpu_id': 'gpu_456'})
        assert result is not None
        
        # Invalidate cache
        await cache_manager.invalidate_cache('gpu_availability')
        
        # Should be gone from L1 cache
        assert len(cache_manager.l1_cache) == 0
    
    @pytest.mark.asyncio
    async def test_event_publishing(self, cache_manager):
        """Test event publishing for cache invalidation"""
        # Mock Redis publish
        cache_manager.redis_client.publish = AsyncMock()
        
        # Publish GPU availability change event
        await cache_manager.notify_gpu_availability_change('gpu_789', 'offline')
        
        # Verify event was published
        cache_manager.redis_client.publish.assert_called_once()
        
        # Check event data
        call_args = cache_manager.redis_client.publish.call_args
        event_data = json.loads(call_args[0][1])
        
        assert event_data['event_type'] == 'gpu_availability_changed'
        assert event_data['resource_id'] == 'gpu_789'
        assert event_data['data']['gpu_id'] == 'gpu_789'
        assert event_data['data']['status'] == 'offline'
    
    @pytest.mark.asyncio
    async def test_event_handling(self, cache_manager):
        """Test handling of incoming invalidation events"""
        test_data = {"gpu_id": "gpu_event", "status": "available"}
        
        # Set data in L1 cache
        cache_key = cache_manager._generate_cache_key('gpu_avail', {'gpu_id': 'gpu_event'})
        cache_manager.l1_cache[cache_key] = {
            'data': test_data,
            'expires_at': time.time() + 300
        }
        
        # Simulate incoming event
        event_data = {
            'event_type': 'gpu_availability_changed',
            'resource_id': 'gpu_event',
            'data': {'gpu_id': 'gpu_event', 'status': 'busy'},
            'timestamp': time.time(),
            'source_node': 'other_node',
            'event_id': 'event_123',
            'affected_namespaces': ['gpu_avail']
        }
        
        # Process event
        await cache_manager._process_invalidation_event(event_data)
        
        # L1 cache should be invalidated
        assert cache_key not in cache_manager.l1_cache
    
    @pytest.mark.asyncio
    async def test_cache_statistics(self, cache_manager):
        """Test cache statistics tracking"""
        # Perform some cache operations
        await cache_manager.set('test_cache', {'key': 'value'}, {'data': 'test'})
        await cache_manager.get('test_cache', {'key': 'value'})
        await cache_manager.get('nonexistent_cache', {'key': 'value'})
        
        stats = await cache_manager.get_cache_stats()
        
        assert 'cache_hits' in stats
        assert 'cache_misses' in stats
        assert 'events_processed' in stats
        assert 'l1_cache_size' in stats
    
    @pytest.mark.asyncio
    async def test_health_check(self, cache_manager):
        """Test cache health check"""
        health = await cache_manager.health_check()
        
        assert 'status' in health
        assert 'redis_connected' in health
        assert 'pubsub_active' in health
        assert 'event_queue_size' in health
    
    @pytest.mark.asyncio
    async def test_cached_decorator(self, cache_manager):
        """Test the cached result decorator"""
        call_count = 0
        
        @cached_result('test_cache', ttl=60)
        async def expensive_function(param1, param2):
            nonlocal call_count
            call_count += 1
            return f"result_{param1}_{param2}"
        
        # First call should execute function
        result1 = await expensive_function('a', 'b')
        assert result1 == "result_a_b"
        assert call_count == 1
        
        # Second call should use cache
        result2 = await expensive_function('a', 'b')
        assert result2 == "result_a_b"
        assert call_count == 1  # Should not increment
        
        # Different parameters should execute function
        result3 = await expensive_function('c', 'd')
        assert result3 == "result_c_d"
        assert call_count == 2


class TestGPUMarketplaceCacheManager:
    """Test the GPU marketplace cache manager"""
    
    @pytest.fixture
    async def marketplace_cache(self):
        """Create a marketplace cache manager for testing"""
        # Mock cache manager
        mock_cache_manager = AsyncMock()
        mock_cache_manager.get = AsyncMock()
        mock_cache_manager.set = AsyncMock()
        mock_cache_manager.invalidate_cache = AsyncMock()
        mock_cache_manager.notify_gpu_availability_change = AsyncMock()
        mock_cache_manager.notify_pricing_update = AsyncMock()
        mock_cache_manager.notify_booking_created = AsyncMock()
        mock_cache_manager.notify_booking_cancelled = AsyncMock()
        
        manager = GPUMarketplaceCacheManager(mock_cache_manager)
        yield manager
    
    @pytest.mark.asyncio
    async def test_gpu_availability_caching(self, marketplace_cache):
        """Test GPU availability caching"""
        gpus = [
            GPUInfo(
                gpu_id="gpu_001",
                provider_id="provider_1",
                gpu_type="RTX 3080",
                memory_gb=10,
                cuda_cores=8704,
                base_price_per_hour=0.1,
                current_price_per_hour=0.12,
                availability_status="available",
                region="us-east",
                performance_score=95.0,
                last_updated=datetime.utcnow()
            ),
            GPUInfo(
                gpu_id="gpu_002",
                provider_id="provider_2",
                gpu_type="RTX 3090",
                memory_gb=24,
                cuda_cores=10496,
                base_price_per_hour=0.15,
                current_price_per_hour=0.18,
                availability_status="busy",
                region="us-west",
                performance_score=98.0,
                last_updated=datetime.utcnow()
            )
        ]
        
        # Set GPU availability
        await marketplace_cache.set_gpu_availability(gpus)
        
        # Verify cache.set was called
        assert marketplace_cache.cache.set.call_count > 0
        
        # Test filtering
        marketplace_cache.cache.get.return_value = [gpus[0].__dict__]
        result = await marketplace_cache.get_gpu_availability(region="us-east")
        
        assert len(result) == 1
        assert result[0].gpu_id == "gpu_001"
        assert result[0].region == "us-east"
    
    @pytest.mark.asyncio
    async def test_gpu_status_update(self, marketplace_cache):
        """Test GPU status update with event notification"""
        # Mock existing GPU
        existing_gpu = GPUInfo(
            gpu_id="gpu_003",
            provider_id="provider_3",
            gpu_type="A100",
            memory_gb=40,
            cuda_cores=6912,
            base_price_per_hour=0.5,
            current_price_per_hour=0.5,
            availability_status="available",
            region="eu-central",
            performance_score=99.0,
            last_updated=datetime.utcnow()
        )
        
        marketplace_cache.cache.get.return_value = [existing_gpu.__dict__]
        
        # Update status
        await marketplace_cache.update_gpu_status("gpu_003", "maintenance")
        
        # Verify notification was sent
        marketplace_cache.cache.notify_gpu_availability_change.assert_called_once_with(
            "gpu_003", "maintenance"
        )
    
    @pytest.mark.asyncio
    async def test_dynamic_pricing(self, marketplace_cache):
        """Test dynamic pricing calculation"""
        # Mock GPU data with low availability
        gpus = [
            GPUInfo(
                gpu_id="gpu_004",
                provider_id="provider_4",
                gpu_type="RTX 3080",
                memory_gb=10,
                cuda_cores=8704,
                base_price_per_hour=0.1,
                current_price_per_hour=0.1,
                availability_status="available",
                region="us-east",
                performance_score=95.0,
                last_updated=datetime.utcnow()
            )
            # Only 1 GPU available (low availability scenario)
        ]
        
        marketplace_cache.cache.get.return_value = [gpus[0].__dict__]
        
        # Calculate dynamic pricing
        price = await marketplace_cache.get_dynamic_pricing("gpu_004")
        
        # Should be higher than base price due to low availability
        assert price > gpus[0].base_price_per_hour
    
    @pytest.mark.asyncio
    async def test_booking_creation(self, marketplace_cache):
        """Test booking creation with cache updates"""
        booking = BookingInfo(
            booking_id="booking_001",
            gpu_id="gpu_005",
            user_id="user_123",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=2),
            status="active",
            total_cost=0.2,
            created_at=datetime.utcnow()
        )
        
        # Mock GPU data
        gpu = GPUInfo(
            gpu_id="gpu_005",
            provider_id="provider_5",
            gpu_type="RTX 3080",
            memory_gb=10,
            cuda_cores=8704,
            base_price_per_hour=0.1,
            current_price_per_hour=0.1,
            availability_status="available",
            region="us-east",
            performance_score=95.0,
            last_updated=datetime.utcnow()
        )
        
        marketplace_cache.cache.get.return_value = [gpu.__dict__]
        
        # Create booking
        result = await marketplace_cache.create_booking(booking)
        
        assert result is True
        
        # Verify GPU status was updated
        marketplace_cache.cache.notify_gpu_availability_change.assert_called()
        
        # Verify booking event was published
        marketplace_cache.cache.notify_booking_created.assert_called_with(
            "booking_001", "gpu_005"
        )
        
        # Verify relevant caches were invalidated
        marketplace_cache.cache.invalidate_cache.assert_any_call('order_book')
        marketplace_cache.cache.invalidate_cache.assert_any_call('market_stats')
    
    @pytest.mark.asyncio
    async def test_booking_cancellation(self, marketplace_cache):
        """Test booking cancellation with cache updates"""
        # Mock GPU data
        gpu = GPUInfo(
            gpu_id="gpu_006",
            provider_id="provider_6",
            gpu_type="RTX 3090",
            memory_gb=24,
            cuda_cores=10496,
            base_price_per_hour=0.15,
            current_price_per_hour=0.15,
            availability_status="busy",
            region="us-west",
            performance_score=98.0,
            last_updated=datetime.utcnow()
        )
        
        marketplace_cache.cache.get.return_value = [gpu.__dict__]
        
        # Cancel booking
        result = await marketplace_cache.cancel_booking("booking_002", "gpu_006")
        
        assert result is True
        
        # Verify GPU status was updated to available
        marketplace_cache.cache.notify_gpu_availability_change.assert_called()
        
        # Verify cancellation event was published
        marketplace_cache.cache.notify_booking_cancelled.assert_called_with(
            "booking_002", "gpu_006"
        )
    
    @pytest.mark.asyncio
    async def test_market_statistics(self, marketplace_cache):
        """Test market statistics calculation"""
        # Mock GPU data
        gpus = [
            GPUInfo(
                gpu_id="gpu_007",
                provider_id="provider_7",
                gpu_type="RTX 3080",
                memory_gb=10,
                cuda_cores=8704,
                base_price_per_hour=0.1,
                current_price_per_hour=0.12,
                availability_status="available",
                region="us-east",
                performance_score=95.0,
                last_updated=datetime.utcnow()
            ),
            GPUInfo(
                gpu_id="gpu_008",
                provider_id="provider_8",
                gpu_type="RTX 3090",
                memory_gb=24,
                cuda_cores=10496,
                base_price_per_hour=0.15,
                current_price_per_hour=0.18,
                availability_status="busy",
                region="us-west",
                performance_score=98.0,
                last_updated=datetime.utcnow()
            )
        ]
        
        marketplace_cache.cache.get.return_value = [gpu.__dict__ for gpu in gpus]
        
        # Get market stats
        stats = await marketplace_cache.get_market_stats()
        
        assert isinstance(stats, MarketStats)
        assert stats.total_gpus == 2
        assert stats.available_gpus == 1
        assert stats.busy_gpus == 1
        assert stats.utilization_rate == 0.5
        assert stats.average_price_per_hour == 0.12  # Average of available GPUs
    
    @pytest.mark.asyncio
    async def test_gpu_search(self, marketplace_cache):
        """Test GPU search functionality"""
        # Mock GPU data
        gpus = [
            GPUInfo(
                gpu_id="gpu_009",
                provider_id="provider_9",
                gpu_type="RTX 3080",
                memory_gb=10,
                cuda_cores=8704,
                base_price_per_hour=0.1,
                current_price_per_hour=0.1,
                availability_status="available",
                region="us-east",
                performance_score=95.0,
                last_updated=datetime.utcnow()
            ),
            GPUInfo(
                gpu_id="gpu_010",
                provider_id="provider_10",
                gpu_type="RTX 3090",
                memory_gb=24,
                cuda_cores=10496,
                base_price_per_hour=0.15,
                current_price_per_hour=0.15,
                availability_status="available",
                region="us-west",
                performance_score=98.0,
                last_updated=datetime.utcnow()
            )
        ]
        
        marketplace_cache.cache.get.return_value = [gpu.__dict__ for gpu in gpus]
        
        # Search with criteria
        results = await marketplace_cache.search_gpus(
            min_memory=16,
            max_price=0.2
        )
        
        # Should only return RTX 3090 (24GB memory, $0.15/hour)
        assert len(results) == 1
        assert results[0].gpu_type == "RTX 3090"
        assert results[0].memory_gb == 24
    
    @pytest.mark.asyncio
    async def test_top_performing_gpus(self, marketplace_cache):
        """Test getting top performing GPUs"""
        # Mock GPU data with different performance scores
        gpus = [
            GPUInfo(
                gpu_id="gpu_011",
                provider_id="provider_11",
                gpu_type="A100",
                memory_gb=40,
                cuda_cores=6912,
                base_price_per_hour=0.5,
                current_price_per_hour=0.5,
                availability_status="available",
                region="us-east",
                performance_score=99.0,
                last_updated=datetime.utcnow()
            ),
            GPUInfo(
                gpu_id="gpu_012",
                provider_id="provider_12",
                gpu_type="RTX 3080",
                memory_gb=10,
                cuda_cores=8704,
                base_price_per_hour=0.1,
                current_price_per_hour=0.1,
                availability_status="available",
                region="us-west",
                performance_score=95.0,
                last_updated=datetime.utcnow()
            )
        ]
        
        marketplace_cache.cache.get.return_value = [gpu.__dict__ for gpu in gpus]
        
        # Get top performing GPUs
        top_gpus = await marketplace_cache.get_top_performing_gpus(limit=2)
        
        assert len(top_gpus) == 2
        assert top_gpus[0].performance_score >= top_gpus[1].performance_score
        assert top_gpus[0].gpu_type == "A100"
    
    @pytest.mark.asyncio
    async def test_cheapest_gpus(self, marketplace_cache):
        """Test getting cheapest GPUs"""
        # Mock GPU data with different prices
        gpus = [
            GPUInfo(
                gpu_id="gpu_013",
                provider_id="provider_13",
                gpu_type="RTX 3060",
                memory_gb=12,
                cuda_cores=3584,
                base_price_per_hour=0.05,
                current_price_per_hour=0.05,
                availability_status="available",
                region="us-east",
                performance_score=85.0,
                last_updated=datetime.utcnow()
            ),
            GPUInfo(
                gpu_id="gpu_014",
                provider_id="provider_14",
                gpu_type="RTX 3080",
                memory_gb=10,
                cuda_cores=8704,
                base_price_per_hour=0.1,
                current_price_per_hour=0.1,
                availability_status="available",
                region="us-west",
                performance_score=95.0,
                last_updated=datetime.utcnow()
            )
        ]
        
        marketplace_cache.cache.get.return_value = [gpu.__dict__ for gpu in gpus]
        
        # Get cheapest GPUs
        cheapest_gpus = await marketplace_cache.get_cheapest_gpus(limit=2)
        
        assert len(cheapest_gpus) == 2
        assert cheapest_gpus[0].current_price_per_hour <= cheapest_gpus[1].current_price_per_hour
        assert cheapest_gpus[0].gpu_type == "RTX 3060"


class TestCacheIntegration:
    """Test integration between cache components"""
    
    @pytest.mark.asyncio
    async def test_marketplace_cache_initialization(self):
        """Test marketplace cache manager initialization"""
        with patch('aitbc_cache.gpu_marketplace_cache.EventDrivenCacheManager') as mock_cache:
            mock_manager = AsyncMock()
            mock_cache.return_value = mock_manager
            mock_manager.connect = AsyncMock()
            
            # Initialize marketplace cache
            manager = await init_marketplace_cache(
                redis_url="redis://localhost:6379/2",
                node_id="test_node",
                region="test_region"
            )
            
            assert isinstance(manager, GPUMarketplaceCacheManager)
            mock_cache.assert_called_once()
            mock_manager.connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_global_marketplace_cache_access(self):
        """Test global marketplace cache access"""
        # Mock the global cache
        with patch('aitbc_cache.gpu_marketplace_cache.marketplace_cache') as mock_global:
            mock_global.get = AsyncMock()
            
            # Should work when initialized
            result = await get_marketplace_cache()
            assert result is not None
        
        # Should raise error when not initialized
        with patch('aitbc_cache.gpu_marketplace_cache.marketplace_cache', None):
            with pytest.raises(RuntimeError, match="Marketplace cache not initialized"):
                await get_marketplace_cache()


class TestCacheEventTypes:
    """Test different cache event types"""
    
    @pytest.mark.asyncio
    async def test_all_event_types(self):
        """Test all supported cache event types"""
        event_types = [
            CacheEventType.GPU_AVAILABILITY_CHANGED,
            CacheEventType.PRICING_UPDATED,
            CacheEventType.BOOKING_CREATED,
            CacheEventType.BOOKING_CANCELLED,
            CacheEventType.PROVIDER_STATUS_CHANGED,
            CacheEventType.MARKET_STATS_UPDATED,
            CacheEventType.ORDER_BOOK_UPDATED,
            CacheEventType.MANUAL_INVALIDATION
        ]
        
        for event_type in event_types:
            # Verify event type can be serialized
            event = CacheEvent(
                event_type=event_type,
                resource_id="test_resource",
                data={"test": "data"},
                timestamp=time.time(),
                source_node="test_node",
                event_id="test_event",
                affected_namespaces=["test_namespace"]
            )
            
            # Test JSON serialization
            event_json = json.dumps(event.__dict__, default=str)
            parsed_event = json.loads(event_json)
            
            assert parsed_event['event_type'] == event_type.value
            assert parsed_event['resource_id'] == "test_resource"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
