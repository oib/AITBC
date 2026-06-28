"""Unit tests for aitbc.caching.block_header_cache (A2)."""

from aitbc.caching.block_header_cache import BlockHeaderCache


def _header(height: int, hash: str) -> dict:
    return {"height": height, "hash": hash, "parent_hash": "0xprev", "state_root": "0xroot"}


class TestBlockHeaderCacheBasic:
    def test_get_miss_returns_none(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        assert cache.get(1, "ait-hub") is None
        assert cache.get_by_hash("0xabc", "ait-hub") is None

    def test_set_and_get_by_height(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set(_header(10, "0xAAA"), "ait-hub")
        result = cache.get(10, "ait-hub")
        assert result is not None
        assert result["height"] == 10
        assert result["hash"] == "0xAAA"

    def test_set_and_get_by_hash(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set(_header(10, "0xAAA"), "ait-hub")
        result = cache.get_by_hash("0xAAA", "ait-hub")
        assert result is not None
        assert result["height"] == 10

    def test_set_and_get_by_hash_case_insensitive(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set(_header(10, "0xABC"), "ait-hub")
        # Query with different case should still hit
        assert cache.get_by_hash("0xabc", "ait-hub") is not None
        assert cache.get_by_hash("0xABC", "ait-hub") is not None


class TestBlockHeaderCacheLRU:
    def test_lru_eviction_removes_oldest(self) -> None:
        cache = BlockHeaderCache(max_size=3)
        cache.set(_header(1, "0x01"), "ait-hub")
        cache.set(_header(2, "0x02"), "ait-hub")
        cache.set(_header(3, "0x03"), "ait-hub")
        assert cache.size == 3

        # Insert 4th — should evict height 1
        cache.set(_header(4, "0x04"), "ait-hub")
        assert cache.size == 3
        assert cache.get(1, "ait-hub") is None
        assert cache.get(2, "ait-hub") is not None
        assert cache.get(3, "ait-hub") is not None
        assert cache.get(4, "ait-hub") is not None

    def test_lru_access_moves_to_end(self) -> None:
        cache = BlockHeaderCache(max_size=3)
        cache.set(_header(1, "0x01"), "ait-hub")
        cache.set(_header(2, "0x02"), "ait-hub")
        cache.set(_header(3, "0x03"), "ait-hub")

        # Access height 1 — moves it to most-recently-used
        cache.get(1, "ait-hub")

        # Insert 4th — should evict height 2 (least recently used now)
        cache.set(_header(4, "0x04"), "ait-hub")
        assert cache.get(1, "ait-hub") is not None  # still present
        assert cache.get(2, "ait-hub") is None  # evicted
        assert cache.get(3, "ait-hub") is not None
        assert cache.get(4, "ait-hub") is not None

    def test_insert_100_headers_with_small_cache(self) -> None:
        cache = BlockHeaderCache(max_size=10)
        for i in range(100):
            cache.set(_header(i, f"0x{i:04x}"), "ait-hub")
        assert cache.size == 10
        # Only the last 10 should be present
        assert cache.get(89, "ait-hub") is None
        assert cache.get(90, "ait-hub") is not None
        assert cache.get(99, "ait-hub") is not None


class TestBlockHeaderCachePerChain:
    def test_per_chain_isolation(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set(_header(1, "0xAAA"), "ait-hub")
        cache.set(_header(1, "0xBBB"), "ait-island1")

        # Same height, different chains — both should be present
        hub_result = cache.get(1, "ait-hub")
        island_result = cache.get(1, "ait-island1")
        assert hub_result is not None
        assert island_result is not None
        assert hub_result["hash"] == "0xAAA"
        assert island_result["hash"] == "0xBBB"

    def test_per_chain_isolation_by_hash(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set(_header(1, "0xAAA"), "ait-hub")
        cache.set(_header(2, "0xAAA"), "ait-island1")

        # Same hash, different chains
        assert cache.get_by_hash("0xAAA", "ait-hub") is not None
        assert cache.get_by_hash("0xAAA", "ait-island1") is not None


class TestBlockHeaderCacheInvalidate:
    def test_invalidate_by_height(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set(_header(10, "0xAAA"), "ait-hub")
        assert cache.get(10, "ait-hub") is not None

        cache.invalidate("ait-hub", height=10)
        assert cache.get(10, "ait-hub") is None
        # Hash index should also be cleaned
        assert cache.get_by_hash("0xAAA", "ait-hub") is None

    def test_invalidate_by_hash(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set(_header(10, "0xAAA"), "ait-hub")
        assert cache.get_by_hash("0xAAA", "ait-hub") is not None

        cache.invalidate("ait-hub", hash="0xAAA")
        assert cache.get_by_hash("0xAAA", "ait-hub") is None
        # Height index should also be cleaned
        assert cache.get(10, "ait-hub") is None

    def test_clear(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set(_header(1, "0x01"), "ait-hub")
        cache.set(_header(2, "0x02"), "ait-hub")
        cache.clear()
        assert cache.size == 0
        assert cache.get(1, "ait-hub") is None


class TestBlockHeaderCacheEdgeCases:
    def test_set_missing_height_skipped(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set({"hash": "0xAAA"}, "ait-hub")
        assert cache.size == 0

    def test_set_missing_hash_skipped(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set({"height": 10}, "ait-hub")
        assert cache.size == 0

    def test_update_existing_header(self) -> None:
        cache = BlockHeaderCache(max_size=100)
        cache.set(_header(10, "0xAAA"), "ait-hub")
        cache.set(_header(10, "0xBBB"), "ait-hub")  # update same height
        assert cache.size == 1
        result = cache.get(10, "ait-hub")
        assert result is not None
        assert result["hash"] == "0xBBB"
        # Old hash should be gone
        assert cache.get_by_hash("0xAAA", "ait-hub") is None
        assert cache.get_by_hash("0xBBB", "ait-hub") is not None
