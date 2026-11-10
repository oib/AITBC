"""#1575: CacheManager expiry bookkeeping must use aware UTC datetimes."""

from __future__ import annotations

from datetime import UTC

import pytest

from coordinator_api.utils.cache import CacheManager


@pytest.mark.unit
def test_cache_entries_are_aware_utc():
    cache = CacheManager()
    cache.set("k", "v", ttl_seconds=60)
    entry = cache._cache["k"]
    assert entry["expires_at"].tzinfo is not None
    assert entry["expires_at"].utcoffset() == UTC.utcoffset(None)
    # get() compares against aware now — must not TypeError.
    assert cache.get("k") == "v"


@pytest.mark.unit
def test_cleanup_expired_uses_aware_now():
    cache = CacheManager()
    cache.set("k", "v", ttl_seconds=-1)
    removed = cache.cleanup_expired()
    assert removed == 1
    assert "k" not in cache._cache


@pytest.mark.unit
def test_memory_cap_evicts_on_value_payload_not_dict_shell():
    """#1689: a tiny dict shell holding a huge payload must trip the cap.

    The old sys.getsizeof(self._cache) measured only the dict shell, so a
    few large values never evicted. With real accounting, storing payloads
    whose combined estimate exceeds max_memory_mb evicts the oldest entry
    on the very next set — no 100-set sampling window.
    """
    cache = CacheManager(max_size=1000, max_memory_mb=1)
    big = "x" * (512 * 1024)  # ~0.5 MiB payload per entry
    cache.set("k1", big, ttl_seconds=300)
    cache.set("k2", big, ttl_seconds=300)
    # k1+k2 (~1 MiB) fit under 1 MiB? No — together they exceed it, so k1
    # was already evicted when k2 was set.
    assert cache.get("k1") is None
    assert cache.get("k2") == big
    # And the estimate tracks deletes.
    cache.delete("k2")
    assert cache._estimated_bytes == 0


@pytest.mark.unit
def test_expiry_paths_decrement_byte_estimate():
    """#1689: cleanup_expired and an expired get() must release the byte
    charge — otherwise the estimate only ever grows and the cap evicts
    live entries while dead weight keeps the counter pinned."""
    cache = CacheManager(max_size=1000, max_memory_mb=100)
    cache.set("a", "x" * 1000, ttl_seconds=-1)
    cache.set("b", "y" * 1000, ttl_seconds=-1)
    assert cache._estimated_bytes > 0
    assert cache.cleanup_expired() == 2
    assert cache._estimated_bytes == 0

    # An expired read takes the same _remove_entry path.
    cache.set("c", "z" * 1000, ttl_seconds=-1)
    assert cache.get("c") is None
    assert cache._estimated_bytes == 0


@pytest.mark.unit
def test_memory_cap_enforced_on_every_set():
    """#1689: enforcement is per-set, not sampled every 100 sets."""
    cache = CacheManager(max_size=1000, max_memory_mb=1)
    payload = "y" * (300 * 1024)
    for i in range(10):
        cache.set(f"k{i}", payload, ttl_seconds=300)
    # ~3 MiB of payloads against a 1 MiB cap: only the newest ~3 entries
    # can remain; the estimate must stay under ~cap + one entry.
    assert cache._estimated_bytes <= (1 * 1024 * 1024) + len(payload) + 4096
    assert len(cache._cache) < 10
