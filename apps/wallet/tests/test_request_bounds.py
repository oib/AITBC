"""Bounds on admin request models (#1746 WALLET-DEEP2-1).

Unbounded password/message/metadata fields fed argon2, keccak and sqlite
writes — these pin the pydantic max_length / serialized-size limits.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wallet_app.models import (
    WalletCreateRequest,
    WalletSignRequest,
    WalletTransactionRequest,
    WalletUnlockRequest,
)

PASSWORD = "correct-horse-battery-staple!"


def test_create_request_accepts_normal_input() -> None:
    req = WalletCreateRequest(
        chain_id="aitbc",
        wallet_id="w1",
        password=PASSWORD,
        metadata={"address": "0x" + "ab" * 20},
        secret_key="a" * 44,
    )
    assert req.wallet_id == "w1"


def test_create_request_rejects_oversized_fields() -> None:
    base = {"chain_id": "aitbc", "wallet_id": "w1", "password": PASSWORD}
    with pytest.raises(ValidationError):
        WalletCreateRequest(chain_id="aitbc", wallet_id="w1", password="x" * 5000)
    with pytest.raises(ValidationError):
        WalletCreateRequest(**base, secret_key="a" * 100_000)
    with pytest.raises(ValidationError):
        WalletCreateRequest(**base, metadata={f"k{i}": "v" * 500 for i in range(64)})
    with pytest.raises(ValidationError):
        WalletCreateRequest(chain_id="aitbc", wallet_id="w" * 1000, password=PASSWORD)


def test_unlock_and_sign_password_bounded() -> None:
    with pytest.raises(ValidationError):
        WalletUnlockRequest(password="p" * 5000)
    with pytest.raises(ValidationError):
        WalletSignRequest(password="p" * 5000, message_base64="aGk=")
    # ~64 KiB decoded cap on the base64 string
    with pytest.raises(ValidationError):
        WalletSignRequest(password=PASSWORD, message_base64="A" * 200_000)


def test_transaction_request_bounds() -> None:
    base = {"password": PASSWORD, "recipient": "0x" + "ab" * 20, "amount": 1}
    WalletTransactionRequest(**base)  # ok
    with pytest.raises(ValidationError):
        WalletTransactionRequest(**{**base, "password": "p" * 5000})
    with pytest.raises(ValidationError):
        WalletTransactionRequest(**{**base, "recipient": "0x" + "ab" * 500})
    with pytest.raises(ValidationError):
        WalletTransactionRequest(**{**base, "payload": {"blob": "x" * 100_000}})
