"""
Tests for caching utilities
"""

import time
from datetime import datetime, timedelta
from unittest.mock import patch

from aitbc.caching import (
    CacheEntry,
    LRUCache,
    TTLCache,
    _generate_cache_key,
    cached,
    cached_lru,
    clear_global_caches,
    get_global_lru_cache,
    get_global_ttl_cache,
)


class TestCacheEntry:
    """Tests for CacheEntry"""

    def test_cache_entry_creation(self):
        """Test CacheEntry creation"""
        entry = CacheEntry(value="test_value")
        assert entry.value == "test_value"
        assert entry.expires_at is None
        assert entry.hit_count == 0

    def test_cache_entry_with_expiration(self):
        """Test CacheEntry with expiration"""
        expires = datetime.now() + timedelta(seconds=60)
        entry = CacheEntry(value="test_value", expires_at=expires)
        assert entry.expires_at == expires

    def test_is_expired_no_expiration(self):
        """Test is_expired when no expiration set"""
        entry = CacheEntry(value="test_value")
        assert entry.is_expired() is False

    def test_is_expired_not_expired(self):
        """Test is_expired when not yet expired"""
        expires = datetime.now() + timedelta(seconds=60)
        entry = CacheEntry(value="test_value", expires_at=expires)
        assert entry.is_expired() is False

    def test_is_expired_expired(self):
        """Test is_expired when expired"""
        expires = datetime.now() - timedelta(seconds=1)
        entry = CacheEntry(value="test_value", expires_at=expires)
        assert entry.is_expired() is True


class TestLRUCache:
    """Tests for LRUCache"""

    def test_initialization(self):
        """Test LRUCache initialization"""
        cache = LRUCache(capacity=10)
        assert cache.capacity == 10
        assert len(cache.cache) == 0
        assert cache._hits == 0
        assert cache._misses == 0

    def test_get_miss(self):
        """Test get when key not in cache"""
        cache = LRUCache()
        result = cache.get("nonexistent")
        assert result is None
        assert cache._misses == 1

    def test_get_hit(self):
        """Test get when key in cache"""
        cache = LRUCache()
        cache.set("key1", "value1")
        result = cache.get("key1")
        assert result == "value1"
        assert cache._hits == 1

    def test_get_expired(self):
        """Test get when entry expired"""
        cache = LRUCache()
        cache.set("key1", "value1", ttl=1)
        time.sleep(1.1)
        result = cache.get("key1")
        assert result is None
        assert cache._misses == 1

    def test_set_basic(self):
        """Test set basic functionality"""
        cache = LRUCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_set_with_ttl(self):
        """Test set with TTL"""
        cache = LRUCache()
        cache.set("key1", "value1", ttl=60)
        assert cache.get("key1") == "value1"

    def test_set_overwrite(self):
        """Test set overwrites existing key"""
        cache = LRUCache()
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

    def test_set_eviction(self):
        """Test LRU eviction when capacity exceeded"""
        cache = LRUCache(capacity=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should evict key1 (least recently used)
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_clear(self):
        """Test clear cache"""
        cache = LRUCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert len(cache.cache) == 0
        assert cache.get("key1") is None

    def test_get_stats(self):
        """Test get cache statistics"""
        cache = LRUCache(capacity=10)
        cache.set("key1", "value1")
        cache.get("key1")
        cache.get("key2")  # miss

        stats = cache.get_stats()
        assert stats["capacity"] == 10
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_get_stats_empty(self):
        """Test get stats on empty cache"""
        cache = LRUCache()
        stats = cache.get_stats()
        assert stats["hit_rate"] == 0

    @patch('aitbc.caching.logger')
    def test_print_stats(self, mock_logger):
        """Test print stats logs output"""
        cache = LRUCache()
        cache.set("key1", "value1")
        cache.print_stats()
        assert mock_logger.info.called

    def test_lru_ordering(self):
        """Test that recently used items are moved to end"""
        cache = LRUCache(capacity=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to make it recently used
        cache.get("key1")

        # Add key4, should evict key2 (not key1)
        cache.set("key4", "value4")
        assert cache.get("key1") == "value1"  # Still in cache
        assert cache.get("key2") is None  # Evicted


class TestTTLCache:
    """Tests for TTLCache"""

    def test_initialization(self):
        """Test TTLCache initialization"""
        cache = TTLCache(default_ttl=60)
        assert cache.default_ttl == 60
        assert len(cache.cache) == 0

    def test_get_miss(self):
        """Test get when key not in cache"""
        cache = TTLCache()
        result = cache.get("nonexistent")
        assert result is None
        assert cache._misses == 1

    def test_get_hit(self):
        """Test get when key in cache"""
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1")
        result = cache.get("key1")
        assert result == "value1"
        assert cache._hits == 1

    def test_get_expired(self):
        """Test get when entry expired"""
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1")
        # Manually set expiration to past
        cache.cache["key1"].expires_at = datetime.now() - timedelta(seconds=1)
        result = cache.get("key1")
        assert result is None
        assert cache._misses == 1

    def test_set_with_default_ttl(self):
        """Test set uses default TTL"""
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1")
        entry = cache.cache["key1"]
        assert entry.expires_at is not None
        assert entry.expires_at > datetime.now()

    def test_set_with_custom_ttl(self):
        """Test set with custom TTL"""
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1", ttl=30)
        entry = cache.cache["key1"]
        assert entry.expires_at is not None
        expected_expires = datetime.now() + timedelta(seconds=30)
        assert abs((entry.expires_at - expected_expires).total_seconds()) < 1

    def test_set_overwrite(self):
        """Test set overwrites existing key"""
        cache = TTLCache()
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

    def test_clear(self):
        """Test clear cache"""
        cache = TTLCache()
        cache.set("key1", "value1")
        cache.clear()
        assert len(cache.cache) == 0

    def test_cleanup_expired(self):
        """Test cleanup expired entries"""
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Expire key1
        cache.cache["key1"].expires_at = datetime.now() - timedelta(seconds=1)

        removed = cache.cleanup_expired()
        assert removed == 1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_cleanup_expired_none(self):
        """Test cleanup when no expired entries"""
        cache = TTLCache()
        cache.set("key1", "value1")
        removed = cache.cleanup_expired()
        assert removed == 0

    def test_get_stats(self):
        """Test get cache statistics"""
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1")
        cache.get("key1")
        cache.get("key2")  # miss

        stats = cache.get_stats()
        assert stats["size"] == 1
        assert stats["default_ttl"] == 60
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


class TestCacheDecorators:
    """Tests for cache decorators"""

    def test_cached_decorator(self):
        """Test cached decorator"""
        call_count = [0]

        @cached(ttl=60)
        def expensive_function(x):
            call_count[0] += 1
            return x * 2

        # First call executes function
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count[0] == 1

        # Second call uses cache
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count[0] == 1  # Should not increment

    def test_cached_decorator_different_args(self):
        """Test cached decorator with different arguments"""
        call_count = [0]

        @cached(ttl=60)
        def expensive_function(x):
            call_count[0] += 1
            return x * 2

        expensive_function(5)
        expensive_function(10)
        assert call_count[0] == 2  # Different args, different cache keys

    def test_cached_decorator_with_custom_cache(self):
        """Test cached decorator with custom cache instance"""
        call_count = [0]
        custom_cache = TTLCache(default_ttl=60)

        @cached(ttl=60, cache_instance=custom_cache)
        def expensive_function(x):
            call_count[0] += 1
            return x * 2

        expensive_function(5)
        expensive_function(5)
        assert call_count[0] == 1

    def test_cached_lru_decorator(self):
        """Test cached_lru decorator"""
        call_count = [0]

        @cached_lru(capacity=10)
        def expensive_function(x):
            call_count[0] += 1
            return x * 2

        expensive_function(5)
        expensive_function(5)
        assert call_count[0] == 1

    def test_cached_lru_decorator_with_ttl(self):
        """Test cached_lru decorator with TTL"""
        call_count = [0]

        @cached_lru(capacity=10, ttl=1)
        def expensive_function(x):
            call_count[0] += 1
            return x * 2

        expensive_function(5)
        expensive_function(5)
        assert call_count[0] == 1

        # Wait for expiration
        time.sleep(1.1)
        expensive_function(5)
        assert call_count[0] == 2  # Should re-execute after expiration

    def test_cached_lru_decorator_eviction(self):
        """Test cached_lru decorator eviction"""
        call_count = [0]

        @cached_lru(capacity=2)
        def expensive_function(x):
            call_count[0] += 1
            return x * 2

        expensive_function(1)
        expensive_function(2)
        expensive_function(3)  # Should evict least recently used
        expensive_function(1)  # Should re-execute
        assert call_count[0] == 4  # All calls executed due to eviction

    def test_decorator_cache_attachment(self):
        """Test that cache is attached to decorated function"""
        @cached(ttl=60)
        def func(x):
            return x * 2

        assert hasattr(func, 'cache')
        assert isinstance(func.cache, TTLCache)


class TestCacheKeyGeneration:
    """Tests for cache key generation"""

    def test_generate_cache_key_simple_args(self):
        """Test cache key with simple arguments"""
        key = _generate_cache_key("func_name", (1, 2, 3), {})
        assert "func_name" in key
        assert "1" in key
        assert "2" in key
        assert "3" in key

    def test_generate_cache_key_with_kwargs(self):
        """Test cache key with keyword arguments"""
        key = _generate_cache_key("func_name", (), {"x": 1, "y": 2})
        assert "x=1" in key
        assert "y=2" in key

    def test_generate_cache_key_complex_args(self):
        """Test cache key with complex arguments"""
        key = _generate_cache_key("func_name", ([1, 2], {"a": 3}), {})
        # Complex args should be hashed
        assert "func_name" in key
        assert len(key.split(":")) >= 3  # func_name + args + hash

    def test_generate_cache_key_consistency(self):
        """Test cache key generation is consistent"""
        key1 = _generate_cache_key("func", (1, 2), {"x": 3})
        key2 = _generate_cache_key("func", (1, 2), {"x": 3})
        assert key1 == key2

    def test_generate_cache_key_different_order(self):
        """Test cache key with different kwarg order"""
        key1 = _generate_cache_key("func", (), {"x": 1, "y": 2})
        key2 = _generate_cache_key("func", (), {"y": 2, "x": 1})
        assert key1 == key2  # Should be same due to sorting


class TestGlobalCaches:
    """Tests for global cache instances"""

    def test_get_global_lru_cache(self):
        """Test get global LRU cache"""
        cache = get_global_lru_cache()
        assert isinstance(cache, LRUCache)
        assert cache.capacity == 256

    def test_get_global_ttl_cache(self):
        """Test get global TTL cache"""
        cache = get_global_ttl_cache()
        assert isinstance(cache, TTLCache)
        assert cache.default_ttl == 300

    def test_global_caches_singleton(self):
        """Test global caches are singletons"""
        cache1 = get_global_lru_cache()
        cache2 = get_global_lru_cache()
        assert cache1 is cache2

    def test_clear_global_caches(self):
        """Test clear all global caches"""
        lru_cache = get_global_lru_cache()
        ttl_cache = get_global_ttl_cache()

        lru_cache.set("key1", "value1")
        ttl_cache.set("key2", "value2")

        clear_global_caches()

        assert lru_cache.get("key1") is None
        assert ttl_cache.get("key2") is None

    @patch('aitbc.caching.logger')
    def test_clear_global_caches_logging(self, mock_logger):
        """Test clear global caches logs"""
        clear_global_caches()
        assert mock_logger.info.called
