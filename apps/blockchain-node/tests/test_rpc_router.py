from __future__ import annotations

import pytest

from aitbc_chain.rpc.router import TransactionRequest


def test_transfer_payload_accepts_legacy_to_field() -> None:
    req = TransactionRequest.model_validate(
        {
            "type": "transfer",
            "sender": "aitbc1sender",
            "nonce": 1,
            "fee": 0,
            "payload": {"to": "aitbc1recipient", "value": "100"},
        }
    )

    assert req.type == "TRANSFER"
    assert req.payload["recipient"] == "aitbc1recipient"
    assert req.payload["to"] == "aitbc1recipient"
    assert req.payload["amount"] == "100"
    assert req.payload["value"] == "100"


def test_transfer_payload_requires_recipient_or_to() -> None:
    with pytest.raises(ValueError, match="recipient"):
        TransactionRequest.model_validate(
            {
                "type": "TRANSFER",
                "sender": "aitbc1sender",
                "nonce": 1,
                "fee": 0,
                "payload": {"amount": "100"},
            }
        )
