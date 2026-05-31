"""
Tests for Redis caching utilities
"""


from aitbc.redis_cache import RedisCache, cache_key, get_cache


class TestRedisCache:
    """Tests for RedisCache class (disabled cache mode)"""

    def test_init_without_redis(self):
        """Test initialization without Redis available"""
        cache = RedisCache(redis_url=None)
        assert cache.is_available() is False

    def test_get_without_redis(self):
        """Test get operation without Redis"""
        cache = RedisCache(redis_url=None)
        result = cache.get("test_key")
        assert result is None

    def test_set_without_redis(self):
        """Test set operation without Redis"""
        cache = RedisCache(redis_url=None)
        result = cache.set("test_key", {"key": "value"})
        assert result is False

    def test_delete_without_redis(self):
        """Test delete operation without Redis"""
        cache = RedisCache(redis_url=None)
        result = cache.delete("test_key")
        assert result is False

    def test_exists_without_redis(self):
        """Test exists operation without Redis"""
        cache = RedisCache(redis_url=None)
        result = cache.exists("test_key")
        assert result is False

    def test_clear_without_redis(self):
        """Test clear operation without Redis"""
        cache = RedisCache(redis_url=None)
        result = cache.clear()
        assert result is False

    def test_get_many_without_redis(self):
        """Test get_many operation without Redis"""
        cache = RedisCache(redis_url=None)
        result = cache.get_many(["key1", "key2"])
        assert result == {}

    def test_set_many_without_redis(self):
        """Test set_many operation without Redis"""
        cache = RedisCache(redis_url=None)
        result = cache.set_many({"key1": "value1"})
        assert result is False

    def test_delete_many_without_redis(self):
        """Test delete_many operation without Redis"""
        cache = RedisCache(redis_url=None)
        result = cache.delete_many(["key1"])
        assert result is False

    def test_increment_without_redis(self):
        """Test increment operation without Redis"""
        cache = RedisCache(redis_url=None)
        result = cache.increment("counter")
        assert result is None


class TestGetCache:
    """Tests for get_cache function"""

    def test_get_cache_without_url(self):
        """Test get_cache without URL returns disabled cache"""
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
