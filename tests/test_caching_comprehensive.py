"""Comprehensive tests for aitbc.caching"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from aitbc.caching import (
    BlockchainCache,
    CacheEntry,
    CacheInvalidator,
    CacheMetrics,
    LRUCache,
    RedisCache,
    TTLCache,
    _generate_blockchain_cache_key,
    _generate_cache_key,
    cached,
    cached_lru,
    clear_global_caches,
    generate_cache_key,
    get_blockchain_cache,
    get_cache,
    get_cache_metrics,
    get_global_lru_cache,
    get_global_ttl_cache,
)


class TestCacheEntry:
    def test_is_expired_none(self):
        entry = CacheEntry(value="test")
        assert entry.is_expired() is False

    def test_is_expired_future(self):
        entry = CacheEntry(value="test", expires_at=datetime.now() + timedelta(hours=1))
        assert entry.is_expired() is False

    def test_is_expired_past(self):
        entry = CacheEntry(value="test", expires_at=datetime.now() - timedelta(hours=1))
        assert entry.is_expired() is True

    def test_update_access(self):
        entry = CacheEntry(value="test")
        old_time = entry.last_accessed
        entry.update_access()
        assert entry.last_accessed >= old_time


class TestBlockchainCache:
    def test_generate_account_key(self):
        bc = BlockchainCache()
        key = bc.generate_account_key("0xAbC", 1)
        assert key == "account_balance:1:0xabc"

    def test_generate_block_key(self):
        bc = BlockchainCache()
        key = bc.generate_block_key(100, 1)
        assert key == "block:1:100"

    def test_generate_transaction_key(self):
        bc = BlockchainCache()
        key = bc.generate_transaction_key("0xTx", 1)
        assert key == "transaction:1:0xtx"

    def test_generate_contract_state_key(self):
        bc = BlockchainCache()
        key = bc.generate_contract_state_key("0xContract", 1, "slot1")
        assert key == "contract_state:1:0xcontract:slot1"

    def test_generate_contract_state_key_no_slot(self):
        bc = BlockchainCache()
        key = bc.generate_contract_state_key("0xContract", 1)
        assert key == "contract_state:1:0xcontract"

    def test_generate_chain_state_key(self):
        bc = BlockchainCache()
        key = bc.generate_chain_state_key(1, "syncing")
        assert key == "chain_state:1:syncing"

    def test_generate_market_data_key(self):
        bc = BlockchainCache()
        key = bc.generate_market_data_key("spot", "ETH-USD")
        assert key == "market_data:spot:ETH-USD"

    def test_get_account_balance_no_redis(self):
        bc = BlockchainCache()
        assert bc.get_account_balance("0xabc", 1) is None

    def test_set_account_balance_no_redis(self):
        bc = BlockchainCache()
        assert bc.set_account_balance("0xabc", 1, 100) is False

    def test_get_block_no_redis(self):
        bc = BlockchainCache()
        assert bc.get_block(100, 1) is None

    def test_set_block_no_redis(self):
        bc = BlockchainCache()
        assert bc.set_block(100, 1, {"hash": "0x"}) is False

    def test_get_transaction_no_redis(self):
        bc = BlockchainCache()
        assert bc.get_transaction("0xtx", 1) is None

    def test_set_transaction_no_redis(self):
        bc = BlockchainCache()
        assert bc.set_transaction("0xtx", 1, {"from": "a"}) is False

    def test_invalidate_account_no_redis(self):
        bc = BlockchainCache()
        assert bc.invalidate_account("0xabc", 1) is False

    def test_invalidate_block_no_redis(self):
        bc = BlockchainCache()
        assert bc.invalidate_block(100, 1) is False

    def test_invalidate_contract_state_no_redis(self):
        bc = BlockchainCache()
        assert bc.invalidate_contract_state("0xabc", 1) is False

    def test_invalidate_chain_state_no_redis(self):
        bc = BlockchainCache()
        assert bc.invalidate_chain_state(1, "syncing") == 0

    def test_invalidate_chain_state_all_no_redis(self):
        bc = BlockchainCache()
        assert bc.invalidate_chain_state(1) == 0

    def test_subscribe_and_notify(self):
        bc = BlockchainCache()
        calls = []
        bc.subscribe_to_invalidation(lambda t, d: calls.append((t, d)))
        bc._notify_subscribers("test", {"k": "v"})
        assert len(calls) == 1

    def test_notify_error_in_callback(self):
        bc = BlockchainCache()
        bc.subscribe_to_invalidation(lambda t, d: (_ for _ in ()).throw(Exception("fail")))
        bc._notify_subscribers("test", {})  # should not raise

    def test_get_cache_stats_no_redis(self):
        bc = BlockchainCache()
        stats = bc.get_cache_stats()
        assert stats["redis_available"] is False
        assert stats["subscribers"] == 0

    def test_with_mock_redis(self):
        mock_redis = MagicMock()
        mock_redis.is_available.return_value = True
        bc = BlockchainCache(redis_cache=mock_redis)
        bc.get_account_balance("0xabc", 1)
        mock_redis.get.assert_called_once()


class TestCacheMetrics:
    def test_record_hit(self):
        m = CacheMetrics()
        m.record_hit("get", 10.0)
        assert m.total_hits == 1
        assert m.total_requests == 1

    def test_record_miss(self):
        m = CacheMetrics()
        m.record_miss("get", 5.0)
        assert m.total_misses == 1
        assert m.total_requests == 1

    def test_record_error(self):
        m = CacheMetrics()
        m.record_error("get", 1.0)
        assert m.total_errors == 1
        assert m.total_requests == 1

    def test_get_stats(self):
        m = CacheMetrics()
        m.record_hit("get", 10.0)
        m.record_miss("get", 5.0)
        stats = m.get_stats()
        assert stats["hit_rate"] == 0.5
        assert "get" in stats["operation_stats"]

    def test_reset(self):
        m = CacheMetrics()
        m.record_hit("get", 10.0)
        m.reset()
        assert m.total_requests == 0

    def test_get_cache_metrics_singleton(self):
        m1 = get_cache_metrics()
        m2 = get_cache_metrics()
        assert m1 is m2


class TestLRUCache:
    def test_get_miss(self):
        cache = LRUCache(capacity=2)
        assert cache.get("missing") is None
        assert cache._misses == 1

    def test_set_and_get(self):
        cache = LRUCache(capacity=2)
        cache.set("key", "value")
        assert cache.get("key") == "value"
        assert cache._hits == 1

    def test_expired_entry(self):
        cache = LRUCache(capacity=2)
        cache.set("key", "value", ttl=0)
        assert cache.get("key") is None

    def test_eviction(self):
        cache = LRUCache(capacity=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert cache.get("a") is None
        assert cache.get("c") == 3

    def test_lru_order(self):
        cache = LRUCache(capacity=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")
        cache.set("c", 3)
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_clear(self):
        cache = LRUCache(capacity=2)
        cache.set("a", 1)
        cache.clear()
        assert cache.get("a") is None

    def test_get_stats(self):
        cache = LRUCache(capacity=2)
        cache.get("missing")
        cache.set("key", "value")
        cache.get("key")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_print_stats(self):
        cache = LRUCache(capacity=2)
        cache.print_stats()  # should not raise


class TestTTLCache:
    def test_get_miss(self):
        cache = TTLCache(default_ttl=300)
        assert cache.get("missing") is None
        assert cache._misses == 1

    def test_set_and_get(self):
        cache = TTLCache(default_ttl=300)
        cache.set("key", "value")
        assert cache.get("key") == "value"
        assert cache._hits == 1

    def test_expired_entry(self):
        cache = TTLCache(default_ttl=0)
        cache.set("key", "value")
        assert cache.get("key") is None

    def test_clear(self):
        cache = TTLCache(default_ttl=300)
        cache.set("a", 1)
        cache.clear()
        assert cache.get("a") is None

    def test_cleanup_expired(self):
        cache = TTLCache(default_ttl=0)
        cache.set("a", 1)
        count = cache.cleanup_expired()
        assert count == 1
        assert cache.get("a") is None

    def test_get_stats(self):
        cache = TTLCache(default_ttl=300)
        cache.get("missing")
        cache.set("key", "value")
        cache.get("key")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1


class TestCachedDecorator:
    def test_cached_basic(self):
        call_count = 0

        @cached(ttl=300)
        def my_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        assert my_func(5) == 10
        assert my_func(5) == 10
        assert call_count == 1

    def test_cached_lru_basic(self):
        call_count = 0

        @cached_lru(capacity=2)
        def my_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        assert my_func(5) == 10
        assert my_func(5) == 10
        assert call_count == 1


class TestCacheKeyGeneration:
    def test_generate_cache_key_simple(self):
        key = generate_cache_key("prefix", "arg1", "arg2")
        assert key == "prefix:arg1:arg2"

    def test_generate_cache_key_kwargs(self):
        key = generate_cache_key("prefix", "arg1", foo="bar")
        assert "foo=bar" in key

    def test_generate_cache_key_long(self):
        key = generate_cache_key("prefix", "x" * 300)
        assert key.startswith("prefix:")
        assert len(key) <= 50

    def test_internal_generate_cache_key(self):
        key = _generate_cache_key("func", (1, "a"), {"b": 2})
        assert key.startswith("func:1:a:b=2")

    def test_internal_generate_cache_key_complex(self):
        key = _generate_cache_key("func", ([1, 2],), {})
        assert key.startswith("func:")

    def test_blockchain_cache_key(self):
        key = _generate_blockchain_cache_key("account", (), {"address": "0xABC", "chain_id": 1})
        assert "addr:0xabc" in key
        assert "chain:1" in key


class TestGlobalCaches:
    def test_get_global_lru_cache(self):
        cache = get_global_lru_cache()
        assert isinstance(cache, LRUCache)

    def test_get_global_ttl_cache(self):
        cache = get_global_ttl_cache()
        assert isinstance(cache, TTLCache)

    def test_clear_global_caches(self):
        get_global_lru_cache().set("a", 1)
        get_global_ttl_cache().set("b", 2)
        clear_global_caches()
        assert get_global_lru_cache().get("a") is None
        assert get_global_ttl_cache().get("b") is None


class TestCacheInvalidator:
    def test_handle_event_unknown(self):
        bc = BlockchainCache()
        inv = CacheInvalidator(bc)
        assert inv.handle_event("unknown", {}) == 0

    def test_handle_event_new_block_no_redis(self):
        bc = BlockchainCache()
        inv = CacheInvalidator(bc)
        assert inv.handle_event("new_block", {"chain_id": 1, "block_number": 100}) == 0

    def test_handle_event_new_transaction_no_redis(self):
        bc = BlockchainCache()
        inv = CacheInvalidator(bc)
        assert inv.handle_event("new_transaction", {"chain_id": 1, "from_address": "a"}) == 0

    def test_handle_event_contract_state_no_redis(self):
        bc = BlockchainCache()
        inv = CacheInvalidator(bc)
        assert inv.handle_event("contract_state_changed", {"chain_id": 1, "contract_address": "a"}) == 0

    def test_handle_event_account_balance_no_redis(self):
        bc = BlockchainCache()
        inv = CacheInvalidator(bc)
        assert inv.handle_event("account_balance_changed", {"chain_id": 1, "address": "a"}) == 0

    def test_on_contract_state_no_slot(self):
        bc = BlockchainCache()
        inv = CacheInvalidator(bc)
        assert inv._on_contract_state_changed({"chain_id": 1, "contract_address": "a"}) == 0

    def test_on_account_balance_no_data(self):
        bc = BlockchainCache()
        inv = CacheInvalidator(bc)
        assert inv._on_account_balance_changed({}) == 0


class TestRedisCache:
    def test_init_without_redis(self):
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = RedisCache(redis_url=None)
        assert cache.is_available() is False

    def test_get_fallback(self):
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = RedisCache(redis_url=None)
        cache._data["key"] = "value"
        assert cache.get("key") == "value"

    def test_set_fallback(self):
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = RedisCache(redis_url=None)
        assert cache.set("key", "value") is True
        assert cache._data["key"] == "value"

    def test_delete_fallback(self):
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = RedisCache(redis_url=None)
        cache._data["key"] = "value"
        assert cache.delete("key") is True
        assert "key" not in cache._data

    def test_delete_missing(self):
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            cache = RedisCache(redis_url=None)
        assert cache.delete("missing") is False


class TestGetCache:
    def test_get_cache_singleton(self):
        import aitbc.caching as caching

        caching._global_redis_cache = None
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            c1 = get_cache()
            c2 = get_cache()
        assert c1 is c2

    def test_get_blockchain_cache(self):
        import aitbc.caching as caching

        caching._global_redis_cache = None
        with patch("redis.from_url", side_effect=Exception("No Redis")):
            bc = get_blockchain_cache()
        assert isinstance(bc, BlockchainCache)
