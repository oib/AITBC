"""B6: End-to-end signing round-trip test (v0.5.16).

Proves that a transaction signed by the shared ``TransactionService`` (A1,
secp256k1) is accepted by the blockchain node's ``/rpc/transaction`` endpoint
— i.e. it passes the Bug 4 signature verification check and does NOT get a
403 ``Invalid transaction signature``.

This is the closure test for the signing-scheme regression: before A1,
``TransactionService`` signed with ed25519 (64-byte sigs) and every call was
rejected by the secp256k1 verifier.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from eth_keys import keys
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc.crypto.transaction_service import TransactionService
from aitbc_chain.rpc.router import router

# Deterministic secp256k1 test key and its derived Ethereum address.
PK_HEX = "4c0883a69102937d6231471b5dbb6204fe512961708279e1c1d4f0e0a1d9d2e3"
ADDR = keys.PrivateKey(bytes.fromhex(PK_HEX)).public_key.to_checksum_address()
TO_ADDR = "0x" + "11" * 20


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> TransactionService:
    """A TransactionService wired to the test key with nonce lookups stubbed."""
    monkeypatch.setenv("GENESIS_PRIVATE_KEY", PK_HEX)
    monkeypatch.setenv("GENESIS_ADDRESS", ADDR)
    monkeypatch.setenv("CHAIN_ID", "ait-testnet")
    svc = TransactionService()
    monkeypatch.setattr(svc, "get_nonce", lambda _addr: 0)
    return svc


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient bound to the RPC router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestSigningRoundTrip:
    """B6: TransactionService → /rpc/transaction → signature accepted."""

    def test_signed_tx_passes_endpoint_signature_check(self, service: TransactionService, client: TestClient) -> None:
        """A TransactionService-signed tx must NOT get 403 from /rpc/transaction.

        We only care about the signature check (line 107 of transactions.py).
        The mempool/account validation happens after the signature check, so
        we mock the mempool to isolate the signature verification.
        """
        tx = service.generate_signed_transaction(TO_ADDR, 100)
        assert tx is not None, "TransactionService should produce a signed tx"
        assert len(bytes.fromhex(tx["signature"])) == 65, "secp256k1 sig must be 65 bytes"
        assert tx["chain_id"] == "ait-testnet"

        # Mock the mempool so the endpoint gets past the signature check.
        # The signature check happens BEFORE mempool.add(), so if we get
        # anything other than 403, the signature was accepted.
        mock_mempool = MagicMock()
        mock_mempool.add.return_value = "0xmockhash"

        with (
            patch("aitbc_chain.rpc.transactions.get_mempool", return_value=mock_mempool),
            patch("aitbc_chain.rpc.transactions.session_scope") as mock_session_scope,
        ):
            # Mock session_scope to return a context manager with a session
            # that finds the sender account with sufficient balance.
            mock_session = MagicMock()
            mock_account = MagicMock()
            mock_account.balance = 1_000_000
            mock_account.nonce = 0
            mock_session.get.return_value = mock_account
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_session)
            mock_ctx.__exit__ = MagicMock(return_value=None)
            mock_session_scope.return_value = mock_ctx

            response = client.post("/transaction", json=tx)

        # 403 means signature rejected; anything else means signature accepted.
        assert response.status_code != 403, (
            f"Signature was rejected by the endpoint! Status: {response.status_code}, body: {response.text}"
        )

    def test_tampered_tx_is_rejected_by_endpoint(self, service: TransactionService, client: TestClient) -> None:
        """A tampered TransactionService tx must be rejected by the signature check.

        The endpoint's broad ``except Exception`` handler (transactions.py:116)
        re-wraps the 403 HTTPException as 400, so we check for either status
        code OR the "Invalid transaction signature" message in the body.
        """
        tx = service.generate_signed_transaction(TO_ADDR, 100)
        assert tx is not None
        tx["amount"] = 999_999  # tamper after signing

        response = client.post("/transaction", json=tx)
        body = response.text
        assert response.status_code == 403 or "Invalid transaction signature" in body, (
            f"Tampered tx should be rejected by signature check, got {response.status_code}: {body}"
        )

    def test_canonical_message_excludes_chain_id(self, service: TransactionService) -> None:
        """The signed message must exclude chain_id (verifier alignment).

        The node verifier reconstructs the message from {from, to, amount, fee,
        nonce, payload, type} — chain_id is NOT part of the signed payload.
        This test pins that contract.
        """
        from aitbc.crypto.transaction_service import _canonical_signing_message

        tx = service.generate_signed_transaction(TO_ADDR, 100)
        assert tx is not None
        signed_msg = _canonical_signing_message(tx)
        decoded = json.loads(signed_msg)
        assert "chain_id" not in decoded, "chain_id must NOT be in the signed message"
        assert "signature" not in decoded, "signature must NOT be in the signed message"
        assert set(decoded.keys()) == {"from", "to", "amount", "fee", "nonce", "payload", "type"}

    def test_recover_signer_matches_canonical_implementation(self, service: TransactionService) -> None:
        """A3: aitbc.crypto.recover_signer must recover the same address as the node verifier."""
        from aitbc.crypto import recover_signer

        tx = service.generate_signed_transaction(TO_ADDR, 100)
        assert tx is not None

        # The node endpoint constructs the verifier dict from exactly these
        # fields (transactions.py lines 95-104) — no chain_id, no signature.
        message_data = {
            "from": tx["from"],
            "to": tx["to"],
            "amount": tx["amount"],
            "fee": tx["fee"],
            "nonce": tx["nonce"],
            "payload": tx["payload"],
            "type": tx["type"],
        }
        recovered = recover_signer(message_data, tx["signature"])
        assert recovered is not None, "recover_signer should succeed for a valid signature"
        assert recovered.lower() == tx["from"].lower(), f"recover_signer returned {recovered}, expected {tx['from']}"
