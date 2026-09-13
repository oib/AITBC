"""Regression tests for trading Redis URL resolution.

The fleet ships a credentialed ``REDIS_URL`` in ``blockchain-secrets.env``, but
``gossip_broadcast_url`` and ``lease_tracker_redis_url`` defaulted to a bare
``redis://localhost:6379`` and only accepted ``TRADING_``-prefixed overrides, so
the authenticated Redis was unreachable and every restart fell back to memory.
"""

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for var in ("REDIS_URL", "TRADING_GOSSIP_BROADCAST_URL", "TRADING_LEASE_TRACKER_REDIS_URL"):
        monkeypatch.delenv(var, raising=False)


def test_redis_url_env_is_the_fallback(monkeypatch: pytest.MonkeyPatch):
    from trading_service.config import Settings

    monkeypatch.setenv("REDIS_URL", "redis://:secret@127.0.0.1:6379/0")
    settings = Settings()
    assert settings.gossip_broadcast_url == "redis://:secret@127.0.0.1:6379/0"
    assert settings.lease_tracker_redis_url == "redis://:secret@127.0.0.1:6379/0"


def test_explicit_trading_vars_win_over_redis_url(monkeypatch: pytest.MonkeyPatch):
    from trading_service.config import Settings

    monkeypatch.setenv("REDIS_URL", "redis://:secret@127.0.0.1:6379/0")
    monkeypatch.setenv("TRADING_GOSSIP_BROADCAST_URL", "redis://other:6390")
    settings = Settings()
    assert settings.gossip_broadcast_url == "redis://other:6390"
    assert settings.lease_tracker_redis_url == "redis://:secret@127.0.0.1:6379/0"


def test_defaults_to_bare_localhost_without_env():
    from trading_service.config import Settings

    settings = Settings()
    assert settings.gossip_broadcast_url == "redis://localhost:6379"
    assert settings.lease_tracker_redis_url == "redis://localhost:6379"
