"""Tests for WalletClient request shaping.

These pin the path and body that send_payment puts on the wire. It previously posted to
/v1/wallets/{wallet_id}/payments -- a path no service in this repo has ever served -- with
a body no endpoint accepts, and nothing caught it because WalletClient had no tests.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from aitbc_sdk.client import WalletClient


class _RecordingHTTP:
    """Stands in for AITBCHTTPClient, capturing what the client would send."""

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {}
        self.calls: list[dict[str, Any]] = []

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append({"method": "GET", "path": path, "params": params})
        return self.response

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"method": "POST", "path": path, "json": json, "params": params})
        return self.response


@pytest.fixture()
def http() -> _RecordingHTTP:
    return _RecordingHTTP({"success": True, "tx_hash": "0xdeadbeef", "status": "submitted"})


def test_send_payment_targets_the_daemon_send_route(http: _RecordingHTTP) -> None:
    WalletClient(http).send_payment(  # type: ignore[arg-type]
        wallet_id="wallet-123",
        recipient="wallet-456",
        amount=1000,
        password="hunter2",
    )

    call = http.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/v1/wallets/wallet-123/send"
    # The route that never existed.
    assert call["path"] != "/v1/wallets/wallet-123/payments"


def test_send_payment_body_matches_wallet_transaction_request(http: _RecordingHTTP) -> None:
    WalletClient(http).send_payment(  # type: ignore[arg-type]
        wallet_id="wallet-123",
        recipient="wallet-456",
        amount=1000,
        password="hunter2",
    )

    body = http.calls[0]["json"]
    assert body == {"password": "hunter2", "recipient": "wallet-456", "amount": 1000, "fee": 36}
    # The daemon's model has no such fields; sending them was the old bug.
    assert "recipient_id" not in body
    assert "asset" not in body


def test_send_payment_omits_unset_optionals(http: _RecordingHTTP) -> None:
    WalletClient(http).send_payment(  # type: ignore[arg-type]
        wallet_id="w", recipient="r", amount=1, password="p"
    )

    body = http.calls[0]["json"]
    for key in ("nonce", "chain_id", "payload"):
        assert key not in body, f"{key} should be omitted so the daemon applies its default"


def test_send_payment_forwards_optionals_when_given(http: _RecordingHTTP) -> None:
    WalletClient(http).send_payment(  # type: ignore[arg-type]
        wallet_id="w",
        recipient="r",
        amount=250,
        password="p",
        fee=99,
        nonce=7,
        chain_id="ait-mainnet",
        payload={"memo": "rent"},
    )

    assert http.calls[0]["json"] == {
        "password": "p",
        "recipient": "r",
        "amount": 250,
        "fee": 99,
        "nonce": 7,
        "chain_id": "ait-mainnet",
        "payload": {"memo": "rent"},
    }


def test_send_payment_keeps_nonce_zero(http: _RecordingHTTP) -> None:
    """nonce=0 is a real nonce; an `if nonce:` guard would silently drop it."""
    WalletClient(http).send_payment(  # type: ignore[arg-type]
        wallet_id="w", recipient="r", amount=1, password="p", nonce=0
    )

    assert http.calls[0]["json"]["nonce"] == 0


def test_send_payment_returns_the_response(http: _RecordingHTTP) -> None:
    result = WalletClient(http).send_payment(  # type: ignore[arg-type]
        wallet_id="w", recipient="r", amount=1, password="p"
    )

    assert result["tx_hash"] == "0xdeadbeef"


def test_get_balance_path_and_parsing() -> None:
    http = _RecordingHTTP({"wallet_id": "wallet-123", "address": "ait1abc", "balance": "10.5", "asset": "AITBC"})

    balance = WalletClient(http).get_balance("wallet-123")  # type: ignore[arg-type]

    assert http.calls[0]["path"] == "/v1/wallets/wallet-123/balance"
    assert balance.wallet_id == "wallet-123"
    assert balance.address == "ait1abc"
    assert balance.balance == Decimal("10.5")
    assert balance.asset == "AITBC"


def test_get_balance_tolerates_daemon_response_without_asset() -> None:
    """The daemon returns balance_ait/chain_id and no asset field."""
    http = _RecordingHTTP(
        {
            "wallet_id": "wallet-123",
            "address": "ait1abc",
            "balance": 42,
            "balance_ait": "0.00000042",
            "chain_id": "ait-mainnet",
        }
    )

    balance = WalletClient(http).get_balance("wallet-123")  # type: ignore[arg-type]

    assert balance.balance == Decimal("42")
    assert balance.asset == ""
