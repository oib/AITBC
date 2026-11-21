"""#2371: ``_create_escrow_payment`` must forward ``market_job_id`` to the
coordinator.

The buyer signs ``market_job_id`` into the ESCROW_LOCK payload, but the
coordinator only sees ``buyer_lock_signature``/``nonce``/``fee`` — without
the field in the ``/v1/payments`` body it rebuilds a different canonical tx
and the chain refuses the signature (``403 Invalid transaction signature``,
the live regression found by the S90 play).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import aitbc_cli.commands.ai as _ai

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
NODE_WALLET = "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01"


class _FakeCoordClient:
    def __init__(self):
        self.posts: list[dict] = []

    def post(self, path, json=None, **kwargs):
        self.posts.append({"path": path, "json": json})
        return {"payment_id": "pay-1"}


@pytest.mark.unit
def test_create_escrow_payment_sends_market_job_id():
    client = _FakeCoordClient()
    lock_tx = {"from": BUYER, "payload": {"provider": PROVIDER}, "nonce": 3, "fee": 36}
    with patch(
        "aitbc_cli.commands.ai.create_signed_escrow_lock",
        return_value=(lock_tx, "0xsig"),
    ):
        _ai._create_escrow_payment(
            None,
            client,
            "http://127.0.0.1:8202",
            "coord-job-1",
            "0.1",
            "AITBC",
            BUYER,
            PROVIDER,
            "0x" + "01" * 32,
            NODE_WALLET,
            "bc-2",
            None,
            None,
            market_job_id="ai_job_0123456789abcdef",
        )
    assert client.posts[0]["path"] == "/v1/payments"
    assert client.posts[0]["json"]["market_job_id"] == "ai_job_0123456789abcdef"


@pytest.mark.unit
def test_create_escrow_payment_omits_market_job_id_when_absent():
    client = _FakeCoordClient()
    lock_tx = {"from": BUYER, "payload": {"provider": PROVIDER}, "nonce": 3, "fee": 36}
    with patch(
        "aitbc_cli.commands.ai.create_signed_escrow_lock",
        return_value=(lock_tx, "0xsig"),
    ):
        _ai._create_escrow_payment(
            None,
            client,
            "http://127.0.0.1:8202",
            "coord-job-1",
            "0.1",
            "AITBC",
            BUYER,
            PROVIDER,
            "0x" + "01" * 32,
            NODE_WALLET,
            "bc-2",
            None,
            None,
        )
    assert "market_job_id" not in client.posts[0]["json"]
