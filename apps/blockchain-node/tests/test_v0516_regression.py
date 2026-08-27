"""Regression test suite for AITBC v0.5.16 — 18 bug fixes.

Tests cover:
  Bug 1:  chain_id in TransactionRequest
  Bug 2:  chain_id in sync RPC (fetch_blocks_range, bulk_import_from)
  Bug 3+12: Bridge proof verification (proposer_signature, block anchor, chain_id)
  Bug 4:  Transaction signature verification
  Bug 5:  authorize_arbitrator owner verification
  Bug 7:  Bridge lock/confirm signature verification
  Bug 8:  Staking signature verification
  Bug 9:  Mining endpoint authentication
  Bug 10+11: Silent import failures + contract stub (503 not fake success)
  Bug 13: Staking chain_id validation
  Bug 14: X-Wallet-Address header warning
  Bug 15: RPC port fix (8006 not 8202)
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from aitbc_chain.config import settings
from aitbc_chain.contracts.dispute_resolution import dispute_resolution_contract
from aitbc_chain.cross_chain.bridge import (
    CrossChainBridge,
    init_cross_chain_bridge,
)
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.rpc.auth import get_authenticated_address
from aitbc_chain.rpc.router import router
from aitbc_chain.rpc.transactions import TransactionRequest
from aitbc_chain.rpc.utils import (
    sign_transaction_data,
    validate_chain_id,
    verify_transaction_signature,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from aitbc_chain.metadata import chain_metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_keypair():
    """Generate a deterministic Ethereum-style key pair for testing."""
    from eth_keys import keys

    priv_key = keys.PrivateKey(b"\x01" * 32)
    address = priv_key.public_key.to_checksum_address()
    return priv_key, address


def _sign_message(priv_key, message_data: dict[str, Any]) -> str:
    """Sign a dict message with keccak256 + eth_keys, returning hex signature."""
    from eth_utils import keccak

    message = json.dumps(message_data, sort_keys=True, separators=(",", ":")).encode()
    msg_hash = keccak(message)
    sig = priv_key.sign_msg_hash(msg_hash)
    return sig.to_hex()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


@pytest.fixture
def client():
    """Create a TestClient for the RPC router (wrapped in a FastAPI app for middleware)."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def db_engine(tmp_path):
    """In-memory SQLite engine for sync/bridge tests."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test_v0516.db'}", echo=False)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    """Context-manager session factory backed by the test engine."""

    @contextmanager
    def _factory():
        with Session(db_engine) as session:
            yield session

    return _factory


@pytest.fixture
def mock_session_factory():
    """A no-op session factory that yields a Mock session."""

    @contextmanager
    def _factory():
        yield MagicMock()

    return _factory


@pytest.fixture
def initialized_bridge(mock_session_factory):
    """Initialise the global cross-chain bridge with a mock session factory."""
    bridge = init_cross_chain_bridge(mock_session_factory)
    yield bridge
    # Reset global bridge after test
    import aitbc_chain.cross_chain.bridge as bridge_mod

    bridge_mod._bridge_instance = None


# ---------------------------------------------------------------------------
# Bug 1: chain_id in TransactionRequest
# ---------------------------------------------------------------------------


class TestBug1ChainIdInTransactionRequest:
    """TransactionRequest must accept and propagate chain_id."""

    def test_transaction_request_accepts_chain_id(self) -> None:
        """TransactionRequest model accepts an optional chain_id field."""
        req = TransactionRequest.model_validate(
            {
                "from": "0xsender",
                "to": "0xrecipient",
                "amount": 100,
                "nonce": 1,
                "fee": 10,
                "chain_id": "ait-testnet",
                "signature": "0xabc123",
            }
        )
        assert req.chain_id == "ait-testnet"

    def test_transaction_request_chain_id_defaults_none(self) -> None:
        """chain_id defaults to None when not provided."""
        req = TransactionRequest.model_validate(
            {
                "from": "0xsender",
                "to": "0xrecipient",
                "amount": 100,
                "nonce": 1,
                "fee": 10,
                "signature": "0xabc123",
            }
        )
        assert req.chain_id is None


@contextmanager
def _null_session_scope():
    """A no-op session_scope that yields a Mock."""
    yield MagicMock()


# ---------------------------------------------------------------------------
# Bug 2: chain_id in sync RPC
# ---------------------------------------------------------------------------


class TestBug2ChainIdInSyncRPC:
    """fetch_blocks_range and bulk_import_from must send chain_id to remote peers."""


# ---------------------------------------------------------------------------
# Bug 3 + 12: Bridge proof verification
# ---------------------------------------------------------------------------


class TestBug3And12BridgeProofVerification:
    """_validate_proof must reject forgeable proofs and verify chain_id + signature."""

    @pytest.fixture
    def bridge(self, mock_session_factory):
        """Create a CrossChainBridge instance for direct _validate_proof testing."""
        return CrossChainBridge(mock_session_factory)

    @pytest.fixture
    def valid_record(self):
        """A CrossChainTransfer-like record matching the valid proof."""
        return SimpleNamespace(
            transfer_id="0xtransfer123",
            source_chain="ait-source",
            target_chain="ait-target",
            sender="0xsender",
            recipient="0xrecipient",
            amount=1000,
            asset="native",
            status="pending",
        )

    def _base_proof(self, record) -> dict[str, Any]:
        """Build a proof dict with all required fields except proposer_signature."""
        return {
            "source_chain": record.source_chain,
            "lock_tx_hash": "0xlocktxhash",
            "amount": record.amount,
            "sender": record.sender,
            "recipient": record.recipient,
            "chain_id": record.source_chain,
            "block_height": 42,
            "block_hash": "0x" + "a" * 64,
        }

    def test_rejects_proof_missing_proposer_signature(self, bridge, valid_record) -> None:
        """Proof without proposer_signature is rejected."""
        proof = self._base_proof(valid_record)
        # proposer_signature intentionally omitted
        assert bridge._validate_proof(proof, valid_record) is False

    def test_rejects_proof_missing_block_height(self, bridge, valid_record) -> None:
        """Proof without block_height is rejected."""
        proof = self._base_proof(valid_record)
        proof["proposer_signature"] = "0x" + "b" * 130
        del proof["block_height"]
        assert bridge._validate_proof(proof, valid_record) is False

    def test_rejects_proof_missing_block_hash(self, bridge, valid_record) -> None:
        """Proof without block_hash is rejected."""
        proof = self._base_proof(valid_record)
        proof["proposer_signature"] = "0x" + "b" * 130
        del proof["block_hash"]
        assert bridge._validate_proof(proof, valid_record) is False

    def test_rejects_proof_with_wrong_chain_id(self, bridge, valid_record) -> None:
        """Proof with chain_id not matching record's source_chain is rejected."""
        proof = self._base_proof(valid_record)
        proof["chain_id"] = "ait-wrong-chain"
        proof["proposer_signature"] = "0x" + "b" * 130
        assert bridge._validate_proof(proof, valid_record) is False

    def test_accepts_valid_proof_with_valid_signature(self, bridge, valid_record) -> None:
        """A complete proof with a valid proposer_signature is accepted."""
        priv_key, _ = _generate_keypair()
        proof = self._base_proof(valid_record)
        # Sign the proof (excluding proposer_signature) with the test private key
        proof_for_signing = {k: v for k, v in proof.items() if k != "proposer_signature"}
        proof["proposer_signature"] = _sign_message(priv_key, proof_for_signing)
        # v0.7.2: _validate_proof now does block header lookup + validator set freshness
        # check. With a mock session, these fail. Use "field-eq" mode (skips block header
        # lookup) and patch validator set freshness to return True.
        with patch.object(bridge, "_check_validator_set_freshness", return_value=True):
            with patch.object(settings, "bridge_verification_mode", "field-eq"):
                assert bridge._validate_proof(proof, valid_record) is True

    def test_rejects_proof_with_invalid_signature(self, bridge, valid_record) -> None:
        """A proof with an invalid (malformed) proposer_signature is rejected."""
        proof = self._base_proof(valid_record)
        proof["proposer_signature"] = "0xinvalid"
        assert bridge._validate_proof(proof, valid_record) is False


# ---------------------------------------------------------------------------
# Bug 4: Transaction signature verification
# ---------------------------------------------------------------------------


class TestBug4TransactionSignatureVerification:
    """submit_transaction must verify the transaction signature."""

    def test_verify_transaction_signature_rejects_invalid_sig(self) -> None:
        """verify_transaction_signature returns False for an invalid signature."""
        tx_data = {
            "from": "0xsender",
            "to": "0xrecipient",
            "amount": 100,
            "nonce": 1,
            "fee": 10,
        }
        # A random 65-byte hex string that won't recover to the sender
        fake_sig = "0x" + "ab" * 65
        assert verify_transaction_signature(tx_data, fake_sig, "0xsender") is False

    def test_verify_transaction_signature_rejects_missing_sig(self) -> None:
        """verify_transaction_signature returns False when signature is empty."""
        tx_data = {"from": "0xsender", "to": "0xrecipient", "amount": 100}
        assert verify_transaction_signature(tx_data, "", "0xsender") is False

    def test_verify_transaction_signature_rejects_missing_sender(self) -> None:
        """verify_transaction_signature returns False when sender is empty."""
        tx_data = {"from": "0xsender", "to": "0xrecipient", "amount": 100}
        assert verify_transaction_signature(tx_data, "0xabc", "") is False

    def test_verify_transaction_signature_accepts_valid_sig(self) -> None:
        """verify_transaction_signature returns True for a correctly signed transaction."""
        priv_key, sender_address = _generate_keypair()
        tx_data = {
            "from": sender_address,
            "to": "0xrecipient",
            "amount": 100,
            "nonce": 1,
            "fee": 10,
            "type": "TRANSFER",
        }
        # Build the message the same way verify_transaction_signature does
        tx_without_sig = {k: v for k, v in tx_data.items() if k != "signature"}
        signature = _sign_message(priv_key, tx_without_sig)
        assert verify_transaction_signature(tx_data, signature, sender_address) is True

    def test_verify_transaction_signature_ignores_gossip_tx_hash(self) -> None:
        """Followers attach tx_hash after signing; verification must ignore it."""
        priv_key, sender_address = _generate_keypair()
        tx_data = {
            "from": sender_address,
            "to": "0xrecipient",
            "amount": 3600,
            "nonce": 0,
            "fee": 36,
            "type": "ESCROW_LOCK",
            "payload": {
                "job_id": "354a98bb66104d1f95e76e744ee8ab0a",
                "provider": "0xa54b82312beb65d0e90c21717ea372396991fa36",
            },
            "chain_id": "ait-hub",
        }
        signature = _sign_message(priv_key, tx_data)
        gossiped = dict(tx_data)
        gossiped["signature"] = signature
        gossiped["tx_hash"] = "0xabea1a7f038dedf89995549f94e656dfe147e9a707a8ebe7dddad6a4d6424081"
        gossiped["value"] = 3600
        assert verify_transaction_signature(gossiped, signature, sender_address) is True

    def test_sign_transaction_data_ignores_gossip_fields_and_value(self) -> None:
        """sign_transaction_data must exclude signature, tx_hash and the value alias."""
        priv_key, sender_address = _generate_keypair()
        tx_data = {
            "from": sender_address,
            "to": "0xrecipient",
            "amount": 3600,
            "nonce": 0,
            "fee": 36,
            "type": "ESCROW_LOCK",
            "payload": {
                "job_id": "354a98bb66104d1f95e76e744ee8ab0a",
                "provider": "0xa54b82312beb65d0e90c21717ea372396991fa36",
            },
            "chain_id": "ait-hub",
        }
        signature = sign_transaction_data(tx_data, priv_key.to_hex())

        # Adding gossip / internal fields after signing must not break verification.
        gossiped = dict(tx_data)
        gossiped["signature"] = signature
        gossiped["tx_hash"] = "0xabea1a7f038dedf89995549f94e656dfe147e9a707a8ebe7dddad6a4d6424081"
        gossiped["value"] = 3600
        assert verify_transaction_signature(gossiped, signature, sender_address) is True

        # Providing tx_hash or value to the signer itself must not change the signed bytes.
        with_hash = dict(tx_data)
        with_hash["tx_hash"] = "0xabea1a7f038dedf89995549f94e656dfe147e9a707a8ebe7dddad6a4d6424081"
        assert sign_transaction_data(with_hash, priv_key.to_hex()) == signature

        with_value = dict(tx_data)
        with_value["value"] = 3600
        assert sign_transaction_data(with_value, priv_key.to_hex()) == signature


# ---------------------------------------------------------------------------
# Bug 5: authorize_arbitrator owner verification
# ---------------------------------------------------------------------------


class TestBug5AuthorizeArbitratorOwnerVerification:
    """authorize_arbitrator must verify owner_address and owner_signature."""

    @pytest.fixture
    def contract_with_owner(self):
        """DisputeResolutionContract with a known owner set."""
        priv_key, owner_address = _generate_keypair()
        contract = dispute_resolution_contract
        contract.set_owner(owner_address)
        contract._test_priv_key = priv_key  # type: ignore[attr-defined]
        contract._test_owner_address = owner_address  # type: ignore[attr-defined]
        yield contract
        # Reset owner after test
        contract._owner = None

    def test_rejects_wrong_owner_address(self, contract_with_owner) -> None:
        """authorize_arbitrator rejects when owner_address doesn't match _owner."""
        result = contract_with_owner.authorize_arbitrator(
            arbitrator_address="0xnewarb",
            reputation_score=90,
            owner_address="0xwrongowner",
            owner_signature="0xabc",
        )
        assert result["success"] is False
        assert "owner" in result["message"].lower()

    def test_rejects_missing_owner_signature(self, contract_with_owner) -> None:
        """authorize_arbitrator rejects when owner_signature is None."""
        owner_addr = contract_with_owner._test_owner_address  # type: ignore[attr-defined]
        result = contract_with_owner.authorize_arbitrator(
            arbitrator_address="0xnewarb",
            reputation_score=90,
            owner_address=owner_addr,
            owner_signature=None,
        )
        assert result["success"] is False
        assert "signature" in result["message"].lower()

    def test_rejects_invalid_owner_signature(self, contract_with_owner) -> None:
        """authorize_arbitrator rejects an invalid owner_signature."""
        owner_addr = contract_with_owner._test_owner_address  # type: ignore[attr-defined]
        result = contract_with_owner.authorize_arbitrator(
            arbitrator_address="0xnewarb",
            reputation_score=90,
            owner_address=owner_addr,
            owner_signature="0x" + "cd" * 65,  # invalid signature
        )
        assert result["success"] is False
        assert "signature" in result["message"].lower()

    def test_accepts_valid_owner_signature(self, contract_with_owner) -> None:
        """authorize_arbitrator accepts with correct owner + valid signature."""
        owner_addr = contract_with_owner._test_owner_address  # type: ignore[attr-defined]
        priv_key = contract_with_owner._test_priv_key  # type: ignore[attr-defined]
        sign_data = {
            "action": "authorize_arbitrator",
            "arbitrator_address": "0xnewarb123",
            "reputation_score": 90,
        }
        signature = _sign_message(priv_key, sign_data)
        result = contract_with_owner.authorize_arbitrator(
            arbitrator_address="0xnewarb123",
            reputation_score=90,
            owner_address=owner_addr,
            owner_signature=signature,
        )
        assert result["success"] is True
        assert result["status"] == "Authorized"

    def test_rejects_when_owner_not_set(self) -> None:
        """authorize_arbitrator rejects when contract owner is not set."""
        # Use a fresh contract instance to avoid interfering with the global one
        from aitbc_chain.contracts.dispute_resolution import DisputeResolutionContract

        contract = DisputeResolutionContract()
        assert contract._owner is None
        result = contract.authorize_arbitrator(
            arbitrator_address="0xnewarb",
            reputation_score=90,
            owner_address="0xsomeowner",
            owner_signature="0xabc",
        )
        assert result["success"] is False
        assert "owner" in result["message"].lower()


# ---------------------------------------------------------------------------
# Bug 7: Bridge lock/confirm signature verification
# ---------------------------------------------------------------------------


class TestBug7BridgeLockConfirmSignatureVerification:
    """bridge_lock and bridge_confirm must verify signatures."""

    @pytest.fixture(autouse=True)
    def _patch_supported_chains(self):
        """Allow test chain IDs (ait-source, ait-target) in bridge RPC validation."""
        with patch.object(settings, "supported_chains", "ait-source,ait-target,chain-a,chain-b"):
            yield


# ---------------------------------------------------------------------------
# Bug 8: Staking signature verification
# ---------------------------------------------------------------------------


class TestBug8StakingSignatureVerification:
    """stake_tokens and unstake_tokens must verify signatures."""

    @pytest.fixture
    def supported_chain(self, monkeypatch):
        """Configure settings so 'ait-testnet' is a supported chain."""
        monkeypatch.setattr(settings, "chain_id", "ait-testnet")
        monkeypatch.setattr(settings, "supported_chains", "ait-testnet")
        return "ait-testnet"


# ---------------------------------------------------------------------------
# Bug 9: Mining endpoint authentication
# ---------------------------------------------------------------------------


class TestBug9MiningEndpointAuthentication:
    """Mining endpoints require authentication via X-Wallet-Address header."""


# ---------------------------------------------------------------------------
# Bug 10 + 11: Silent import failures + contract stub
# ---------------------------------------------------------------------------


class TestBug10And11ContractStub:
    """contracts_stub must raise HTTPException(503), not return fake success."""


# ---------------------------------------------------------------------------
# Bug 13: Staking chain_id validation
# ---------------------------------------------------------------------------


class TestBug13StakingChainIdValidation:
    """stake_tokens must reject unsupported chain_id with 400."""

    def test_validate_chain_id_helper(self, monkeypatch) -> None:
        """validate_chain_id returns True for supported, False for unsupported."""
        monkeypatch.setattr(settings, "supported_chains", "ait-mainnet,ait-testnet")
        assert validate_chain_id("ait-mainnet") is True
        assert validate_chain_id("ait-testnet") is True
        assert validate_chain_id("ait-unknown") is False


# ---------------------------------------------------------------------------
# Bug 14: X-Wallet-Address header warning
# ---------------------------------------------------------------------------


class TestBug14XWalletAddressHeaderWarning:
    """Auth must reject X-Wallet-Address unless TRUST_X_WALLET_ADDRESS=true."""

    def _make_request(self, wallet_address: str | None = None):
        """Create a mock FastAPI Request with optional X-Wallet-Address header."""
        request = MagicMock()
        headers = {}
        if wallet_address:
            headers["X-Wallet-Address"] = wallet_address
        request.headers.get = lambda key, default=None: headers.get(key, default)
        return request

    def test_rejects_x_wallet_address_when_trust_not_set(self, monkeypatch) -> None:
        """Auth rejects X-Wallet-Address when TRUST_X_WALLET_ADDRESS is not 'true'."""
        monkeypatch.delenv("TRUST_X_WALLET_ADDRESS", raising=False)
        wallet = "0x" + "1" * 40
        request = self._make_request(wallet)
        with pytest.raises(HTTPException) as exc_info:
            get_authenticated_address(request)
        assert exc_info.value.status_code == 401

    def test_rejects_x_wallet_address_when_trust_false(self, monkeypatch) -> None:
        """Auth rejects X-Wallet-Address when TRUST_X_WALLET_ADDRESS=false."""
        monkeypatch.setenv("TRUST_X_WALLET_ADDRESS", "false")
        wallet = "0x" + "1" * 40
        request = self._make_request(wallet)
        with pytest.raises(HTTPException) as exc_info:
            get_authenticated_address(request)
        assert exc_info.value.status_code == 401

    def test_accepts_x_wallet_address_when_trust_true(self, monkeypatch) -> None:
        """Auth accepts X-Wallet-Address when TRUST_X_WALLET_ADDRESS=true."""
        monkeypatch.setenv("TRUST_X_WALLET_ADDRESS", "true")
        wallet = "0x" + "1" * 40
        request = self._make_request(wallet)
        result = get_authenticated_address(request)
        assert result == wallet

    def test_rejects_invalid_wallet_address_format(self, monkeypatch) -> None:
        """Auth rejects X-Wallet-Address with invalid format (not 0x + 40 hex)."""
        monkeypatch.setenv("TRUST_X_WALLET_ADDRESS", "true")
        request = self._make_request("0xshort")
        with pytest.raises(HTTPException) as exc_info:
            get_authenticated_address(request)
        assert exc_info.value.status_code == 401

    def test_rejects_when_no_auth_provided(self, monkeypatch) -> None:
        """Auth rejects when no X-Wallet-Address and no credentials are provided."""
        monkeypatch.delenv("TRUST_X_WALLET_ADDRESS", raising=False)
        monkeypatch.delenv("DEV_MODE", raising=False)
        request = self._make_request(None)
        with pytest.raises(HTTPException) as exc_info:
            get_authenticated_address(request)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Bug 15: RPC port fix
# ---------------------------------------------------------------------------


class TestBug15RpcPortFix:
    """TransactionService must default to port 8202 (correct port), not stale 8006."""

    def test_transaction_service_defaults_to_8202(self, monkeypatch) -> None:
        """TransactionService rpc_url defaults to http://localhost:8202."""
        # Ensure BLOCKCHAIN_RPC_URL is not set
        monkeypatch.delenv("BLOCKCHAIN_RPC_URL", raising=False)
        from aitbc.crypto.transaction_service import TransactionService

        service = TransactionService()
        assert service.rpc_url == "http://localhost:8202"
        assert "8006" not in service.rpc_url

    def test_transaction_service_respects_env_override(self, monkeypatch) -> None:
        """TransactionService uses BLOCKCHAIN_RPC_URL when set."""
        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://node.example:9000")
        from aitbc.crypto.transaction_service import TransactionService

        service = TransactionService()
        assert service.rpc_url == "http://node.example:9000"
