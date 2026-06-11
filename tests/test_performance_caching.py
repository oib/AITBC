"""
Performance Caching Tests
Tests for enhanced caching strategies including blockchain-specific caching
"""

from unittest.mock import Mock

import pytest

from aitbc.caching import (
    BlockchainCache,
    CacheInvalidator,
    CacheMetrics,
    LRUCache,
    get_blockchain_cache,
    get_cache_metrics,
)


class TestBlockchainCache:
    """Test blockchain-specific caching functionality"""

    def test_generate_account_key(self):
        """Test account balance cache key generation"""
        cache = BlockchainCache()
        
        key1 = cache.generate_account_key("0x1234567890abcdef1234567890abcdef12345678", 1)
        key2 = cache.generate_account_key("0x1234567890abcdef1234567890abcdef12345678", 1)
        key3 = cache.generate_account_key("0x1234567890abcdef1234567890abcdef12345678", 2)
        
        # Same address and chain should generate same key
        assert key1 == key2
        # Different chain should generate different key
        assert key1 != key3
        # Should contain the correct prefix
        assert "account_balance" in key1
        assert "1" in key1  # chain ID
        assert "1234567890abcdef1234567890abcdef12345678" in key1  # address (lowercase)

    def test_generate_block_key(self):
        """Test block cache key generation"""
        cache = BlockchainCache()
        
        key = cache.generate_block_key(12345, 1)
        assert "block" in key
        assert "1" in key  # chain ID
        assert "12345" in key  # block number

    def test_generate_transaction_key(self):
        """Test transaction cache key generation"""
        cache = BlockchainCache()
        
        tx_hash = "0x" + "a" * 64
        key = cache.generate_transaction_key(tx_hash, 1)
        assert "transaction" in key
        assert "1" in key  # chain ID
        assert tx_hash.lower() in key

    def test_generate_contract_state_key(self):
        """Test contract state cache key generation"""
        cache = BlockchainCache()
        
        key = cache.generate_contract_state_key("0x" + "b" * 40, 1, "slot1")
        assert "contract_state" in key
        assert "1" in key  # chain ID
        assert "slot1" in key  # slot

    def test_generate_market_data_key(self):
        """Test market data cache key generation"""
        cache = BlockchainCache()
        
        key = cache.generate_market_data_key("spot", "BTC-USD")
        assert "market_data" in key
        assert "spot" in key
        assert "BTC-USD" in key

    def test_cache_ttl_defaults(self):
        """Test that cache TTL defaults are appropriate for different data types"""
        cache = BlockchainCache()
        
        # Account balances should have short TTL (change frequently)
        assert cache.TTL_ACCOUNT_BALANCE == 30
        # Block data should have longer TTL (stable)
        assert cache.TTL_BLOCK == 3600
        # Transaction data should have very long TTL (immutable)
        assert cache.TTL_TRANSACTION == 86400
        # Contract state should have moderate TTL (changes frequently)
        assert cache.TTL_CONTRACT_STATE == 60
        # Chain state should have very short TTL (changes very frequently)
        assert cache.TTL_CHAIN_STATE == 10

    def test_get_cache_stats(self):
        """Test blockchain cache statistics"""
        cache = BlockchainCache()
        stats = cache.get_cache_stats()
        
        assert "redis_available" in stats
        assert "prefixes" in stats
        assert "default_ttl" in stats
        assert "subscribers" in stats
        assert stats["prefixes"]["account_balance"] == cache.PREFIX_ACCOUNT_BALANCE


class TestCacheMetrics:
    """Test cache performance metrics tracking"""

    def test_record_hit(self):
        """Test recording cache hits"""
        metrics = CacheMetrics()
        
        metrics.record_hit("test_operation", 1.5)
        metrics.record_hit("test_operation", 2.0)
        
        stats = metrics.get_stats()
        assert stats["total_requests"] == 2
        assert stats["total_hits"] == 2
        assert stats["total_misses"] == 0
        assert stats["hit_rate"] == 1.0
        assert stats["operation_stats"]["test_operation"]["hits"] == 2

    def test_record_miss(self):
        """Test recording cache misses"""
        metrics = CacheMetrics()
        
        metrics.record_miss("test_operation", 1.5)
        metrics.record_miss("test_operation", 2.0)
        
        stats = metrics.get_stats()
        assert stats["total_requests"] == 2
        assert stats["total_hits"] == 0
        assert stats["total_misses"] == 2
        assert stats["hit_rate"] == 0.0
        assert stats["operation_stats"]["test_operation"]["misses"] == 2

    def test_record_error(self):
        """Test recording cache errors"""
        metrics = CacheMetrics()
        
        metrics.record_error("test_operation", 1.5)
        
        stats = metrics.get_stats()
        assert stats["total_requests"] == 1
        assert stats["total_errors"] == 1
        assert stats["error_rate"] == 1.0

    def test_mixed_operations(self):
        """Test recording mixed cache operations"""
        metrics = CacheMetrics()
        
        metrics.record_hit("test_operation", 1.0)
        metrics.record_miss("test_operation", 1.5)
        metrics.record_hit("test_operation", 2.0)
        
        stats = metrics.get_stats()
        assert stats["total_requests"] == 3
        assert stats["total_hits"] == 2
        assert stats["total_misses"] == 1
        assert stats["hit_rate"] == 2/3

    def test_multiple_operations(self):
        """Test tracking multiple different operations"""
        metrics = CacheMetrics()
        
        metrics.record_hit("operation1", 1.0)
        metrics.record_miss("operation2", 1.5)
        metrics.record_hit("operation1", 2.0)
        
        stats = metrics.get_stats()
        assert len(stats["operation_stats"]) == 2
        assert stats["operation_stats"]["operation1"]["hits"] == 2
        assert stats["operation_stats"]["operation2"]["misses"] == 1

    def test_average_duration_calculation(self):
        """Test average duration calculation per operation"""
        metrics = CacheMetrics()
        
        metrics.record_hit("test_operation", 1.0)
        metrics.record_hit("test_operation", 2.0)
        metrics.record_hit("test_operation", 3.0)
        
        stats = metrics.get_stats()
        avg_duration = stats["operation_stats"]["test_operation"]["avg_duration_ms"]
        assert avg_duration == 2.0  # (1.0 + 2.0 + 3.0) / 3

    def test_metrics_reset(self):
        """Test resetting cache metrics"""
        metrics = CacheMetrics()
        
        metrics.record_hit("test_operation", 1.0)
        metrics.reset()
        
        stats = metrics.get_stats()
        assert stats["total_requests"] == 0
        assert stats["total_hits"] == 0
        assert stats["total_misses"] == 0
        assert len(stats["operation_stats"]) == 0


class TestCacheInvalidator:
    """Test automatic cache invalidation based on blockchain events"""

    def test_on_new_block_invalidation(self):
        """Test cache invalidation on new block"""
        mock_redis_cache = Mock()
        mock_redis_cache._client = Mock()
        mock_redis_cache._client.keys = Mock(return_value=[])
        
        mock_cache = Mock(spec=BlockchainCache)
        mock_cache.redis_cache = mock_redis_cache
        mock_cache.invalidate_block = Mock(return_value=True)
        mock_cache.invalidate_chain_state = Mock(return_value=5)
        mock_cache.invalidate_account = Mock(return_value=1)
        
        invalidator = CacheInvalidator(mock_cache)
        
        event_data = {
            "chain_id": 1,
            "block_number": 12345
        }
        
        invalidated = invalidator._on_new_block(event_data)
        
        assert mock_cache.invalidate_block.called
        assert mock_cache.invalidate_chain_state.called
        assert invalidated > 0

    def test_on_new_transaction_invalidation(self):
        """Test cache invalidation on new transaction"""
        mock_cache = Mock(spec=BlockchainCache)
        mock_cache.invalidate_account = Mock(return_value=True)
        mock_cache.invalidate_contract_state = Mock(return_value=True)
        
        invalidator = CacheInvalidator(mock_cache)
        
        event_data = {
            "chain_id": 1,
            "from_address": "0x" + "a" * 40,
            "to_address": "0x" + "b" * 40,
            "contract_address": "0x" + "c" * 40
        }
        
        invalidated = invalidator._on_new_transaction(event_data)
        
        assert mock_cache.invalidate_account.call_count == 2  # from and to addresses
        assert mock_cache.invalidate_contract_state.called
        assert invalidated > 0

    def test_on_contract_state_changed_invalidation(self):
        """Test cache invalidation on contract state change"""
        mock_cache = Mock(spec=BlockchainCache)
        mock_cache.invalidate_contract_state = Mock(return_value=2)
        
        invalidator = CacheInvalidator(mock_cache)
        
        event_data = {
            "chain_id": 1,
            "contract_address": "0x" + "c" * 40,
            "slot": "slot1"
        }
        
        invalidated = invalidator._on_contract_state_changed(event_data)
        
        assert mock_cache.invalidate_contract_state.called
        assert invalidated >= 0

    def test_handle_event_dispatching(self):
        """Test event dispatching to appropriate handlers"""
        mock_redis_cache = Mock()
        mock_redis_cache._client = Mock()
        mock_redis_cache._client.keys = Mock(return_value=[])
        
        mock_cache = Mock(spec=BlockchainCache)
        mock_cache.redis_cache = mock_redis_cache
        mock_cache.invalidate_block = Mock(return_value=True)
        mock_cache.invalidate_chain_state = Mock(return_value=5)
        
        invalidator = CacheInvalidator(mock_cache)
        
        # Test new block event
        event_data = {"chain_id": 1, "block_number": 12345}
        invalidated = invalidator.handle_event("new_block", event_data)
        assert invalidated > 0
        
        # Test unknown event (should return 0)
        invalidated = invalidator.handle_event("unknown_event", {})
        assert invalidated == 0


class TestLRUCacheEnhancements:
    """Test enhanced LRU cache with new CacheEntry fields"""

    def test_cache_entry_tracking(self):
        """Test that cache entries track access times"""
        cache = LRUCache(capacity=10)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        # Access key1
        cache.get("key1")
        
        # Access key2
        cache.get("key2")
        
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["size"] == 2

    def test_cache_expiration_with_access_tracking(self):
        """Test cache expiration with access time tracking"""
        cache = LRUCache(capacity=10)
        
        # Set entry with short TTL
        cache.set("key1", "value1", ttl=1)
        
        # Should be accessible immediately
        assert cache.get("key1") == "value1"
        
        # Wait for expiration
        import time
        time.sleep(1.1)
        
        # Should be expired now
        assert cache.get("key1") is None


class TestGlobalCacheFunctions:
    """Test global cache functions"""

    def test_get_cache_metrics_singleton(self):
        """Test that get_cache_metrics returns singleton instance"""
        metrics1 = get_cache_metrics()
        metrics2 = get_cache_metrics()
        
        assert metrics1 is metrics2

    def test_get_blockchain_cache(self):
        """Test blockchain cache factory function"""
        cache = get_blockchain_cache()
        
        assert isinstance(cache, BlockchainCache)
        assert cache.redis_cache is not None  # Should create Redis cache


if __name__ == "__main__":
    pytest.main([__file__, "-v"])