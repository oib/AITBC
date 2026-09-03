"""The ``software_job`` proof-of-work record must satisfy the endpoint that receives it.

``/rpc/transactions/marketplace`` exempts only the ``offer`` and ``software_offer``
actions from signature checking (V23-90, so listing works without wallet keys). Every
other action is rejected with ``403 Signature required``. The three job commands in
``market/jobs.py`` built a ``software_job`` transaction with no signature field, caught
the rejection, warned, and released the escrow anyway -- so the on-chain proof of work
never existed, and nothing failed loudly enough to say so.

As with the exchange signer, these assert against the server's real verifier rather than
a copy of the format: canonical JSON is easy to almost match, and a different key order
or separator yields a different keccak hash and a 403 that names neither side.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from eth_account import Account
from fastapi import HTTPException

from aitbc.crypto.crypto import sign_transaction_data
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS
from aitbc_chain.rpc.transactions import submit_marketplace_transaction
from aitbc_cli.commands.market import jobs
from aitbc_chain.rpc.utils import verify_transaction_signature

CHAIN_ID = "ait-hub.aitbc.bubuit.net"
ZERO = "0x0000000000000000000000000000000000000000"


def _job_tx(sender: str, action: str = "software_job") -> dict[str, Any]:
    """The shape market/jobs.py builds after a job completes."""
    return {
        "from": sender,
        "to": ZERO,
        "amount": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 7,
        "type": "GPU_MARKETPLACE",
        "chain_id": CHAIN_ID,
        "payload": {
            "action": action,
            "job_id": "job-1",
            "offer_id": "offer-1",
            "buyer_address": sender,
            "provider_address": sender,
            "result_hash": "0xabc",
            "actual_duration_minutes": 1.25,
            "actual_cost": "0.001",
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
        },
    }


def test_the_server_accepts_what_the_job_commands_sign() -> None:
    signer = Account.create()
    tx = _job_tx(signer.address)
    tx["signature"] = sign_transaction_data(tx, signer.key.hex())

    assert verify_transaction_signature(tx, tx["signature"], signer.address) is True


def test_tampering_with_the_cost_invalidates_the_signature() -> None:
    """The signature must cover the payload, not just the envelope."""
    signer = Account.create()
    tx = _job_tx(signer.address)
    tx["signature"] = sign_transaction_data(tx, signer.key.hex())
    tx["payload"]["actual_cost"] = "999.0"

    assert verify_transaction_signature(tx, tx["signature"], signer.address) is False


async def test_an_unsigned_job_record_is_refused_as_403_not_400() -> None:
    """The refusal must keep its own status code.

    Both raises live inside a ``try`` whose ``except Exception`` reissued everything as
    400. HTTPException is an Exception, so a caller could not tell "you did not sign
    this" from "this transaction is malformed" -- which is why the failure was recorded
    as a 400 for as long as it was.
    """
    with pytest.raises(HTTPException) as excinfo:
        await submit_marketplace_transaction(None, _job_tx(Account.create().address))

    assert excinfo.value.status_code == 403
    assert "Signature required" in str(excinfo.value.detail)


async def test_an_offer_is_still_exempt_from_signing() -> None:
    """V23-90's exemption must survive: listing works without wallet private keys.

    A missing sender is the next check after the exemption, so reaching *that* refusal
    proves the signature gate was skipped rather than passed.
    """
    tx = _job_tx(Account.create().address, action="software_offer")
    tx.pop("from")

    with pytest.raises(HTTPException) as excinfo:
        await submit_marketplace_transaction(None, tx)

    assert excinfo.value.status_code == 400
    assert "Sender required" in str(excinfo.value.detail)


class _Captor:
    """Stands in for AITBCHTTPClient and keeps whatever was posted."""

    sent: dict[str, Any] | None = None

    def __init__(self, base_url: str, timeout: int) -> None:
        self.base_url = base_url

    def post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        _Captor.sent = json
        return {"transaction_hash": "0xfeed"}


class _Config:
    hub_discovery_url = "hub.aitbc.bubuit.net"


def test_the_job_record_is_signed_before_it_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The call site must sign, not merely have a signer available to it.

    Asserting the helper's output against the real verifier is what the other tests do;
    this one asserts that the code path which posts the record is the one that signs it.
    That is the part that was broken -- the signer already existed.
    """
    signer = Account.create()
    _Captor.sent = None
    monkeypatch.setattr(jobs, "AITBCHTTPClient", _Captor)

    tx_hash = jobs._record_job_on_chain(_Config(), _job_tx(signer.address), signer.key.hex())

    assert tx_hash == "0xfeed"
    assert _Captor.sent is not None
    signature = _Captor.sent.get("signature")
    assert signature, "the record was posted without a signature"
    assert verify_transaction_signature(_Captor.sent, signature, signer.address) is True


def test_a_refused_record_does_not_abort_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    """The buyer has already paid by this point, so the escrow release must still happen."""

    class _Refuses(_Captor):
        def post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("403 Signature required")

    signer = Account.create()
    monkeypatch.setattr(jobs, "AITBCHTTPClient", _Refuses)

    assert jobs._record_job_on_chain(_Config(), _job_tx(signer.address), signer.key.hex()) is None
