"""#3073 AUDIT-DISPUTE-REPLAY-DOMAIN-1: dispute signatures bind the chain id.

``dispute_sign_data`` carried no domain separation — a captured signed
vote was a bearer credential on every node and island until freshness
expiry, and the nonce store is node-local so nothing stopped replay.
The signed dict now carries the *serving* node's resolved ``chain_id``:
a proof minted for chain A cannot verify on chain B's node, and the
pre-#3073 shape (no ``chain_id`` key) no longer verifies anywhere.
"""

from __future__ import annotations

import secrets
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from eth_keys import keys

import aitbc_chain.rpc.disputes as disputes
import aitbc_chain.rpc.utils as rpc_utils
import aitbc_chain.rpc.routers.disputes as disputes_router
from aitbc.blockchain.dispute_auth import dispute_sign_data, new_dispute_proof_fields
from aitbc_chain.chain_id import resolve_chain_id


def _keypair() -> tuple[str, str]:
    pk = keys.PrivateKey(secrets.token_bytes(32))
    return pk.public_key.to_checksum_address(), pk.to_hex()


ADDRESS, PRIVATE_KEY = _keypair()
FOREIGN_CHAIN = "bc-foreign-3073"
_LOCAL = object()


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(rpc_utils, "_nonce_db_path", lambda: tmp_path / "admin_nonces.db")
    app = FastAPI()
    app.include_router(disputes_router.router, prefix="/rpc")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def service_ok(monkeypatch):
    def _ok(**kwargs: Any) -> dict[str, Any]:
        return {"success": True, "dispute_id": 1, "evidence_id": 1, "vote_id": 0, "status": "Submitted", "message": "ok"}

    for name in ("file_dispute", "submit_evidence", "verify_evidence", "submit_arbitration_vote"):
        monkeypatch.setattr(disputes.dispute_resolution_service, name, _ok)


def _signed_body(
    action: str,
    payload: dict[str, Any],
    *,
    chain_id: Any = _LOCAL,
    legacy_shape: bool = False,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Build ``(headers, json_body)``; ``chain_id=None`` signs the pre-#3073 shape."""
    from aitbc.blockchain.dispute_auth import sign_transaction_data

    proof = new_dispute_proof_fields()
    fields: dict[str, Any] = {
        "action": action,
        "address": ADDRESS,
        "payload": payload,
        "issued_at": int(proof["issued_at"]),
        "nonce": str(proof["nonce"]),
    }
    if not legacy_shape:
        fields["chain_id"] = resolve_chain_id() if chain_id is _LOCAL else chain_id
    signature = sign_transaction_data(fields, PRIVATE_KEY)
    return {"X-Wallet-Address": ADDRESS}, {**payload, "signature": signature, **proof}


VOTE_PAYLOAD = {"dispute_id": 1, "vote": "plaintiff", "reasoning": "clear"}


def test_signature_for_foreign_chain_is_403(client, service_ok):
    """A proof minted for another chain's node must not verify here — the
    cross-island/cross-chain bearer-credential hole."""
    headers, body = _signed_body("rpc/disputes/vote", VOTE_PAYLOAD, chain_id=FOREIGN_CHAIN)
    resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
    assert resp.status_code == 403
    assert "signature" in resp.json()["detail"].lower()


def test_signature_with_null_chain_id_is_403(client, service_ok):
    headers, body = _signed_body("rpc/disputes/vote", VOTE_PAYLOAD, chain_id=None)
    resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
    assert resp.status_code == 403


def test_legacy_shape_without_chain_id_is_403(client, service_ok):
    """Pre-#3073 clients signed a dict with no ``chain_id`` key — that shape
    must not verify anymore (hard break, no legacy accept window)."""
    headers, body = _signed_body("rpc/disputes/vote", VOTE_PAYLOAD, legacy_shape=True)
    resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
    assert resp.status_code == 403


def test_correct_chain_signature_still_accepted(client, service_ok):
    headers, body = _signed_body("rpc/disputes/vote", VOTE_PAYLOAD)
    resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
    assert resp.status_code == 200


def test_dispute_sign_data_carries_chain_id():
    """The canonical dict both sides build must include the domain field."""
    data = dispute_sign_data(
        action="rpc/disputes/vote",
        address=ADDRESS,
        payload=VOTE_PAYLOAD,
        issued_at=1,
        nonce="n",
        chain_id="bc-x",
    )
    assert data["chain_id"] == "bc-x"
