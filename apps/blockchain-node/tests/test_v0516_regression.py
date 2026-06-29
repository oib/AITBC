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
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from aitbc_chain.config import settings
from aitbc_chain.contracts.dispute_resolution import dispute_resolution_contract
from aitbc_chain.cross_chain.bridge import (
    CrossChainBridge,
    init_cross_chain_bridge,
)
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.rpc.auth import get_authenticated_address
from aitbc_chain.rpc.contracts_stub import _stub
from aitbc_chain.rpc.router import router
from aitbc_chain.rpc.transactions import TransactionRequest, submit_transaction
from aitbc_chain.rpc.utils import (
    validate_chain_id,
    verify_transaction_signature,
)
from aitbc_chain.sync import ChainSync
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


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
    SQLModel.metadata.create_all(engine)
    return engine


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

    def test_submit_transaction_uses_provided_chain_id(self, monkeypatch) -> None:
        """submit_transaction resolves chain_id from the request, not just settings."""
        # Mock get_mempool so we don't need a real mempool
        mock_mempool = MagicMock()
        mock_mempool.add.return_value = "0xtxhash"
        monkeypatch.setattr("aitbc_chain.mempool.get_mempool", lambda: mock_mempool)
        # Mock verify_transaction_signature to return True (signature is valid)
        monkeypatch.setattr(
            "aitbc_chain.rpc.transactions.verify_transaction_signature",
            lambda tx, sig, sender: True,
        )
        # Mock _validate_transaction_admission to do nothing
        monkeypatch.setattr(
            "aitbc_chain.rpc.transactions._validate_transaction_admission",
            lambda tx, mempool: None,
        )
        # Mock session_scope
        monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", lambda: _null_session_scope())

        # Capture the chain_id used
        captured_chain_id: list[str] = []

        def mock_get_chain_id(cid: str | None = None) -> str:
            result = cid if cid is not None else "ait-mainnet"
            captured_chain_id.append(result)
            return result

        monkeypatch.setattr("aitbc_chain.rpc.transactions.get_chain_id", mock_get_chain_id)

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

        import asyncio

        result = asyncio.run(submit_transaction(MagicMock(), req))
        assert result["success"] is True
        assert captured_chain_id == ["ait-testnet"]


@contextmanager
def _null_session_scope():
    """A no-op session_scope that yields a Mock."""
    yield MagicMock()


# ---------------------------------------------------------------------------
# Bug 2: chain_id in sync RPC
# ---------------------------------------------------------------------------


class TestBug2ChainIdInSyncRPC:
    """fetch_blocks_range and bulk_import_from must send chain_id to remote peers."""

    def test_fetch_blocks_range_sends_chain_id(self, session_factory) -> None:
        """fetch_blocks_range includes chain_id in query params."""
        import asyncio

        sync = ChainSync(session_factory, chain_id="ait-testnet", validate_signatures=False)

        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        sync._client = mock_client

        asyncio.run(sync.fetch_blocks_range(0, 10, "http://source-rpc"))

        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args.kwargs
        assert "params" in call_kwargs
        assert call_kwargs["params"]["chain_id"] == "ait-testnet"
        assert call_kwargs["params"]["start"] == 0
        assert call_kwargs["params"]["end"] == 10

    def test_bulk_import_from_sends_chain_id_to_head(self, session_factory) -> None:
        """bulk_import_from includes chain_id in the /rpc/head request."""
        import asyncio

        sync = ChainSync(session_factory, chain_id="ait-testnet", validate_signatures=False)

        # Mock /rpc/head response — return height -1 so sync exits early
        head_response = Mock()
        head_response.json.return_value = {"height": -1}
        head_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=head_response)
        sync._client = mock_client

        asyncio.run(sync.bulk_import_from("http://source-rpc"))

        # Verify /rpc/head was called with chain_id in params
        first_call = mock_client.get.call_args_list[0]
        assert first_call.args[0] == "http://source-rpc/rpc/head"
        assert first_call.kwargs["params"]["chain_id"] == "ait-testnet"


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

    def test_submit_transaction_rejects_invalid_signature(self, client, monkeypatch) -> None:
        """POST /transaction with an invalid signature is rejected (not 200)."""
        # Mock get_mempool so it doesn't fail before signature check
        mock_mempool = MagicMock()
        monkeypatch.setattr("aitbc_chain.mempool.get_mempool", lambda: mock_mempool)

        response = client.post(
            "/transaction",
            json={
                "from": "0xsender",
                "to": "0xrecipient",
                "amount": 100,
                "nonce": 1,
                "fee": 10,
                "signature": "0x" + "ab" * 65,  # invalid signature
            },
        )
        # The 403 is raised inside a try/except that wraps to 400, so accept either
        assert response.status_code in (400, 403)
        assert response.status_code != 200

    def test_submit_transaction_rejects_missing_signature(self, client) -> None:
        """POST /transaction without signature field fails with 422 (required field)."""
        response = client.post(
            "/transaction",
            json={
                "from": "0xsender",
                "to": "0xrecipient",
                "amount": 100,
                "nonce": 1,
                "fee": 10,
                # signature intentionally omitted
            },
        )
        assert response.status_code == 422


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

    def test_bridge_lock_rejects_without_signature(self, client, initialized_bridge) -> None:
        """POST /bridge/lock without signature returns 403."""
        response = client.post(
            "/bridge/lock",
            json={
                "source_chain": "ait-source",
                "target_chain": "ait-target",
                "sender": "0xsender",
                "recipient": "0xrecipient",
                "amount": 1000,
                # signature intentionally omitted
            },
        )
        assert response.status_code == 403

    def test_bridge_lock_rejects_invalid_signature(self, client, initialized_bridge) -> None:
        """POST /bridge/lock with invalid signature returns 403."""
        response = client.post(
            "/bridge/lock",
            json={
                "source_chain": "ait-source",
                "target_chain": "ait-target",
                "sender": "0xsender",
                "recipient": "0xrecipient",
                "amount": 1000,
                "signature": "0x" + "ab" * 65,  # invalid signature
            },
        )
        assert response.status_code == 403

    def test_bridge_confirm_rejects_without_signature(self, client, initialized_bridge) -> None:
        """POST /bridge/confirm without confirmer signature returns 403."""
        # B1 fence: enable the release path so we reach the Bug 7 signature check.
        with patch.object(settings, "bridge_release_enabled", True):
            response = client.post(
                "/bridge/confirm",
                json={
                    "transfer_id": "0xtransfer123",
                    "proof": {"source_chain": "ait-source"},
                    "confirmer": "0xrecipient",
                    # signature intentionally omitted
                },
            )
        assert response.status_code == 403

    def test_bridge_confirm_rejects_without_confirmer(self, client, initialized_bridge) -> None:
        """POST /bridge/confirm without confirmer address returns 403."""
        # B1 fence: enable the release path so we reach the Bug 7 signature check.
        with patch.object(settings, "bridge_release_enabled", True):
            response = client.post(
                "/bridge/confirm",
                json={
                    "transfer_id": "0xtransfer123",
                    "proof": {"source_chain": "ait-source"},
                    "signature": "0xabc",
                    # confirmer intentionally omitted
                },
            )
        assert response.status_code == 403


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

    def test_stake_tokens_rejects_without_signature(self, client, supported_chain) -> None:
        """POST /staking/stake without signature returns 403."""
        response = client.post(
            "/staking/stake",
            json={
                "address": "0xstaker",
                "amount": 1000,
                "chain_id": supported_chain,
                # signature intentionally omitted
            },
        )
        assert response.status_code == 403

    def test_unstake_tokens_rejects_without_signature(self, client, supported_chain) -> None:
        """POST /staking/unstake without signature returns 403."""
        response = client.post(
            "/staking/unstake",
            json={
                "address": "0xstaker",
                "stake_id": 1,
                "chain_id": supported_chain,
                # signature intentionally omitted
            },
        )
        assert response.status_code == 403

    def test_stake_tokens_rejects_invalid_signature(self, client, supported_chain) -> None:
        """POST /staking/stake with invalid signature returns 403."""
        response = client.post(
            "/staking/stake",
            json={
                "address": "0xstaker",
                "amount": 1000,
                "chain_id": supported_chain,
                "signature": "0x" + "ab" * 65,  # invalid signature
            },
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Bug 9: Mining endpoint authentication
# ---------------------------------------------------------------------------


class TestBug9MiningEndpointAuthentication:
    """Mining endpoints require authentication via X-Wallet-Address header."""

    def test_mining_start_requires_authentication(self, client) -> None:
        """POST /mining/start without X-Wallet-Address returns 401."""
        response = client.post("/mining/start", json={"miner_address": "0xminer", "threads": 1})
        assert response.status_code == 401

    def test_mining_stop_requires_authentication(self, client) -> None:
        """POST /mining/stop without X-Wallet-Address returns 401."""
        response = client.post("/mining/stop")
        assert response.status_code == 401

    def test_mining_status_requires_authentication(self, client) -> None:
        """GET /mining/status without X-Wallet-Address returns 401."""
        response = client.get("/mining/status")
        assert response.status_code == 401

    def test_mining_miners_requires_authentication(self, client) -> None:
        """GET /mining/miners without X-Wallet-Address returns 401 (Bug 9 closure — was previously unauthenticated)."""
        response = client.get("/mining/miners")
        assert response.status_code == 401

    def test_mining_start_succeeds_with_trusted_header(self, client, monkeypatch) -> None:
        """POST /mining/start succeeds when TRUST_X_WALLET_ADDRESS=true and header is set."""
        monkeypatch.setenv("TRUST_X_WALLET_ADDRESS", "true")
        wallet = "0x" + "1" * 40
        response = client.post(
            "/mining/start",
            json={"miner_address": "0xminer", "threads": 1},
            headers={"X-Wallet-Address": wallet},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "started"


# ---------------------------------------------------------------------------
# Bug 10 + 11: Silent import failures + contract stub
# ---------------------------------------------------------------------------


class TestBug10And11ContractStub:
    """contracts_stub must raise HTTPException(503), not return fake success."""

    def test_stub_raises_503(self) -> None:
        """The _stub function raises HTTPException with status 503."""
        with pytest.raises(HTTPException) as exc_info:
            import asyncio

            asyncio.run(_stub(MagicMock()))

        assert exc_info.value.status_code == 503

    def test_all_stub_functions_raise_503(self) -> None:
        """Every stub function raises HTTPException(503)."""
        import aitbc_chain.rpc.contracts_stub as stub_mod

        stub_functions = [
            stub_mod.deploy_messaging_contract,
            stub_mod.list_contracts,
            stub_mod.deploy_contract,
            stub_mod.call_contract,
            stub_mod.verify_contract,
            stub_mod.get_messaging_contract_state,
            stub_mod.get_forum_topics,
            stub_mod.create_forum_topic,
            stub_mod.get_topic_messages,
            stub_mod.post_message,
            stub_mod.vote_message,
            stub_mod.search_messages,
            stub_mod.get_agent_reputation,
            stub_mod.moderate_message,
        ]
        import asyncio

        for fn in stub_functions:
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(fn(MagicMock()))
            assert exc_info.value.status_code == 503, f"{fn.__name__} did not raise 503"


# ---------------------------------------------------------------------------
# Bug 13: Staking chain_id validation
# ---------------------------------------------------------------------------


class TestBug13StakingChainIdValidation:
    """stake_tokens must reject unsupported chain_id with 400."""

    def test_stake_tokens_rejects_unsupported_chain_id(self, client, monkeypatch) -> None:
        """POST /staking/stake with unsupported chain_id returns 400."""
        # Configure settings so only 'ait-mainnet' is supported
        monkeypatch.setattr(settings, "supported_chains", "ait-mainnet")
        monkeypatch.setattr(settings, "chain_id", "ait-mainnet")

        response = client.post(
            "/staking/stake",
            json={
                "address": "0xstaker",
                "amount": 1000,
                "chain_id": "ait-unsupported",
                "signature": "0xabc",
            },
        )
        assert response.status_code == 400

    def test_unstake_tokens_rejects_unsupported_chain_id(self, client, monkeypatch) -> None:
        """POST /staking/unstake with unsupported chain_id returns 400."""
        monkeypatch.setattr(settings, "supported_chains", "ait-mainnet")
        monkeypatch.setattr(settings, "chain_id", "ait-mainnet")

        response = client.post(
            "/staking/unstake",
            json={
                "address": "0xstaker",
                "stake_id": 1,
                "chain_id": "ait-unsupported",
                "signature": "0xabc",
            },
        )
        assert response.status_code == 400

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
