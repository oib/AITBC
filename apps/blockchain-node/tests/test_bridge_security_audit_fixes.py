"""Regression tests for bridge security audit fixes (Bug #3 and Bug #4).

Bug #3: _verify_proposer_signature must reject signatures from addresses
        not in the validator set when a validator set is registered.

Bug #4: _validate_proof must reject proofs that omit merkle_proof when
        bridge_require_merkle_proof=True, and must log a WARNING (not
        silently skip) when the flag is False.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from eth_keys import keys
from eth_utils import keccak
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.models import Account, BridgeBlockHeader, CrossChainTransfer


# ---------------------------------------------------------------------------
# Helpers (mirrors test_v072_bridge_verification.py patterns)
# ---------------------------------------------------------------------------


def _sign_hash(private_key_hex: str, msg_hash: bytes) -> str:
    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    sig = pk.sign_msg_hash(msg_hash)
    return sig.to_hex()


def _canonical_hash(data: dict[str, Any]) -> bytes:
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return keccak(message)


def _sign_proof(proof_fields: dict[str, Any], private_key_hex: str) -> str:
    msg_hash = _canonical_hash(proof_fields)
    return _sign_hash(private_key_hex, msg_hash)


def _build_proof_fields(
    record: CrossChainTransfer, block_height: int = 10, block_hash: str = "0x" + "ab" * 32
) -> dict[str, Any]:
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
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=address, balance=balance, nonce=0))
        session.commit()


def _register_validators(bridge: CrossChainBridge, chain_id: str, accounts: list[EthAccount], epoch: int = 0) -> None:
    for acct in accounts:
        bridge.register_validator(
            chain_id=chain_id,
            address=acct.address.lower(),
            public_key="0x" + acct.key.hex(),
            epoch=epoch,
        )


def _sign_block_header(proposer: EthAccount, chain_id: str, height: int, block_hash: str, state_root: str) -> str:
    from aitbc.bridge import BridgeBlockHeader as SDKHeader, build_verification_message

    sdk_header = SDKHeader(
        chain_id=chain_id,
        height=height,
        hash=block_hash,
        parent_hash="0x" + "00" * 32,
        proposer=proposer.address.lower(),
        state_root=state_root,
    )
    msg_data = build_verification_message(sdk_header)
    msg_hash = _canonical_hash(msg_data)
    return _sign_hash(proposer.key.hex(), msg_hash)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)


@pytest.fixture
def bridge(engine) -> CrossChainBridge:
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture
def validator_accounts() -> list[EthAccount]:
    return [EthAccount.create() for _ in range(3)]


# ---------------------------------------------------------------------------
# Bug #3: Proposer signature must be in validator set
# ---------------------------------------------------------------------------


class TestBug3ProposerSignatureValidatorSetMembership:
    """Bug #3: _verify_proposer_signature must check validator set membership."""

    def test_non_member_signature_rejected_when_vset_registered(
        self, bridge: CrossChainBridge, engine, validator_accounts: list[EthAccount]
    ) -> None:
        """A proof signed by a non-validator-set member is rejected when a vset exists."""
        _register_validators(bridge, "chain-a", validator_accounts)
        _seed_sender(engine, "chain-a", "0xsender", 100000)

        # Sign the block header with a validator so _verify_block_header_signature passes
        proposer = validator_accounts[0]
        block_hash = "0x" + "ab" * 32
        state_root = "0x" + "cd" * 32
        header_sig = _sign_block_header(proposer, "chain-a", 10, block_hash, state_root)
        _store_block_header(
            engine,
            chain_id="chain-a",
            height=10,
            block_hash=block_hash,
            proposer=proposer.address.lower(),
            state_root=state_root,
            signature=header_sig,
            confirmation_count=10,
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        # Sign the proof with someone NOT in the validator set
        non_member = EthAccount.create()
        proof_fields = _build_proof_fields(record, block_hash=block_hash)
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            non_member.key.hex(),
        )

        with patch("aitbc_chain.config.settings.bridge_multisig_enabled", False):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False, "Proof signed by non-validator-set member must be rejected"

    def test_member_signature_accepted_when_vset_registered(
        self, bridge: CrossChainBridge, engine, validator_accounts: list[EthAccount]
    ) -> None:
        """A proof signed by a validator set member is accepted."""
        _register_validators(bridge, "chain-a", validator_accounts)
        _seed_sender(engine, "chain-a", "0xsender", 100000)

        proposer = validator_accounts[0]
        block_hash = "0x" + "ab" * 32
        state_root = "0x" + "cd" * 32
        header_sig = _sign_block_header(proposer, "chain-a", 10, block_hash, state_root)
        _store_block_header(
            engine,
            chain_id="chain-a",
            height=10,
            block_hash=block_hash,
            proposer=proposer.address.lower(),
            state_root=state_root,
            signature=header_sig,
            confirmation_count=10,
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        # Sign the proof with a validator set member
        proof_fields = _build_proof_fields(record, block_hash=block_hash)
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            proposer.key.hex(),
        )

        with patch("aitbc_chain.config.settings.bridge_multisig_enabled", False):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True, "Proof signed by validator set member must be accepted"

    def test_any_valid_signature_accepted_without_vset(self, bridge: CrossChainBridge, engine) -> None:
        """When no validator set is registered, any valid signature is accepted (dev mode)."""
        _seed_sender(engine, "chain-a", "0xsender", 100000)

        _store_block_header(
            engine,
            chain_id="chain-a",
            height=10,
            proposer="0xproposer",
            state_root="0x" + "cd" * 32,
            signature="",
            confirmation_count=10,
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        # Sign with a random account (no vset registered)
        signer = EthAccount.create()
        proof_fields = _build_proof_fields(record)
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True, "Without vset, any valid signature should be accepted (dev mode)"


# ---------------------------------------------------------------------------
# Bug #4: Merkle proof enforcement when bridge_require_merkle_proof=True
# ---------------------------------------------------------------------------


class TestBug4MerkleProofEnforcement:
    """Bug #4: _validate_proof must enforce Merkle proof when configured."""

    def test_proof_without_merkle_rejected_when_required(self, bridge: CrossChainBridge, engine) -> None:
        """A proof without merkle_proof is rejected when bridge_require_merkle_proof=True."""
        _seed_sender(engine, "chain-a", "0xsender", 100000)

        _store_block_header(
            engine,
            chain_id="chain-a",
            height=10,
            proposer="0xproposer",
            state_root="0x" + "cd" * 32,
            signature="",
            confirmation_count=10,
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        signer = EthAccount.create()
        proof_fields = _build_proof_fields(record)
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )
        # No merkle_proof in proof_fields

        with (
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_require_merkle_proof", True),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is False, "Proof without merkle_proof must be rejected when bridge_require_merkle_proof=True"

    def test_proof_without_merkle_accepted_when_not_required(self, bridge: CrossChainBridge, engine) -> None:
        """A proof without merkle_proof is accepted when bridge_require_merkle_proof=False (default)."""
        _seed_sender(engine, "chain-a", "0xsender", 100000)

        _store_block_header(
            engine,
            chain_id="chain-a",
            height=10,
            proposer="0xproposer",
            state_root="0x" + "cd" * 32,
            signature="",
            confirmation_count=10,
        )

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        signer = EthAccount.create()
        proof_fields = _build_proof_fields(record)
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )
        # No merkle_proof in proof_fields

        with (
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_require_merkle_proof", False),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True, "Proof without merkle_proof should be accepted when bridge_require_merkle_proof=False"

    def test_proof_with_valid_merkle_accepted_when_required(self, bridge: CrossChainBridge, engine) -> None:
        """A proof with a valid merkle_proof is accepted when bridge_require_merkle_proof=True."""
        from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie

        _seed_sender(engine, "chain-a", "0xsender", 100000)

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecip", 5000)
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None

        # Build a trie with the lock event and get the real state root + proof
        lock_key = record.source_tx_hash or "0xlock"
        lock_value = f"lock:{record.transfer_id}:{record.amount}"
        trie = MerklePatriciaTrie()
        trie.put(lock_key.encode(), lock_value.encode())
        state_root = trie.get_root()
        state_root_hex = "0x" + state_root.hex()
        merkle_proof = trie.get_proof(lock_key.encode())

        _store_block_header(
            engine,
            chain_id="chain-a",
            height=10,
            proposer="0xproposer",
            state_root=state_root_hex,
            signature="",
            confirmation_count=10,
        )

        signer = EthAccount.create()
        proof_fields = _build_proof_fields(record)
        proof_fields["state_root"] = state_root_hex
        proof_fields["lock_event"] = lock_value
        proof_fields["merkle_proof"] = [p.hex() for p in merkle_proof]
        proof_fields["proposer_signature"] = _sign_proof(
            {k: v for k, v in proof_fields.items() if k != "proposer_signature"},
            signer.key.hex(),
        )

        with (
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
            patch("aitbc_chain.config.settings.bridge_block_signature_required", False),
            patch("aitbc_chain.config.settings.bridge_require_merkle_proof", True),
        ):
            result = bridge._validate_proof(proof_fields, record)
        assert result is True, "Proof with valid merkle_proof must be accepted when bridge_require_merkle_proof=True"
