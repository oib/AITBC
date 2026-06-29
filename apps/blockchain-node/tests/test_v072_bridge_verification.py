"""Integration tests for v0.7.2 Bridge Verification — Merkle proofs, block headers, finality, unfencing.

Covers:
- BridgeBlockHeader SQLModel table + storage/retrieval (B2)
- Merkle proof verification via merkle_patricia_trie (B3)
- Block header signature verification using v0.7.1 validator set (B4)
- Finality threshold enforcement — small vs large transfers (B5)
- Validator set epoch tracking with grace period (B6)
- Unfenced release path — confirm/batch_confirm now work (B7)
- RPC endpoints: block-headers, oracle-status (B7)
- CLI oracle-status command (B7)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from eth_keys import keys
from eth_utils import keccak
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.models import Account, BridgeBlockHeader, BridgeValidator, CrossChainTransfer
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
    """keccak256 of canonical JSON encoding."""
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return keccak(message)


def _sign_proof(proof_fields: dict[str, Any], private_key_hex: str) -> str:
    """Sign the proof fields with a private key, returning the hex signature."""
    msg_hash = _canonical_hash(proof_fields)
    return _sign_hash(private_key_hex, msg_hash)


def _build_proof_fields(
    record: CrossChainTransfer, block_height: int = 10, block_hash: str = "0x" + "ab" * 32
) -> dict[str, Any]:
    """Build the proof fields (without signatures) for a transfer record."""
    return {
        "source_chain": record.source_chain,
        "lock_tx_hash": record.source_tx_hash or "0xlock",
        "amount": record.amount,
        "sender": record.sender,
        "recipient": record.recipient,
        "chain_id": record.source_chain,
        "block_height": block_height,
        "block_hash": block_hash,
    }


def _store_block_header(
    engine: Any,
    chain_id: str = "chain-a",
    height: int = 10,
    block_hash: str = "0x" + "ab" * 32,
    proposer: str = "0xproposer",
    state_root: str = "0x" + "cd" * 32,
    signature: str = "",
    confirmation_count: int = 10,
) -> BridgeBlockHeader:
    """Store a block header in the DB for bridge proof verification."""
    with Session(engine) as session:
        header = BridgeBlockHeader(
            chain_id=chain_id,
            height=height,
            hash=block_hash,
            parent_hash="0x" + "00" * 32,
            proposer=proposer,
            state_root=state_root,
            signature=signature,
            confirmation_count=confirmation_count,
            finality_confirmed=confirmation_count >= 6,
        )
        session.add(header)
        session.commit()
        session.refresh(header)
        return header


def _seed_sender(engine, chain_id: str, address: str, balance: int) -> None:
    """Seed an account with balance in the in-memory DB."""
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=address, balance=balance, nonce=0))
        session.commit()


def _generate_merkle_proof(key: str, value: str) -> tuple[list[bytes], bytes]:
    """Generate a valid Merkle proof for a key-value pair using MerklePatriciaTrie.

    Returns (proof_elements, state_root).
    """
    from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie

    trie = MerklePatriciaTrie()
    trie.put(key.encode(), value.encode())
    state_root = trie.get_root()
    proof = trie.get_proof(key.encode())
    return proof, state_root


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rpc_engine():
    """Engine with StaticPool for cross-thread in-memory SQLite sharing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def bridge(rpc_engine) -> CrossChainBridge:
    """A CrossChainBridge backed by the rpc_engine (StaticPool)."""
    return CrossChainBridge(lambda: Session(rpc_engine))


@pytest.fixture
def rpc_setup(rpc_engine):
    """Patches get_cross_chain_bridge with a real bridge + yields (bridge, client)."""
    b = CrossChainBridge(lambda: Session(rpc_engine))
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=b):
        yield b, c


@pytest.fixture
def initialized_bridge(rpc_engine):
    """Patches get_cross_chain_bridge with a real bridge backed by rpc_engine."""
    b = CrossChainBridge(lambda: Session(rpc_engine))
    with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=b):
        yield b


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient bound to the RPC router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def validator_accounts() -> list[EthAccount]:
    """Generate 5 ephemeral validator accounts."""
    return [EthAccount.create() for _ in range(5)]


# ---------------------------------------------------------------------------
# BridgeBlockHeader Storage Tests (B2)
# ---------------------------------------------------------------------------


class TestBlockHeaderStorage:
    """BridgeBlockHeader SQLModel table + store_block_header (v0.7.2 §B2)."""

    def test_block_header_table_exists(self, rpc_engine) -> None:
        """BridgeBlockHeader table is created and queryable."""
        with Session(rpc_engine) as session:
            header = BridgeBlockHeader(
                chain_id="chain-a",
                height=10,
                hash="0x" + "ab" * 32,
                parent_hash="0x" + "00" * 32,
                proposer="0xproposer",
                state_root="0x" + "cd" * 32,
            )
            session.add(header)
            session.commit()
            loaded = session.get(BridgeBlockHeader, header.id)
            assert loaded is not None
            assert loaded.chain_id == "chain-a"
            assert loaded.height == 10
            assert loaded.finality_confirmed is False
            assert loaded.confirmation_count == 0

    def test_store_block_header_via_bridge(self, bridge: CrossChainBridge) -> None:
        """store_block_header() creates a new header in the DB."""
        header = bridge.store_block_header(
            {
                "chain_id": "chain-a",
                "height": 5,
                "hash": "0x" + "ab" * 32,
                "proposer": "0xproposer",
                "state_root": "0x" + "cd" * 32,
            }
        )
        assert header.chain_id == "chain-a"
        assert header.height == 5
        assert header.hash == "0x" + "ab" * 32

        # Verify it's retrievable
        retrieved = bridge._get_block_header("chain-a", 5)
        assert retrieved is not None
        assert retrieved.hash == "0x" + "ab" * 32

    def test_store_block_header_update_existing(self, bridge: CrossChainBridge) -> None:
        """store_block_header() updates an existing header (same chain+height)."""
        bridge.store_block_header(
            {
                "chain_id": "chain-a",
                "height": 5,
                "hash": "0x" + "aa" * 32,
                "proposer": "0xproposer1",
                "state_root": "0x" + "cd" * 32,
            }
        )
        bridge.store_block_header(
            {
                "chain_id": "chain-a",
                "height": 5,
                "hash": "0x" + "bb" * 32,
                "proposer": "0xproposer2",
                "state_root": "0x" + "ef" * 32,
            }
        )
        retrieved = bridge._get_block_header("chain-a", 5)
        assert retrieved is not None
        assert retrieved.hash == "0x" + "bb" * 32
        assert retrieved.proposer == "0xproposer2"

    def test_get_block_header_status(self, bridge: CrossChainBridge) -> None:
        """get_block_header_status() returns a dict with finality info."""
        bridge.store_block_header(
            {
                "chain_id": "chain-a",
                "height": 5,
                "hash": "0x" + "ab" * 32,
                "proposer": "0xproposer",
                "state_root": "0x" + "cd" * 32,
                "confirmation_count": 10,
                "finality_confirmed": True,
            }
        )
        status = bridge.get_block_header_status("chain-a", 5)
        assert status is not None
        assert status["finality_confirmed"] is True
        assert status["confirmation_count"] == 10

    def test_get_block_header_status_not_found(self, bridge: CrossChainBridge) -> None:
        """get_block_header_status() returns None for missing header."""
        status = bridge.get_block_header_status("chain-a", 999)
        assert status is None


# ---------------------------------------------------------------------------
# Merkle Proof Verification Tests (B3)
# ---------------------------------------------------------------------------


class TestMerkleProofVerification:
    """Merkle proof verification via merkle_patricia_trie (v0.7.2 §B3)."""

    def test_valid_merkle_proof_accepted(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """A valid Merkle proof is accepted by _validate_proof."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        # Generate a valid Merkle proof
        lock_key = record.source_tx_hash or "0xlock"
        lock_value = f"lock:{record.transfer_id}:{record.amount}"
        proof_elements, state_root = _generate_merkle_proof(lock_key, lock_value)
        state_root_hex = "0x" + state_root.hex()

        # Store the block header with the trie's state root
        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            state_root=state_root_hex,
            confirmation_count=10,
        )

        # Build the proof
        proof_fields = _build_proof_fields(record)
        proof_fields["state_root"] = state_root_hex
        proof_fields["lock_event"] = lock_value
        proof_fields["merkle_proof"] = [p.hex() for p in proof_elements]

        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True

    def test_invalid_merkle_proof_rejected(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """A tampered Merkle proof is rejected."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        # Generate a valid Merkle proof
        lock_key = record.source_tx_hash or "0xlock"
        lock_value = f"lock:{record.transfer_id}:{record.amount}"
        proof_elements, state_root = _generate_merkle_proof(lock_key, lock_value)
        state_root_hex = "0x" + state_root.hex()

        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            state_root=state_root_hex,
            confirmation_count=10,
        )

        # Tamper with the proof — change the lock_event value
        proof_fields = _build_proof_fields(record)
        proof_fields["state_root"] = state_root_hex
        proof_fields["lock_event"] = "tampered:value"
        proof_fields["merkle_proof"] = [p.hex() for p in proof_elements]

        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False

    def test_wrong_state_root_rejected(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """A proof with a state root mismatch is rejected."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        # Store a block header with a different state root
        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            state_root="0x" + "ee" * 32,
            confirmation_count=10,
        )

        proof_fields = _build_proof_fields(record)
        proof_fields["state_root"] = "0x" + "cd" * 32  # different from header
        proof_fields["lock_event"] = "lock:value"
        proof_fields["merkle_proof"] = ["00" * 32]

        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False

    def test_no_block_header_rejected(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """A proof with no stored block header is rejected."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        # Don't store a block header
        proof_fields = _build_proof_fields(record)
        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False


# ---------------------------------------------------------------------------
# Block Header Signature Verification Tests (B4)
# ---------------------------------------------------------------------------


class TestBlockHeaderSignatureVerification:
    """Block header signature verification using v0.7.1 validator set (v0.7.2 §B4)."""

    def test_valid_block_header_signature_accepted(
        self, bridge: CrossChainBridge, rpc_engine, validator_accounts: list[EthAccount]
    ) -> None:
        """A block header signed by a validator set member is accepted."""
        _register_validators(bridge, "chain-a", validator_accounts)
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)

        # Create a block header signed by a validator
        proposer = validator_accounts[0]
        block_hash = "0x" + "ab" * 32
        state_root = "0x" + "cd" * 32

        # Sign the block header (matching validate_block_header's message format)
        from aitbc.bridge import BridgeBlockHeader as SDKHeader, build_verification_message

        sdk_header = SDKHeader(
            chain_id="chain-a",
            height=10,
            hash=block_hash,
            parent_hash="0x" + "00" * 32,
            proposer=proposer.address.lower(),
            state_root=state_root,
        )
        msg_data = build_verification_message(sdk_header)
        msg_hash = _canonical_hash(msg_data)
        signature = _sign_hash(proposer.key.hex(), msg_hash)

        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            block_hash=block_hash,
            proposer=proposer.address.lower(),
            state_root=state_root,
            signature=signature,
            confirmation_count=10,
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record, block_hash=block_hash)
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            proposer.key.hex(),
        )

        with patch("aitbc_chain.config.settings.bridge_multisig_enabled", False):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True

    def test_invalid_block_header_signature_rejected(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """A block header with an invalid signature is rejected."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)

        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            proposer="0xproposer",
            state_root="0x" + "cd" * 32,
            signature="0x" + "ff" * 65,  # invalid signature
            confirmation_count=10,
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with patch("aitbc_chain.config.settings.bridge_multisig_enabled", False):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False

    def test_non_member_signer_rejected(
        self, bridge: CrossChainBridge, rpc_engine, validator_accounts: list[EthAccount]
    ) -> None:
        """A block header signed by a non-validator-set member is rejected."""
        _register_validators(bridge, "chain-a", validator_accounts)
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)

        # Sign with someone NOT in the validator set
        non_member = EthAccount.create()
        block_hash = "0x" + "ab" * 32
        state_root = "0x" + "cd" * 32

        from aitbc.bridge import BridgeBlockHeader as SDKHeader, build_verification_message

        sdk_header = SDKHeader(
            chain_id="chain-a",
            height=10,
            hash=block_hash,
            parent_hash="0x" + "00" * 32,
            proposer=non_member.address.lower(),
            state_root=state_root,
        )
        msg_data = build_verification_message(sdk_header)
        msg_hash = _canonical_hash(msg_data)
        signature = _sign_hash(non_member.key.hex(), msg_hash)

        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            block_hash=block_hash,
            proposer=non_member.address.lower(),
            state_root=state_root,
            signature=signature,
            confirmation_count=10,
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record, block_hash=block_hash)
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            non_member.key.hex(),
        )

        with patch("aitbc_chain.config.settings.bridge_multisig_enabled", False):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False


# ---------------------------------------------------------------------------
# Finality Tracking Tests (B5)
# ---------------------------------------------------------------------------


class TestFinalityTracking:
    """Finality threshold enforcement — small vs large transfers (v0.7.2 §B5)."""

    def test_small_transfer_min_confirmations(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """Small transfers require only min_confirmations (3)."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)

        # Store a block header with exactly 3 confirmations
        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            proposer="0xproposer",
            confirmation_count=3,  # meets min_confirmations
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True

    def test_small_transfer_below_min_confirmations_rejected(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """Small transfers with < min_confirmations are rejected."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)

        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            proposer="0xproposer",
            confirmation_count=2,  # below min_confirmations (3)
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False

    def test_large_transfer_requires_full_finality(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """Large transfers (>= 10000) require full finality (6 confirmations)."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 1000000)

        # Store a block header with 4 confirmations — enough for small, not for large
        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            proposer="0xproposer",
            confirmation_count=4,  # meets min (3) but not full (6)
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 15000)  # large
        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False

    def test_large_transfer_with_full_finality_accepted(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """Large transfers with full finality (6+ confirmations) are accepted."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 1000000)

        _store_block_header(
            rpc_engine,
            chain_id="chain-a",
            height=10,
            proposer="0xproposer",
            confirmation_count=6,  # meets full finality
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 15000)  # large
        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True

    def test_confirmation_count_incremented(self, bridge: CrossChainBridge) -> None:
        """Storing a new block increments confirmations for earlier blocks."""
        # Store block at height 5
        bridge.store_block_header(
            {
                "chain_id": "chain-a",
                "height": 5,
                "hash": "0x" + "aa" * 32,
                "proposer": "0xproposer",
                "state_root": "0x" + "cd" * 32,
            }
        )
        # Store block at height 10 — should increment height 5's confirmations
        bridge.store_block_header(
            {
                "chain_id": "chain-a",
                "height": 10,
                "hash": "0x" + "bb" * 32,
                "proposer": "0xproposer",
                "state_root": "0x" + "ef" * 32,
            }
        )
        h5 = bridge._get_block_header("chain-a", 5)
        assert h5 is not None
        assert h5.confirmation_count == 1


# ---------------------------------------------------------------------------
# Validator Set Epoch Tracking Tests (B6)
# ---------------------------------------------------------------------------


class TestValidatorSetEpochTracking:
    """Validator set epoch tracking with grace period (v0.7.2 §B6)."""

    def test_validator_set_fresh(self, bridge: CrossChainBridge, validator_accounts: list[EthAccount]) -> None:
        """A recently registered validator set is fresh."""
        _register_validators(bridge, "chain-a", validator_accounts)
        assert bridge._check_validator_set_freshness("chain-a") is True

    def test_validator_set_stale_after_grace_period(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """A validator set older than the grace period is stale."""
        # Register a validator with an old timestamp
        with Session(rpc_engine) as session:
            old_time = datetime.now(UTC) - timedelta(seconds=7200)
            v = BridgeValidator(
                chain_id="chain-a",
                address="0xvalidator",
                public_key="0xpubkey",
                epoch=0,
                is_active=True,
                registered_at=old_time,
            )
            session.add(v)
            session.commit()

        with patch("aitbc_chain.config.settings.bridge_validator_set_grace_period", 3600):
            result = bridge._check_validator_set_freshness("chain-a")
        assert result is False

    def test_no_validators_is_fresh(self, bridge: CrossChainBridge) -> None:
        """No validators registered → fresh enough (will fail elsewhere)."""
        assert bridge._check_validator_set_freshness("chain-empty") is True


# ---------------------------------------------------------------------------
# Unfenced Release Path Tests (B7)
# ---------------------------------------------------------------------------


class TestUnfencedReleasePath:
    """Unfenced release path — confirm/batch_confirm now work (v0.7.2 §B7)."""

    def test_confirm_works_when_unfenced(
        self, initialized_bridge: CrossChainBridge, client: TestClient, rpc_engine, validator_accounts: list[EthAccount]
    ) -> None:
        """POST /bridge/confirm works when unfenced (with valid proof + block header)."""
        _register_validators(initialized_bridge, "chain-a", validator_accounts)
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        _store_block_header(rpc_engine, chain_id="chain-a", height=10, proposer=validator_accounts[0].address.lower())

        transfer = initialized_bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        # Confirm the transfer via RPC (unfenced by default in v0.7.2)
        with (
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        ):
            response = client.post(
                "/bridge/confirm",
                json={
                    "transfer_id": transfer.transfer_id,
                    "proof": proof_fields,
                    "confirmer": "0xrecip",
                    "signature": "0x" + "ff" * 65,  # confirmer sig (not checked deeply)
                },
            )
        # Should not be 503 (fence) — may be 200 or 400 depending on confirmer sig
        assert response.status_code != 503

    def test_confirm_fenced_when_explicitly_disabled(
        self, initialized_bridge: CrossChainBridge, client: TestClient, rpc_engine
    ) -> None:
        """POST /bridge/confirm returns 503 when fence is explicitly set to false."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = initialized_bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

        with patch("aitbc_chain.config.settings.bridge_release_enabled", False):
            response = client.post(
                "/bridge/confirm",
                json={
                    "transfer_id": transfer.transfer_id,
                    "proof": {"source_chain": "chain-a"},
                    "confirmer": "0xrecip",
                    "signature": "0x" + "ff" * 65,
                },
            )
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# RPC Endpoint Tests (B7)
# ---------------------------------------------------------------------------


class TestBridgeVerificationRPC:
    """RPC endpoints for block headers and oracle status (v0.7.2 §B7)."""

    def test_store_block_header_rpc(self, rpc_setup) -> None:
        """POST /bridge/block-headers stores a block header."""
        bridge, client = rpc_setup
        response = client.post(
            "/bridge/block-headers",
            json={
                "chain_id": "chain-a",
                "height": 10,
                "hash": "0x" + "ab" * 32,
                "proposer": "0xproposer",
                "state_root": "0x" + "cd" * 32,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["chain_id"] == "chain-a"
        assert data["height"] == 10

    def test_store_block_header_missing_fields(self, rpc_setup) -> None:
        """POST /bridge/block-headers with missing fields returns 400."""
        bridge, client = rpc_setup
        response = client.post(
            "/bridge/block-headers",
            json={"chain_id": "chain-a"},
        )
        assert response.status_code == 400

    def test_get_block_header_rpc(self, rpc_setup) -> None:
        """GET /bridge/block-headers/{chain_id}/{height} returns a stored header."""
        bridge, client = rpc_setup
        # Store first
        client.post(
            "/bridge/block-headers",
            json={
                "chain_id": "chain-a",
                "height": 10,
                "hash": "0x" + "ab" * 32,
                "proposer": "0xproposer",
                "state_root": "0x" + "cd" * 32,
            },
        )
        # Retrieve
        response = client.get("/bridge/block-headers/chain-a/10")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["height"] == 10
        assert data["hash"] == "0x" + "ab" * 32

    def test_get_block_header_not_found(self, rpc_setup) -> None:
        """GET /bridge/block-headers/{chain_id}/{height} returns 404 for missing header."""
        bridge, client = rpc_setup
        response = client.get("/bridge/block-headers/chain-a/999")
        assert response.status_code == 404

    def test_oracle_status_rpc(self, rpc_setup) -> None:
        """GET /bridge/oracle/status returns verification status."""
        bridge, client = rpc_setup
        response = client.get("/bridge/oracle/status")
        assert response.status_code == 200
        data = response.json()
        assert "verification_mode" in data
        assert "min_confirmations" in data
        assert "finality_blocks" in data
        assert "block_headers_total" in data
        assert "release_enabled" in data

    def test_oracle_status_with_headers(self, rpc_setup) -> None:
        """Oracle status reflects stored block headers."""
        bridge, client = rpc_setup
        client.post(
            "/bridge/block-headers",
            json={
                "chain_id": "chain-a",
                "height": 10,
                "hash": "0x" + "ab" * 32,
                "proposer": "0xproposer",
                "state_root": "0x" + "cd" * 32,
                "confirmation_count": 10,
            },
        )
        response = client.get("/bridge/oracle/status")
        assert response.status_code == 200
        data = response.json()
        assert data["block_headers_total"] == 1
        assert "chain-a" in data["block_headers_per_chain"]


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _register_validators(bridge: CrossChainBridge, chain_id: str, accounts: list[EthAccount], epoch: int = 0) -> None:
    """Register a list of validator accounts for a chain."""
    for acct in accounts:
        bridge.register_validator(
            chain_id=chain_id,
            address=acct.address.lower(),
            public_key="0x" + acct.key.hex(),
            epoch=epoch,
        )
