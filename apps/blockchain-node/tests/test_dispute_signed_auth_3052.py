"""AUDIT-DISPUTE-AUTH-HEADER-1 (#3052): dispute mutations need a wallet signature.

``POST /rpc/disputes/{file,evidence,verify-evidence,vote}`` authenticated on a
bare ``X-Wallet-Address`` header trusted verbatim under
``TRUST_X_WALLET_ADDRESS=true`` — any caller could name a real arbitrator and
cast/revise votes that steer escrowed funds. The routes now require a
secp256k1 signature over ``aitbc.blockchain.dispute_auth.dispute_sign_data``
binding the claimed address, the route action, the posted payload, a fresh
``issued_at`` and a single-use ``nonce``. These tests pin the reject and
accept sides of that contract at the HTTP layer.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from eth_keys import keys

import aitbc_chain.rpc.disputes as disputes
import aitbc_chain.rpc.utils as rpc_utils
import aitbc_chain.rpc.routers.disputes as disputes_router
from aitbc.blockchain.dispute_auth import new_dispute_proof_fields, sign_dispute_request

from aitbc_chain.chain_id import resolve_chain_id


def _keypair() -> tuple[str, str]:
    """Return ``(checksummed_address, raw_private_key_hex)``."""
    pk = keys.PrivateKey(secrets.token_bytes(32))
    return pk.public_key.to_checksum_address(), pk.to_hex()


ADDRESS, PRIVATE_KEY = _keypair()
OTHER_ADDRESS, OTHER_KEY = _keypair()


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Disputes router behind /rpc with an isolated nonce store."""
    monkeypatch.setattr(rpc_utils, "_nonce_db_path", lambda: tmp_path / "admin_nonces.db")
    app = FastAPI()
    app.include_router(disputes_router.router, prefix="/rpc")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def service_ok(monkeypatch):
    """Stub the contract service so a passing auth check returns success."""

    def _ok(**kwargs: Any) -> dict[str, Any]:
        return {"success": True, "dispute_id": 1, "evidence_id": 1, "vote_id": 0, "status": "Submitted", "message": "ok"}

    for name in ("file_dispute", "submit_evidence", "verify_evidence", "submit_arbitration_vote"):
        monkeypatch.setattr(disputes.dispute_resolution_service, name, _ok)


def _signed_headers_and_body(
    action: str,
    payload: dict[str, Any],
    *,
    address: str = ADDRESS,
    private_key: str = PRIVATE_KEY,
    sign_payload: dict[str, Any] | None = None,
    **proof_overrides: Any,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Build ``(headers, json_body)`` for one signed dispute mutation."""
    proof = new_dispute_proof_fields()
    proof.update(proof_overrides)
    body = {
        **payload,
        "signature": sign_dispute_request(
            private_key,
            action=action,
            address=address,
            payload=payload if sign_payload is None else sign_payload,
            issued_at=int(proof["issued_at"]),
            nonce=str(proof["nonce"]),
            chain_id=resolve_chain_id(),
        ),
        **proof,
    }
    return {"X-Wallet-Address": address}, body


FILE_PAYLOAD = {
    "agreement_id": 1,
    "respondent": "0x" + "bb" * 20,
    "dispute_type": "Payment",
    "reason": "test",
    "evidence_hash": "0x" + "00" * 32,
}
EVIDENCE_PAYLOAD = {
    "dispute_id": 1,
    "evidence_hash": "0x" + "11" * 32,
    "evidence_type": "receipt",
    "description": "proof",
}
VERIFY_PAYLOAD = {"dispute_id": 1, "evidence_id": 1, "verified": True}
VOTE_PAYLOAD = {"dispute_id": 1, "vote": "plaintiff", "reasoning": "clear"}

ROUTES = [
    ("/rpc/disputes/file", "rpc/disputes/file", FILE_PAYLOAD),
    ("/rpc/disputes/evidence", "rpc/disputes/evidence", EVIDENCE_PAYLOAD),
    ("/rpc/disputes/verify-evidence", "rpc/disputes/verify-evidence", VERIFY_PAYLOAD),
    ("/rpc/disputes/vote", "rpc/disputes/vote", VOTE_PAYLOAD),
]


class TestBareHeaderRejected:
    """The old credential — header alone, even with the trust flag on — is dead."""

    @pytest.mark.parametrize("path,_,payload", ROUTES)
    def test_header_without_signature_is_401(self, client, monkeypatch, path, _, payload):
        monkeypatch.setenv("TRUST_X_WALLET_ADDRESS", "true")
        resp = client.post(path, json=payload, headers={"X-Wallet-Address": ADDRESS})
        assert resp.status_code == 401
        assert "signature" in resp.json()["detail"].lower()

    @pytest.mark.parametrize("path,_,payload", ROUTES)
    def test_no_credentials_is_401(self, client, path, _, payload):
        resp = client.post(path, json=payload)
        assert resp.status_code == 401
        assert "Authentication required" in resp.json()["detail"]

    @pytest.mark.parametrize("path,_,payload", ROUTES)
    def test_malformed_address_is_401(self, client, path, _, payload):
        resp = client.post(path, json=payload, headers={"X-Wallet-Address": "not-an-address"})
        assert resp.status_code == 401
        assert "Invalid wallet address format" in resp.json()["detail"]


class TestSignedRequestAccepted:
    @pytest.mark.parametrize("path,action,payload", ROUTES)
    def test_valid_signature_reaches_service(self, client, service_ok, path, action, payload):
        headers, body = _signed_headers_and_body(action, payload)
        resp = client.post(path, json=body, headers=headers)
        assert resp.status_code == 200, resp.text

    def test_signature_from_wrong_key_is_403(self, client, service_ok):
        headers, body = _signed_headers_and_body("rpc/disputes/vote", VOTE_PAYLOAD, address=ADDRESS, private_key=OTHER_KEY)
        resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
        assert resp.status_code == 403
        assert "signature" in resp.json()["detail"].lower()

    def test_signature_for_other_address_is_403(self, client, service_ok):
        # Signed by OTHER_KEY but claiming ADDRESS — recovery must match the claim.
        headers, body = _signed_headers_and_body(
            "rpc/disputes/vote",
            VOTE_PAYLOAD,
            address=ADDRESS,
            private_key=OTHER_KEY,
            sign_payload=VOTE_PAYLOAD,
        )
        # sign_dispute_request used OTHER_KEY over address=ADDRESS: recovery yields
        # OTHER_ADDRESS != claimed ADDRESS.
        resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
        assert resp.status_code == 403

    def test_payload_tampering_breaks_signature(self, client, service_ok):
        headers, body = _signed_headers_and_body("rpc/disputes/vote", VOTE_PAYLOAD)
        body["reasoning"] = "tampered after signing"
        resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
        assert resp.status_code == 403

    def test_action_binding_blocks_cross_route_replay(self, client, service_ok):
        # A proof minted for /file must not verify on /vote.
        headers, body = _signed_headers_and_body("rpc/disputes/file", FILE_PAYLOAD)
        resp = client.post(
            "/rpc/disputes/vote",
            json={**VOTE_PAYLOAD, **{k: body[k] for k in ("signature", "issued_at", "nonce")}},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_nonce_replay_is_rejected(self, client, service_ok):
        headers, body = _signed_headers_and_body("rpc/disputes/vote", VOTE_PAYLOAD)
        assert client.post("/rpc/disputes/vote", json=body, headers=headers).status_code == 200
        resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
        assert resp.status_code == 403
        assert "nonce" in resp.json()["detail"].lower()

    def test_stale_issued_at_is_rejected(self, client, service_ok):
        headers, body = _signed_headers_and_body("rpc/disputes/vote", VOTE_PAYLOAD, issued_at=int(time.time()) - 3600)
        resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
        assert resp.status_code == 403

    def test_missing_proof_fields_are_rejected(self, client, service_ok):
        resp = client.post(
            "/rpc/disputes/vote",
            json=VOTE_PAYLOAD,
            headers={"X-Wallet-Address": ADDRESS},
        )
        assert resp.status_code == 401


class TestDownstreamChecksStillApply:
    def test_non_arbitrator_still_403(self, client, monkeypatch):
        def _deny(**kwargs: Any) -> dict[str, Any]:
            return {"success": False, "error": "not an authorized arbitrator for this dispute"}

        monkeypatch.setattr(disputes.dispute_resolution_service, "submit_arbitration_vote", _deny)
        headers, body = _signed_headers_and_body("rpc/disputes/vote", VOTE_PAYLOAD)
        resp = client.post("/rpc/disputes/vote", json=body, headers=headers)
        assert resp.status_code == 403

    def test_zero_address_claim_cannot_authenticate(self, client):
        # No private key exists for the zero address, so no valid signature
        # can ever be produced for it — the claim dies at signature verify.
        payload = {"signature": "0x" + "00" * 65, "issued_at": int(time.time()), "nonce": secrets.token_hex(16)}
        resp = client.post(
            "/rpc/disputes/vote",
            json={**VOTE_PAYLOAD, **payload},
            headers={"X-Wallet-Address": "0x0000000000000000000000000000000000000000"},
        )
        assert resp.status_code == 403
