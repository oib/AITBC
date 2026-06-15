"""
Tests for Redis caching utilities
"""

from unittest.mock import patch

from aitbc.redis_cache import RedisCache, cache_key, get_cache


class TestRedisCache:
    """Tests for RedisCache class (disabled cache mode)"""

    def test_init_without_redis(self):
        """Test initialization without Redis available"""
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = RedisCache(redis_url=None)
        assert cache.is_available() is False

    def test_get_without_redis(self):
        """Test get operation without Redis"""
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = RedisCache(redis_url=None)
        result = cache.get("test_key")
        assert result is None

    def test_set_without_redis(self):
        """Test set operation without Redis"""
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = RedisCache(redis_url=None)
        result = cache.set("test_key", {"key": "value"})
        assert result is True
        assert cache.get("test_key") == {"key": "value"}

    def test_delete_without_redis(self):
        """Test delete operation without Redis"""
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = RedisCache(redis_url=None)
        cache.set("test_key", "value")
        result = cache.delete("test_key")
        assert result is True
        assert cache.get("test_key") is None


class TestGetCache:
    """Tests for get_cache function"""

    def test_get_cache_without_url(self):
        """Test get_cache without URL returns disabled cache"""
        import aitbc.caching as caching

        caching._global_redis_cache = None
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = get_cache(redis_url=None)
        assert cache.is_available() is False


class TestCacheKey:
    """Tests for cache_key function"""

    def test_cache_key_simple(self):
        """Test cache_key with simple parts"""
        key = cache_key("user", "123")
        assert key == "aitbc:user:123"

    def test_cache_key_with_prefix(self):
        """Test cache_key with custom prefix"""
        key = cache_key("user", "123", prefix="custom")
        assert key == "custom:user:123"

    def test_cache_key_multiple_parts(self):
        """Test cache_key with multiple parts"""
        key = cache_key("user", "123", "profile", "data")
        assert key == "aitbc:user:123:profile:data"

    def test_cache_key_long_key(self):
        """Test cache_key with long key gets hashed"""
        long_part = "x" * 300
        key = cache_key(long_part, "data")
        assert key.startswith("aitbc:hashed:")
        assert len(key) <= 250
