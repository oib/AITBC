"""Unit tests for the theme preference Redis cache (v0.17.0 §B3)."""

from __future__ import annotations


from coordinator_api.contexts.preferences.redis_cache import ThemePreferenceCache


def test_cache_stores_and_retrieves_preference() -> None:
    cache = ThemePreferenceCache(redis_url=None, ttl_seconds=60)
    pref = {"mode": "dark", "reduced_motion": True, "high_contrast": False}
    cache.set("0xabc", pref)
    assert cache.get("0xabc") == pref


def test_cache_delete_removes_preference() -> None:
    cache = ThemePreferenceCache(redis_url=None, ttl_seconds=60)
    cache.set("0xabc", {"mode": "light"})
    cache.delete("0xabc")
    assert cache.get("0xabc") is None


def test_cache_normalizes_wallet_address_case() -> None:
    cache = ThemePreferenceCache(redis_url=None, ttl_seconds=60)
    cache.set("0xABC", {"mode": "high-contrast"})
    assert cache.get("0xabc") == {"mode": "high-contrast"}
