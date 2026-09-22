"""Regression tests for ``RedisCache`` URL resolution and warn-once.

A caller passing ``redis_url=None`` used to fall straight to the
uncredentialed ``redis://localhost:6379/0`` default even when the service
environment carried a real ``REDIS_URL`` — on hosts where Redis requires
auth that meant a silent in-memory fallback plus a warning every time the
cache was re-instantiated (``aitbc-trading`` logged it every 60s).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import aitbc.caching.redis_cache as redis_cache_module
from aitbc.caching.redis_cache import RedisCache


@pytest.fixture(autouse=True)
def _fresh_warn_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(redis_cache_module, "_warned_urls", set())
    monkeypatch.delenv("REDIS_URL", raising=False)


def _fake_redis_client():
    client = MagicMock()
    client.ping.return_value = True
    return client


def test_env_redis_url_used_when_caller_passes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://:secret@127.0.0.1:6379/5")
    with patch("redis.from_url", return_value=_fake_redis_client()) as from_url:
        cache = RedisCache()
    from_url.assert_called_once_with("redis://:secret@127.0.0.1:6379/5")
    assert cache.is_available()


def test_explicit_url_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://:secret@127.0.0.1:6379/5")
    with patch("redis.from_url", return_value=_fake_redis_client()) as from_url:
        RedisCache(redis_url="redis://example:6380/2")
    from_url.assert_called_once_with("redis://example:6380/2")


def test_localhost_default_when_nothing_configured() -> None:
    with patch("redis.from_url", return_value=_fake_redis_client()) as from_url:
        RedisCache()
    from_url.assert_called_once_with("redis://localhost:6379/0")


def test_fallback_warning_fires_once_per_url() -> None:
    with patch("redis.from_url", side_effect=ConnectionError("no route")):
        RedisCache()
        RedisCache()
        RedisCache(redis_url="redis://localhost:6379/0")  # same resolved URL: still once
        RedisCache(redis_url="redis://elsewhere:6379/0")  # different URL: second warning
    # two distinct URLs -> two warnings total
    assert len(redis_cache_module._warned_urls) == 2


def test_in_memory_fallback_still_works() -> None:
    with patch("redis.from_url", side_effect=ConnectionError("no route")):
        cache = RedisCache()
    assert not cache.is_available()
    assert cache.set("k", {"v": 1}) is True
    assert cache.get("k") == {"v": 1}
    assert cache.delete("k") is True
