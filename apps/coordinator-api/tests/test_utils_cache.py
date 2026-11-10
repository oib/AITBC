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
