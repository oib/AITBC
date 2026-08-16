"""Tests for the publishable ``aitbc-sdk`` client (v0.16.2 §A1)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from aitbc_sdk import AITBCClient, AITBCConnectionError, AITBCRateLimitError, with_backoff


@pytest.fixture()
def client() -> AITBCClient:
    return AITBCClient("http://localhost:8000", api_key="test-key")


def test_aitbc_client_exposes_subclients(client: AITBCClient) -> None:
    assert client.wallet is not None
    assert client.registry is not None


def test_wallet_get_balance(client: AITBCClient) -> None:
    client.wallet._http = MagicMock(
        get=MagicMock(
            return_value={
                "wallet_id": "w-1",
                "address": "0xabc",
                "balance": "123.45",
                "asset": "AITBC",
            }
        )
    )
    balance = client.wallet.get_balance("w-1")
    assert balance.wallet_id == "w-1"
    assert balance.address == "0xabc"
    assert balance.balance == Decimal("123.45")
    assert balance.asset == "AITBC"


def test_registry_get_developer(client: AITBCClient) -> None:
    client.registry._http = MagicMock(
        get=MagicMock(
            return_value={
                "id": "dev-1",
                "name": "Ada",
                "wallet_address": "0xabc",
                "metadata": {"role": "builder"},
            }
        )
    )
    entry = client.registry.get_developer("0xabc")
    assert entry.id == "dev-1"
    assert entry.name == "Ada"
    assert entry.metadata == {"role": "builder"}


def test_registry_list_grants(client: AITBCClient) -> None:
    client.registry._http = MagicMock(
        get=MagicMock(
            return_value={
                "items": [
                    {
                        "grant_id": "g-1",
                        "title": "Compute Infra",
                        "status": "open",
                        "requested_amount": "1000.00",
                        "approved_amount": "0",
                    }
                ]
            }
        )
    )
    grants = client.registry.list_grants()
    assert len(grants) == 1
    assert grants[0].grant_id == "g-1"
    assert grants[0].requested_amount == Decimal("1000.00")


def test_wallet_get_balance_propagates_errors(client: AITBCClient) -> None:
    from aitbc.exceptions import NetworkError

    client.wallet._http = MagicMock(get=MagicMock(side_effect=NetworkError("boom")))
    with pytest.raises(AITBCConnectionError):
        client.wallet.get_balance("w-1")


def test_wallet_get_balance_propagates_rate_limit(client: AITBCClient) -> None:
    from aitbc.exceptions import RateLimitError

    client.wallet._http = MagicMock(get=MagicMock(side_effect=RateLimitError("slow")))
    with pytest.raises(AITBCRateLimitError):
        client.wallet.get_balance("w-1")


def test_with_backoff_succeeds() -> None:
    counter = {"n": 0}

    def fn() -> int:
        counter["n"] += 1
        if counter["n"] < 3:
            raise RuntimeError("not yet")
        return 42

    assert with_backoff(fn, max_retries=3, backoff_seconds=0.0) == 42


def test_with_backoff_gives_up() -> None:
    with pytest.raises(RuntimeError):
        with_backoff(lambda: (_ for _ in ()).throw(RuntimeError("fail")), max_retries=1, backoff_seconds=0.0)
