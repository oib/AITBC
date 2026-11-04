"""#1079 pin: wallet_auth_headers refuses an empty key under AITBC_ENV=production
but still returns headers (possibly empty) in non-production."""

from __future__ import annotations

import pytest

from apps.exchange.simple_exchange.handlers import wallet as wallet_handler


def test_empty_key_raises_in_production(monkeypatch):
    monkeypatch.delenv("WALLET_API_KEY", raising=False)
    monkeypatch.delenv("COORDINATOR_API_KEY", raising=False)
    monkeypatch.setenv("AITBC_ENV", "production")
    with pytest.raises(RuntimeError):
        wallet_handler.wallet_auth_headers()


def test_empty_key_ok_outside_production(monkeypatch):
    monkeypatch.delenv("WALLET_API_KEY", raising=False)
    monkeypatch.delenv("COORDINATOR_API_KEY", raising=False)
    monkeypatch.delenv("AITBC_ENV", raising=False)
    assert wallet_handler.wallet_auth_headers() == {}
    monkeypatch.setenv("AITBC_ENV", "dev")
    assert wallet_handler.wallet_auth_headers() == {}


def test_configured_key_returned(monkeypatch):
    monkeypatch.setenv("WALLET_API_KEY", "k123")
    monkeypatch.delenv("AITBC_ENV", raising=False)
    assert wallet_handler.wallet_auth_headers() == {"X-API-Key": "k123"}
