"""Bridge test suite for the AITBC blockchain node.

Tests the cross-chain bridge lifecycle (lock -> confirm -> release) and
cryptographic proof verification, covering Bug 3 (forgeable proofs),
Bug 7 (missing signature verification on bridge endpoints) and
Bug 12 (cross-chain proof replay) regressions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from eth_keys import keys
from eth_utils import keccak
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc_chain.cross_chain.bridge import BridgeStatus, CrossChainBridge
from aitbc_chain.models import Account, CrossChainTransfer
from aitbc_chain.rpc.router import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sign_hash(private_key_hex: str, msg_hash: bytes) -> str:
    """Sign a keccak message hash with a private key, returning hex signature."""
    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    sig = pk.sign_msg_hash(msg_hash)
    return sig.to_hex()


def _canonical_hash(data: dict[str, Any]) -> bytes:
    """keccak256 of canonical JSON encoding (matches verify_request_signature)."""
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return keccak(message)


def _make_valid_proof(record: CrossChainTransfer, proposer_key: str) -> dict[str, Any]:
    """Build a cryptographically valid proof for a transfer record."""
    proof: dict[str, Any] = {
        "source_chain": record.source_chain,
        "lock_tx_hash": record.source_tx_hash or "0xlock",
        "amount": record.amount,
        "sender": record.sender,
        "recipient": record.recipient,
        "chain_id": record.source_chain,
        "block_height": 10,
        "block_hash": "0x" + "ab" * 32,
    }
    # Sign the proof (without proposer_signature) to produce proposer_signature
    proof_for_signing = {k: v for k, v in proof.items() if k != "proposer_signature"}
    msg_hash = _canonical_hash(proof_for_signing)
    proof["proposer_signature"] = _sign_hash(proposer_key, msg_hash)
    return proof


def _base_proof() -> dict[str, Any]:
    """A proof template with all required fields (signature is a placeholder)."""
    return {
        "source_chain": "chain-a",
        "lock_tx_hash": "0xlockhash",
        "amount": 1000,
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "chain_id": "chain-a",
        "block_height": 5,
        "block_hash": "0x" + "cd" * 32,
        "proposer_signature": "0x" + "11" * 65,
    }


def _make_record(
    source_chain: str = "chain-a",
    target_chain: str = "chain-b",
    sender: str = "0xsender",
    recipient: str = "0xrecipient",
    amount: int = 1000,
    status: str = "pending",
) -> CrossChainTransfer:
    """Create an in-memory CrossChainTransfer record (not persisted)."""
    return CrossChainTransfer(
        transfer_id="0xtransfer1",
        source_chain=source_chain,
        target_chain=target_chain,
        sender=sender,
        recipient=recipient,
        amount=amount,
        asset="native",
        status=status,
        source_tx_hash="0xlockhash",
        lock_time=datetime.now(UTC),
    )


@pytest.fixture
def bridge(engine) -> CrossChainBridge:
    """A CrossChainBridge backed by the in-memory engine."""
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient bound to the RPC router (wrapped in an app for middleware)."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def proposer_account() -> EthAccount:
    """An ephemeral Ethereum-style account used to sign proofs."""
    return EthAccount.create()


# ---------------------------------------------------------------------------
# Bridge Proof Verification Tests (Bug 3 + Bug 12 regression)
# ---------------------------------------------------------------------------


class TestProofVerification:
    """Direct unit tests for CrossChainBridge._validate_proof."""

    def test_proof_missing_proposer_signature_rejected(self, bridge: CrossChainBridge) -> None:
        """Bug 3: proof without proposer_signature must be rejected."""
        record = _make_record()
        proof = _base_proof()
        del proof["proposer_signature"]
        assert bridge._validate_proof(proof, record) is False

    def test_proof_missing_block_anchor_rejected(self, bridge: CrossChainBridge) -> None:
        """Bug 3: proof without block_height/block_hash must be rejected."""
        record = _make_record()
        proof = _base_proof()
        del proof["block_height"]
        del proof["block_hash"]
        assert bridge._validate_proof(proof, record) is False

    def test_proof_wrong_chain_id_rejected(self, bridge: CrossChainBridge) -> None:
        """Bug 12: proof with wrong chain_id must be rejected."""
        record = _make_record(source_chain="chain-a")
        proof = _base_proof()
        proof["chain_id"] = "chain-b"
        # Fix signature so only the chain_id mismatch is the failure cause
        proof_for_signing = {k: v for k, v in proof.items() if k != "proposer_signature"}
        proof["proposer_signature"] = _sign_hash(EthAccount.create().key.hex(), _canonical_hash(proof_for_signing))
        assert bridge._validate_proof(proof, record) is False

    def test_proof_field_mismatch_rejected(self, bridge: CrossChainBridge) -> None:
        """Proof with wrong amount/sender/recipient must be rejected."""
        record = _make_record(amount=1000, sender="0xsender", recipient="0xrecipient")
        for field, bad_value in [("amount", 9999), ("sender", "0xeve"), ("recipient", "0xeve")]:
            proof = _base_proof()
            proof[field] = bad_value
            proof_for_signing = {k: v for k, v in proof.items() if k != "proposer_signature"}
            proof["proposer_signature"] = _sign_hash(EthAccount.create().key.hex(), _canonical_hash(proof_for_signing))
            assert bridge._validate_proof(proof, record) is False, f"field {field} mismatch not rejected"

    def test_proof_with_all_fields_accepted(self, bridge: CrossChainBridge, proposer_account: EthAccount) -> None:
        """A complete, validly-signed proof must be accepted."""
        record = _make_record()
        proof = _make_valid_proof(record, proposer_account.key.hex())
        assert bridge._validate_proof(proof, record) is True

    def test_proof_with_invalid_signature_rejected(self, bridge: CrossChainBridge) -> None:
        """Bug 3: proof with an invalid proposer_signature must be rejected."""
        record = _make_record()
        proof = _make_valid_proof(record, EthAccount.create().key.hex())
        # Corrupt the signature so recovery fails
        proof["proposer_signature"] = "0x" + "00" * 65
        assert bridge._validate_proof(proof, record) is False


# ---------------------------------------------------------------------------
# Bridge Lock Endpoint Tests (Bug 7 regression)
# ---------------------------------------------------------------------------


class TestBridgeLockEndpoint:
    """RPC /bridge/lock signature & field validation (Bug 7)."""

    def test_bridge_lock_without_signature_rejected(self, client: TestClient) -> None:
        """POST /bridge/lock without a signature must return 403."""
        with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=object()):
            response = client.post(
                "/bridge/lock",
                json={
                    "target_chain": "chain-b",
                    "sender": "0xsender",
                    "recipient": "0xrecipient",
                    "amount": 1000,
                },
            )
        assert response.status_code == 403

    def test_bridge_lock_with_invalid_signature_rejected(self, client: TestClient) -> None:
        """POST /bridge/lock with a wrong signature must return 403."""
        with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=object()):
            response = client.post(
                "/bridge/lock",
                json={
                    "target_chain": "chain-b",
                    "sender": "0xsender",
                    "recipient": "0xrecipient",
                    "amount": 1000,
                    "signature": "0x" + "ff" * 65,
                },
            )
        assert response.status_code == 403

    def test_bridge_lock_missing_required_fields(self, client: TestClient) -> None:
        """POST /bridge/lock missing target_chain/sender/recipient must return 400."""
        with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=object()):
            response = client.post(
                "/bridge/lock",
                json={"amount": 1000, "signature": "0x" + "ff" * 65},
            )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Bridge Confirm Endpoint Tests (Bug 7 regression)
# ---------------------------------------------------------------------------


class TestBridgeConfirmEndpoint:
    """RPC /bridge/confirm signature & field validation (Bug 7)."""

    def test_bridge_confirm_disabled_by_default(self, client: TestClient) -> None:
        """POST /bridge/confirm must return 503 when BRIDGE_RELEASE_ENABLED is false (Bug 3 fence)."""
        with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=object()):
            response = client.post(
                "/bridge/confirm",
                json={
                    "transfer_id": "0xtransfer1",
                    "proof": _base_proof(),
                    "confirmer": "0xrecipient",
                    "signature": "0x" + "ff" * 65,
                },
            )
        assert response.status_code == 503
        assert "disabled" in response.json()["detail"].lower()

    def test_bridge_confirm_without_signature_rejected(self, client: TestClient) -> None:
        """POST /bridge/confirm without a confirmer signature must return 403."""
        with (
            patch("aitbc_chain.config.settings.bridge_release_enabled", True),
            patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=object()),
        ):
            response = client.post(
                "/bridge/confirm",
                json={
                    "transfer_id": "0xtransfer1",
                    "proof": _base_proof(),
                    "confirmer": "0xrecipient",
                },
            )
        assert response.status_code == 403

    def test_bridge_confirm_missing_transfer_id(self, client: TestClient) -> None:
        """POST /bridge/confirm without transfer_id must return 400."""
        with (
            patch("aitbc_chain.config.settings.bridge_release_enabled", True),
            patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=object()),
        ):
            response = client.post(
                "/bridge/confirm",
                json={"proof": _base_proof(), "confirmer": "0xrecipient", "signature": "0x" + "ff" * 65},
            )
        assert response.status_code == 400

    def test_bridge_confirm_missing_proof(self, client: TestClient) -> None:
        """POST /bridge/confirm without proof must return 400."""
        with (
            patch("aitbc_chain.config.settings.bridge_release_enabled", True),
            patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=object()),
        ):
            response = client.post(
                "/bridge/confirm",
                json={
                    "transfer_id": "0xtransfer1",
                    "confirmer": "0xrecipient",
                    "signature": "0x" + "ff" * 65,
                },
            )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Bridge Lifecycle Tests
# ---------------------------------------------------------------------------


class TestBridgeLifecycle:
    """Full lock -> confirm lifecycle using a real bridge + in-memory DB."""

    def test_bridge_lifecycle_lock_then_confirm(self, bridge: CrossChainBridge, proposer_account: EthAccount, engine) -> None:
        """Full lock -> confirm cycle with valid data and a valid proof."""
        sender = "0xlivesender"
        recipient = "0xliverecipient"
        source_chain = "chain-a"
        target_chain = "chain-b"
        amount = 5000

        # Seed the sender account with enough balance (amount + fee)
        with Session(engine) as session:
            session.add(Account(chain_id=source_chain, address=sender, balance=amount * 2, nonce=0))
            session.commit()

        # Step 1: lock
        transfer = bridge.initiate_transfer(
            source_chain=source_chain,
            target_chain=target_chain,
            sender=sender,
            recipient=recipient,
            amount=amount,
        )
        assert transfer.status == BridgeStatus.locked
        assert transfer.source_tx_hash == transfer.transfer_id

        # Build a valid proof for the persisted record
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None
            proof = _make_valid_proof(record, proposer_account.key.hex())

        # Step 2: confirm
        completed = bridge.confirm_transfer(transfer.transfer_id, proof)
        assert completed.status == BridgeStatus.completed
        assert completed.target_tx_hash is not None
        assert completed.confirm_time is not None

        # Recipient balance must have been credited on the target chain
        with Session(engine) as session:
            recipient_account = session.get(Account, (target_chain, recipient))
            assert recipient_account is not None
            assert recipient_account.balance == amount

    def test_bridge_transfer_status_tracking(self, bridge: CrossChainBridge, proposer_account: EthAccount, engine) -> None:
        """Verify transfer status transitions (pending -> locked -> confirmed)."""
        sender = "0xtracksender"
        recipient = "0xtrackrecipient"
        source_chain = "chain-a"
        target_chain = "chain-b"
        amount = 3000

        with Session(engine) as session:
            session.add(Account(chain_id=source_chain, address=sender, balance=amount * 2, nonce=0))
            session.commit()

        # DB record starts as "pending" after initiation
        transfer = bridge.initiate_transfer(
            source_chain=source_chain,
            target_chain=target_chain,
            sender=sender,
            recipient=recipient,
            amount=amount,
        )
        # The returned BridgeTransfer reports "locked" status
        assert transfer.status == BridgeStatus.locked

        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None
            assert record.status == "pending"
            proof = _make_valid_proof(record, proposer_account.key.hex())

        completed = bridge.confirm_transfer(transfer.transfer_id, proof)
        assert completed.status == BridgeStatus.completed

        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None
            assert record.status == "completed"


# ---------------------------------------------------------------------------
# Cross-Chain Contamination Tests (Bug 12 regression)
# ---------------------------------------------------------------------------


class TestCrossChainContamination:
    """Proofs must not be replayable across chains (Bug 12)."""

    def test_proof_replay_across_chains_rejected(self, bridge: CrossChainBridge, proposer_account: EthAccount) -> None:
        """A proof valid for chain A must be rejected for a transfer on chain B."""
        record_a = _make_record(source_chain="chain-a", target_chain="chain-b")
        proof = _make_valid_proof(record_a, proposer_account.key.hex())
        assert bridge._validate_proof(proof, record_a) is True

        # A different transfer record on chain B must reject chain A's proof
        record_b = _make_record(source_chain="chain-b", target_chain="chain-c")
        assert bridge._validate_proof(proof, record_b) is False
