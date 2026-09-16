"""GAP-50: client-signed governance transactions.

The governance service held exactly one signing key
(``proposer_private_key``) and ``submit_governance_tx`` refuses any sender
that does not match it — so on-chain submission could only ever work for
one identity. The fix lets the caller's wallet sign: the service verifies
the signature recovers to the claimed actor and that the payload names this
specific action, then relays to ``/rpc/transaction``.

These tests pin the verification rules (signer binding, self-direction,
payload consistency) and the relay path — a mis-signed or re-attached tx
must fail before it reaches the chain.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from eth_keys import keys
from eth_utils import keccak

from governance_service.clients.blockchain import (
    _SIGNED_FIELDS,
    BlockchainClient,
    _canonical_signing_message,
)
from governance_service.services.governance_service import GovernanceService

PRIVKEY = "0x" + "11" * 32
OTHER_PRIVKEY = "0x" + "22" * 32


def _address(privkey: str) -> str:
    return keys.PrivateKey(bytes.fromhex(privkey.removeprefix("0x"))).public_key.to_checksum_address()


def _signed_tx(
    privkey: str,
    tx_type: str = "GOVERNANCE_PROPOSE",
    payload_overrides: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    address = _address(privkey)
    payload = {
        "to": address,
        "amount": 0,
        "type": tx_type,
        "proposal_id": "prop_test1",
        "proposer": address,
        "title": "t",
        "chain_id": "ait-hub",
    }
    payload.update(payload_overrides or {})
    tx: dict[str, Any] = {
        "from": address,
        "to": address,
        "amount": 0,
        "fee": 1,
        "nonce": 0,
        "payload": payload,
        "type": tx_type,
        "chain_id": "ait-hub",
    }
    tx.update(overrides)
    pk = keys.PrivateKey(bytes.fromhex(privkey.removeprefix("0x")))
    message = json.dumps({k: tx[k] for k in _SIGNED_FIELDS if k in tx}, sort_keys=True, separators=(",", ":")).encode()
    tx["signature"] = pk.sign_msg_hash(keccak(message)).to_bytes().hex()
    return tx


class _RecordingClient(BlockchainClient):
    """BlockchainClient with the HTTP layer stubbed — records what would relay."""

    def __init__(self) -> None:
        pass  # skip network/client init

    async def submit_transaction(self, tx_data: dict[str, Any]) -> dict[str, Any]:
        self.relayed = tx_data
        return {"transaction_hash": "0xdeadbeef", "block_height": 12345}


async def test_signed_tx_relays_when_signature_recovers_to_sender():
    client = _RecordingClient()
    tx = _signed_tx(PRIVKEY)
    result = await client.submit_signed_governance_tx(tx)
    assert result["transaction_hash"] == "0xdeadbeef"
    assert client.relayed is tx


async def test_signed_tx_rejects_signer_mismatch():
    """A tx signed by A but claiming from=B must fail before relay."""
    client = _RecordingClient()
    tx = _signed_tx(PRIVKEY)
    tx["from"] = _address(OTHER_PRIVKEY)  # claim a different sender — signature now stale
    with pytest.raises(ValueError, match="does not recover to 'from'"):
        await client.submit_signed_governance_tx(tx)


async def test_signed_tx_rejects_non_self_directed():
    client = _RecordingClient()
    tx = _signed_tx(PRIVKEY)
    tx["to"] = _address(OTHER_PRIVKEY)
    tx["signature"] = _signed_tx(PRIVKEY, to=_address(OTHER_PRIVKEY))["signature"]
    with pytest.raises(ValueError, match="self-directed"):
        await client.submit_signed_governance_tx(tx)


async def test_signed_tx_rejects_nonzero_amount():
    client = _RecordingClient()
    tx = _signed_tx(PRIVKEY, amount=5)
    with pytest.raises(ValueError, match="amount=0"):
        await client.submit_signed_governance_tx(tx)


async def test_signed_tx_rejects_missing_fields():
    client = _RecordingClient()
    tx = _signed_tx(PRIVKEY)
    del tx["nonce"]
    with pytest.raises(ValueError, match="missing fields"):
        await client.submit_signed_governance_tx(tx)


async def test_signed_tx_rejects_malformed_signature():
    client = _RecordingClient()
    tx = _signed_tx(PRIVKEY)
    tx["signature"] = "0xnotasignature"
    with pytest.raises(ValueError, match="malformed"):
        await client.submit_signed_governance_tx(tx)


class TestServiceLevelConsistency:
    """_verify_client_signed_tx binds the signed tx to *this* request — a
    signature made for a different proposal/vote cannot be re-attached."""

    def test_accepts_matching_tx(self):
        tx = _signed_tx(PRIVKEY)
        GovernanceService._verify_client_signed_tx(
            tx, "GOVERNANCE_PROPOSE", _address(PRIVKEY),
            {"proposal_id": "prop_test1", "proposer": _address(PRIVKEY)},
        )

    def test_rejects_wrong_type(self):
        tx = _signed_tx(PRIVKEY, tx_type="GOVERNANCE_VOTE")
        with pytest.raises(ValueError, match="GOVERNANCE_PROPOSE"):
            GovernanceService._verify_client_signed_tx(
                tx, "GOVERNANCE_PROPOSE", _address(PRIVKEY), {},
            )

    def test_rejects_wrong_signer_claim(self):
        tx = _signed_tx(PRIVKEY)
        with pytest.raises(ValueError, match="acting address"):
            GovernanceService._verify_client_signed_tx(
                tx, "GOVERNANCE_PROPOSE", _address(OTHER_PRIVKEY), {},
            )

    def test_rejects_reattached_proposal_id(self):
        """A tx signed for prop_A must not satisfy a request for prop_B."""
        tx = _signed_tx(PRIVKEY)
        with pytest.raises(ValueError, match="payload.proposal_id"):
            GovernanceService._verify_client_signed_tx(
                tx, "GOVERNANCE_PROPOSE", _address(PRIVKEY),
                {"proposal_id": "prop_other"},
            )
