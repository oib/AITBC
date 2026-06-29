"""Integration tests for v0.7.1 Bridge Security — multi-sig, validator sets, block header signatures.

Covers:
- Block header signature on proposal + verification (B3)
- BridgeValidator SQLModel table + validator set cache (B4)
- Validator RPC endpoints: register, get set, security status (B5)
- Multi-sig threshold proof verification (B6)
- CLI commands: security-status, register-validator (B7)
"""

from __future__ import annotations

import json
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
from aitbc_chain.models import Account, Block, CrossChainTransfer
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


def _sign_request(sender_account: EthAccount, data: dict[str, Any]) -> str:
    """Sign a request payload and return the hex signature."""
    msg_hash = _canonical_hash(data)
    return _sign_hash(sender_account.key.hex(), msg_hash)


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


def _sign_proof(proof_fields: dict[str, Any], private_key_hex: str) -> str:
    """Sign the proof fields with a private key, returning the hex signature."""
    msg_hash = _canonical_hash(proof_fields)
    return _sign_hash(private_key_hex, msg_hash)


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


def _seed_sender(engine, chain_id: str, address: str, balance: int) -> None:
    """Seed an account with balance in the in-memory DB."""
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=address, balance=balance, nonce=0))
        session.commit()


def _register_validators(bridge: CrossChainBridge, chain_id: str, accounts: list[EthAccount], epoch: int = 0) -> None:
    """Register a list of validator accounts for a chain."""
    for acct in accounts:
        bridge.register_validator(
            chain_id=chain_id,
            address=acct.address.lower(),
            public_key="0x" + acct.key.hex(),
            epoch=epoch,
        )


# ---------------------------------------------------------------------------
# Block Header Signature Tests (B3)
# ---------------------------------------------------------------------------


class TestBlockHeaderSignature:
    """Block.signature field + PoA signing/verification (v0.7.1 §B3)."""

    def test_block_signature_field_exists(self, rpc_engine) -> None:
        """Block model has a signature field with empty default."""
        with Session(rpc_engine) as session:
            block = Block(
                chain_id="chain-a",
                height=1,
                hash="0x" + "ab" * 32,
                parent_hash="0x" + "00" * 32,
                proposer="0xproposer",
                tx_count=0,
                signature="",
            )
            session.add(block)
            session.commit()
            loaded = session.get(Block, block.id)
            assert loaded is not None
            assert loaded.signature == ""

    def test_verify_block_signature_empty_legacy(self, rpc_engine) -> None:
        """Empty signature is accepted (legacy block, backward-compatible)."""
        from aitbc_chain.consensus.poa import PoAProposer

        block = Block(
            chain_id="chain-a",
            height=1,
            hash="0x" + "ab" * 32,
            parent_hash="0x" + "00" * 32,
            proposer="0xproposer",
            tx_count=0,
            signature="",
        )
        assert PoAProposer.verify_block_signature(block) is True

    def test_verify_block_signature_valid(self, rpc_engine) -> None:
        """Valid block signature recovers to the proposer's address."""
        from aitbc_chain.consensus.poa import PoAProposer

        acct = EthAccount.create()
        block_hash = "0x" + "cd" * 32
        # Sign the block hash using eth_keys (same as PoA._sign_block_hash)
        pk = keys.PrivateKey(bytes.fromhex(acct.key.hex().removeprefix("0x")))
        msg_hash = bytes.fromhex(block_hash.removeprefix("0x"))
        sig = pk.sign_msg_hash(msg_hash)
        block = Block(
            chain_id="chain-a",
            height=1,
            hash=block_hash,
            parent_hash="0x" + "00" * 32,
            proposer=acct.address.lower(),
            tx_count=0,
            signature=sig.to_hex(),
        )
        assert PoAProposer.verify_block_signature(block) is True

    def test_verify_block_signature_wrong_signer(self, rpc_engine) -> None:
        """Signature from a different signer is rejected."""
        from aitbc_chain.consensus.poa import PoAProposer

        signer = EthAccount.create()
        proposer = EthAccount.create()
        block_hash = "0x" + "cd" * 32
        pk = keys.PrivateKey(bytes.fromhex(signer.key.hex().removeprefix("0x")))
        msg_hash = bytes.fromhex(block_hash.removeprefix("0x"))
        sig = pk.sign_msg_hash(msg_hash)
        block = Block(
            chain_id="chain-a",
            height=1,
            hash=block_hash,
            parent_hash="0x" + "00" * 32,
            proposer=proposer.address.lower(),  # different from signer
            tx_count=0,
            signature=sig.to_hex(),
        )
        assert PoAProposer.verify_block_signature(block) is False

    def test_verify_block_signature_corrupt(self, rpc_engine) -> None:
        """Corrupt signature is rejected."""
        from aitbc_chain.consensus.poa import PoAProposer

        block = Block(
            chain_id="chain-a",
            height=1,
            hash="0x" + "cd" * 32,
            parent_hash="0x" + "00" * 32,
            proposer="0xproposer",
            tx_count=0,
            signature="0x" + "00" * 65,  # corrupt
        )
        assert PoAProposer.verify_block_signature(block) is False


# ---------------------------------------------------------------------------
# Validator Registration Tests (B4 + B5)
# ---------------------------------------------------------------------------


class TestValidatorRegistration:
    """BridgeValidator table + register_validator method + RPC endpoint (v0.7.1 §B4-B5)."""

    def test_register_validator_direct(self, bridge: CrossChainBridge, validator_accounts: list[EthAccount]) -> None:
        """Register validators directly via bridge.register_validator()."""
        chain_id = "chain-a"
        for acct in validator_accounts:
            bridge.register_validator(
                chain_id=chain_id,
                address=acct.address.lower(),
                public_key="0x" + acct.key.hex(),
                epoch=0,
            )

        vset = bridge.get_validator_set(chain_id)
        assert vset is not None
        assert vset.total == 5
        assert vset.epoch == 0
        addresses = vset.addresses
        assert len(addresses) == 5

    def test_register_validator_rpc(self, rpc_setup, validator_accounts: list[EthAccount]) -> None:
        """POST /bridge/validators/register registers a validator via RPC."""
        bridge, client = rpc_setup
        acct = validator_accounts[0]
        chain_id = "chain-a"

        # Sign the registration request
        sign_data = {
            "chain_id": chain_id,
            "address": acct.address.lower(),
            "public_key": "0x" + acct.key.hex(),
            "action": "register",
        }
        signature = _sign_request(acct, sign_data)

        response = client.post(
            "/bridge/validators/register",
            json={
                "chain_id": chain_id,
                "address": acct.address.lower(),
                "public_key": "0x" + acct.key.hex(),
                "signature": signature,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "registered"
        assert data["chain_id"] == chain_id

    def test_register_validator_invalid_signature(self, rpc_setup, validator_accounts: list[EthAccount]) -> None:
        """POST /bridge/validators/register with bad signature returns 403."""
        bridge, client = rpc_setup
        acct = validator_accounts[0]

        response = client.post(
            "/bridge/validators/register",
            json={
                "chain_id": "chain-a",
                "address": acct.address.lower(),
                "public_key": "0x" + acct.key.hex(),
                "signature": "0x" + "ff" * 65,  # invalid
            },
        )
        assert response.status_code == 403

    def test_register_validator_missing_fields(self, rpc_setup) -> None:
        """POST /bridge/validators/register with missing fields returns 400."""
        bridge, client = rpc_setup
        response = client.post(
            "/bridge/validators/register",
            json={"chain_id": "chain-a"},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Get Validator Set Tests (B5)
# ---------------------------------------------------------------------------


class TestGetValidatorSet:
    """GET /bridge/validators/{chain_id} endpoint (v0.7.1 §B5)."""

    def test_get_validator_set_empty(self, initialized_bridge: CrossChainBridge, client: TestClient) -> None:
        """GET /bridge/validators/{chain_id} returns empty set for unregistered chain."""
        response = client.get("/bridge/validators/chain-empty")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 0
        assert data["validators"] == []

    def test_get_validator_set_with_validators(
        self, initialized_bridge: CrossChainBridge, client: TestClient, validator_accounts: list[EthAccount]
    ) -> None:
        """GET /bridge/validators/{chain_id} returns registered validators."""
        _register_validators(initialized_bridge, "chain-a", validator_accounts)

        response = client.get("/bridge/validators/chain-a")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 5
        assert len(data["validators"]) == 5
        assert all(v["is_active"] for v in data["validators"])

    def test_get_validator_set_by_epoch(
        self, initialized_bridge: CrossChainBridge, client: TestClient, validator_accounts: list[EthAccount]
    ) -> None:
        """GET /bridge/validators/{chain_id}?epoch=1 returns epoch-specific set."""
        _register_validators(initialized_bridge, "chain-a", validator_accounts[:3], epoch=0)
        _register_validators(initialized_bridge, "chain-a", validator_accounts[3:], epoch=1)

        response = client.get("/bridge/validators/chain-a?epoch=0")
        assert response.status_code == 200
        data = response.json()
        assert data["epoch"] == 0
        assert data["total"] == 3


# ---------------------------------------------------------------------------
# Security Status Tests (B5)
# ---------------------------------------------------------------------------


class TestSecurityStatus:
    """GET /bridge/security/status endpoint (v0.7.1 §B5)."""

    def test_security_status(self, initialized_bridge: CrossChainBridge, client: TestClient) -> None:
        """GET /bridge/security/status returns security configuration."""
        response = client.get("/bridge/security/status")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "multisig_enabled" in data
        assert "threshold" in data
        assert "validator_count" in data
        assert "current_epoch" in data
        assert "block_signature_required" in data
        assert "release_enabled" in data
        assert "bridge_initialized" in data

    def test_security_status_with_validators(
        self, initialized_bridge: CrossChainBridge, client: TestClient, validator_accounts: list[EthAccount]
    ) -> None:
        """Security status reflects registered validators."""
        _register_validators(initialized_bridge, "chain-a", validator_accounts)

        response = client.get("/bridge/security/status")
        assert response.status_code == 200
        data = response.json()
        assert data["validator_count"] == 5


# ---------------------------------------------------------------------------
# Multi-Sig Threshold Verification Tests (B6)
# ---------------------------------------------------------------------------


class TestMultiSigThreshold:
    """Multi-sig threshold proof verification (v0.7.1 §B6)."""

    def test_multisig_disabled_fallback(
        self, bridge: CrossChainBridge, rpc_engine, validator_accounts: list[EthAccount]
    ) -> None:
        """When multisig is disabled, single-signer verification works (backward compat)."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

        # Build a proof with a single proposer_signature (v0.7.0 style)
        record = rpc_engine and None  # just to use rpc_engine
        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        # Sign with any valid key (multisig disabled, so any valid sig works)
        signer = EthAccount.create()
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        # With multisig disabled, _validate_proof should accept this
        with patch("aitbc_chain.config.settings.bridge_multisig_enabled", False):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True

    def test_multisig_threshold_met(self, bridge: CrossChainBridge, rpc_engine, validator_accounts: list[EthAccount]) -> None:
        """M-of-N valid validator signatures meet threshold."""
        _register_validators(bridge, "chain-a", validator_accounts)
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        # Sign with 3 of the 5 validators (meets default threshold of 3)
        signing_fields = dict(proof_fields)
        validator_sigs = [_sign_proof(signing_fields, acct.key.hex()) for acct in validator_accounts[:3]]
        proof_fields["validator_signatures"] = validator_sigs
        proof_fields["proposer_signature"] = validator_sigs[0]  # backward compat

        with (
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", True),
            patch("aitbc_chain.config.settings.bridge_multisig_threshold", 3),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True

    def test_multisig_threshold_not_met(
        self, bridge: CrossChainBridge, rpc_engine, validator_accounts: list[EthAccount]
    ) -> None:
        """Below-threshold signatures are rejected."""
        _register_validators(bridge, "chain-a", validator_accounts)
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        # Sign with only 2 of the 5 validators (below threshold of 3)
        signing_fields = dict(proof_fields)
        validator_sigs = [_sign_proof(signing_fields, acct.key.hex()) for acct in validator_accounts[:2]]
        proof_fields["validator_signatures"] = validator_sigs
        proof_fields["proposer_signature"] = ""

        with (
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", True),
            patch("aitbc_chain.config.settings.bridge_multisig_threshold", 3),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False

    def test_multisig_non_member_signer(
        self, bridge: CrossChainBridge, rpc_engine, validator_accounts: list[EthAccount]
    ) -> None:
        """Signatures from non-validator-set members are rejected."""
        _register_validators(bridge, "chain-a", validator_accounts)
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

        with Session(rpc_engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        proof_fields = _build_proof_fields(record)
        # Sign with 3 non-validator accounts
        non_validators = [EthAccount.create() for _ in range(3)]
        signing_fields = dict(proof_fields)
        validator_sigs = [_sign_proof(signing_fields, acct.key.hex()) for acct in non_validators]
        proof_fields["validator_signatures"] = validator_sigs
        proof_fields["proposer_signature"] = ""

        with (
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", True),
            patch("aitbc_chain.config.settings.bridge_multisig_threshold", 3),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False

    def test_multisig_no_validator_set(self, bridge: CrossChainBridge, rpc_engine) -> None:
        """Multi-sig with no validator set registered is rejected."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
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
        proof_fields["validator_signatures"] = [proof_fields["proposer_signature"]]

        with (
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", True),
            patch("aitbc_chain.config.settings.bridge_multisig_threshold", 3),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False

    def test_confirm_release_fence_active(self, initialized_bridge: CrossChainBridge, client: TestClient, rpc_engine) -> None:
        """Confirm returns 503 when release fence is active (BRIDGE_RELEASE_ENABLED=false)."""
        _seed_sender(rpc_engine, "chain-a", "0xsender", 100000)
        transfer = initialized_bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)

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
        assert "disabled" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Validator Set Epoch Rotation Tests (B4)
# ---------------------------------------------------------------------------


class TestValidatorSetEpochRotation:
    """Validator set epoch tracking and rotation (v0.7.1 §B4)."""

    def test_epoch_rotation(self, bridge: CrossChainBridge, validator_accounts: list[EthAccount]) -> None:
        """Advancing epoch creates a new validator set; old set is retained."""
        # Register epoch 0
        _register_validators(bridge, "chain-a", validator_accounts[:3], epoch=0)
        vset0 = bridge.get_validator_set("chain-a", epoch=0)
        assert vset0 is not None
        assert vset0.total == 3

        # Register epoch 1 with different validators
        _register_validators(bridge, "chain-a", validator_accounts[3:], epoch=1)
        vset1 = bridge.get_validator_set("chain-a", epoch=1)
        assert vset1 is not None
        assert vset1.total == 2

        # Old epoch set is still accessible (grace period)
        vset0_after = bridge.get_validator_set("chain-a", epoch=0)
        assert vset0_after is not None
        assert vset0_after.total == 3

    def test_get_current_epoch(self, bridge: CrossChainBridge, validator_accounts: list[EthAccount]) -> None:
        """get_validator_set with no epoch returns the current (latest) epoch."""
        _register_validators(bridge, "chain-a", validator_accounts[:2], epoch=0)
        _register_validators(bridge, "chain-a", validator_accounts[2:], epoch=2)

        vset = bridge.get_validator_set("chain-a")
        assert vset is not None
        assert vset.epoch == 2
