"""Unit tests for the theme preference Redis cache (v0.17.0 §B3)."""

from __future__ import annotations

import pytest

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


def test_cache_with_redis(monkeypatch) -> None:
    try:
        import fakeredis
    except ImportError:  # pragma: no cover
        pytest.skip("fakeredis not installed")

    server = fakeredis.FakeServer()
    fake = fakeredis.FakeStrictRedis(server=server, decode_responses=True)

    cache = ThemePreferenceCache(redis_url="redis://fake", ttl_seconds=60)
    monkeypatch.setattr(cache, "_client", fake)
    cache.set("0xdef", {"mode": "system"})
    assert cache.get("0xdef") == {"mode": "system"}
    cache.delete("0xdef")
    assert cache.get("0xdef") is None
