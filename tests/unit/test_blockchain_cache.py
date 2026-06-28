"""Unit tests for aitbc.caching.blockchain_cache (A1)."""

from unittest.mock import MagicMock

from aitbc.caching.blockchain_cache import BlockchainCache


class TestBlockchainCacheTyping:
    """A1: chain_id must be str (codebase uses 'ait-hub', not int)."""

    def test_generate_account_key_str_chain_id(self) -> None:
        cache = BlockchainCache()
        key = cache.generate_account_key("0xABC", "ait-hub")
        assert key == "account_balance:ait-hub:0xabc"

    def test_generate_block_key_str_chain_id(self) -> None:
        cache = BlockchainCache()
        key = cache.generate_block_key(42, "ait-island1")
        assert key == "block:ait-island1:42"

    def test_generate_transaction_key_str_chain_id(self) -> None:
        cache = BlockchainCache()
        key = cache.generate_transaction_key("0xTX", "ait-hub")
        assert key == "transaction:ait-hub:0xtx"

    def test_generate_chain_state_key_str_chain_id(self) -> None:
        cache = BlockchainCache()
        key = cache.generate_chain_state_key("ait-hub", "tip")
        assert key == "chain_state:ait-hub:tip"


class TestBlockByHash:
    """A1: get_block_by_hash / set_block_by_hash methods."""

    def test_generate_block_hash_key(self) -> None:
        cache = BlockchainCache()
        key = cache.generate_block_hash_key("0xABC", "ait-hub")
        assert key == "block_hash:ait-hub:0xabc"

    def test_get_block_by_hash_miss_no_redis(self) -> None:
        cache = BlockchainCache()
        assert cache.get_block_by_hash("0xABC", "ait-hub") is None

    def test_set_block_by_hash_no_redis_returns_false(self) -> None:
        cache = BlockchainCache()
        assert cache.set_block_by_hash("0xABC", "ait-hub", {"height": 1}) is False

    def test_set_and_get_block_by_hash_with_redis(self) -> None:
        redis = MagicMock()
        redis.set.return_value = True
        redis.get.return_value = {"height": 42, "hash": "0xabc"}
        cache = BlockchainCache(redis_cache=redis)

        assert cache.set_block_by_hash("0xABC", "ait-hub", {"height": 42}) is True
        redis.set.assert_called_once()
        # The key passed to redis.set should be the block_hash key
        args = redis.set.call_args
        assert "block_hash:ait-hub:0xabc" in args[0][0]

        result = cache.get_block_by_hash("0xABC", "ait-hub")
        assert result == {"height": 42, "hash": "0xabc"}

    def test_invalidate_block_by_hash_with_redis(self) -> None:
        redis = MagicMock()
        redis.delete.return_value = True
        cache = BlockchainCache(redis_cache=redis)

        assert cache.invalidate_block_by_hash("0xABC", "ait-hub") is True
        redis.delete.assert_called_once_with("block_hash:ait-hub:0xabc")


class TestBlockByHeight:
    """A1: get_block / set_block use height (renamed from block_number)."""

    def test_set_and_get_block_with_redis(self) -> None:
        redis = MagicMock()
        redis.set.return_value = True
        redis.get.return_value = {"height": 10}
        cache = BlockchainCache(redis_cache=redis)

        assert cache.set_block(10, "ait-hub", {"height": 10}) is True
        result = cache.get_block(10, "ait-hub")
        assert result == {"height": 10}

    def test_invalidate_block_by_height(self) -> None:
        redis = MagicMock()
        redis.delete.return_value = True
        cache = BlockchainCache(redis_cache=redis)

        assert cache.invalidate_block(10, "ait-hub") is True
        redis.delete.assert_called_once_with("block:ait-hub:10")


class TestCacheStats:
    def test_stats_include_block_hash_prefix(self) -> None:
        cache = BlockchainCache()
        stats = cache.get_cache_stats()
        assert "block_hash" in stats["prefixes"]
        assert stats["prefixes"]["block_hash"] == "block_hash"
