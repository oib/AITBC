"""Issue #670: build_proof must not copy sealed metadata attestations verbatim.

The consensus attestation gate seals blocks with ``attestations=[]`` whenever
the PBFT commit certificate covers ``effective_min``. A proof built verbatim
from such a block carries only the proposer signature and fails the bc-2-side
``_verify_threshold_signatures`` check ("Threshold not met 1/2"), so the
release stalls pending forever.

``build_proof`` now tops ``validator_signatures`` up to the configured
``bridge_multisig_threshold`` with fresh signatures over the sealed block's
canonical header message — the exact shape ``build_verification_message``
rebuilds on the verify side — sourced from (a) the node's own
``VALIDATOR_KEYS`` and (b) a best-effort remote attestation round.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.bridge import build_verification_message, check_threshold, recover_all_signers
from aitbc.bridge.types import BridgeBlockHeader as VerificationHeader
from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.cross_chain.bridge_leaf import lock_leaf_value
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Block, CrossChainTransfer, Transaction
from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie

SOURCE = "chain-a"
TARGET = "chain-b"
SENDER = "0x" + "11" * 20
RECIPIENT = "0x" + "22" * 20
HEIGHT = 7
THRESHOLD = 2


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    chain_metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def bridge(engine) -> CrossChainBridge:
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture
def proposer() -> EthAccount:
    return EthAccount.create()


@pytest.fixture
def validator_b() -> EthAccount:
    return EthAccount.create()


@pytest.fixture(autouse=True)
def _settings():
    with (
        patch("aitbc_chain.config.settings.supported_chains", f"{SOURCE},{TARGET}"),
        patch("aitbc_chain.config.settings.chain_id", SOURCE),
        patch("aitbc_chain.config.settings.block_scoped_preregistered_transactions", False),
        patch("aitbc_chain.config.settings.bridge_release_enabled", False),
        patch("aitbc_chain.config.settings.bridge_multisig_enabled", True),
        patch("aitbc_chain.config.settings.bridge_multisig_threshold", THRESHOLD),
        patch("aitbc_chain.config.settings.bridge_block_signature_required", True),
        patch("aitbc_chain.config.settings.bridge_lock_leaf_v2_height", None),
        patch("aitbc_chain.config.settings.validator_keys", ""),
        patch("aitbc_chain.config.settings.validator_set", ""),
        patch("aitbc_chain.config.settings.bridge_proof_attestation_timeout_seconds", 0.1),
    ):
        yield


def _lock(bridge: CrossChainBridge, engine: Any, amount: int = 1_000) -> str:
    with Session(engine) as session:
        if session.get(Account, (SOURCE, SENDER)) is None:
            session.add(Account(chain_id=SOURCE, address=SENDER, balance=10_000_000, nonce=0))
            session.commit()
    return bridge.initiate_transfer(SOURCE, TARGET, SENDER, RECIPIENT, amount).transfer_id


def _seal(
    bridge: CrossChainBridge,
    engine: Any,
    proposer: EthAccount,
    transfer_ids: list[str],
    attestations: list[dict[str, str]] | None,
) -> Block:
    """Seal the locks into one signed source block with the given metadata attestation set."""
    with Session(engine) as session:
        trie = MerklePatriciaTrie()
        locks = []
        for tid in transfer_ids:
            record = session.get(CrossChainTransfer, tid)
            assert record is not None
            leaf = lock_leaf_value(record.transfer_id, record.amount, record.target_chain, record.recipient, HEIGHT)
            trie.put(tid.encode(), leaf.encode())
            locks.append(
                session.exec(select(Transaction).where(Transaction.chain_id == SOURCE, Transaction.tx_hash == tid)).one()
            )
        bridge_state_root = "0x" + trie.get_root().hex()
        block = Block(
            chain_id=SOURCE,
            height=HEIGHT,
            hash="0x" + hashlib.sha256(f"{SOURCE}|{HEIGHT}|{bridge_state_root}".encode()).hexdigest(),
            parent_hash="0x" + "00" * 32,
            proposer=proposer.address.lower(),
            timestamp=datetime.now(UTC),
            tx_count=len(locks),
            state_root="0x" + "00" * 32,
            bridge_state_root=bridge_state_root,
            signature="",
            block_metadata=json.dumps({"attestations": attestations}) if attestations is not None else None,
        )
        block.signature = sign_block_hash_local(block, proposer.key.hex())
        for tx in locks:
            tx.block_height = HEIGHT
            session.add(tx)
        session.add(block)
        session.commit()
        session.refresh(block)
    bridge.store_block_header(
        {
            "chain_id": SOURCE,
            "height": block.height,
            "hash": block.hash,
            "parent_hash": block.parent_hash,
            "proposer": block.proposer,
            "state_root": block.state_root or "",
            "bridge_state_root": block.bridge_state_root or "",
            "signature": block.signature,
            "confirmation_count": 10,
            "finality_confirmed": True,
        }
    )
    return block


def sign_block_hash_local(block: Block, private_key: str) -> str:
    """Sign the canonical header message — same as poa._block_header_message."""
    message = build_verification_message(
        VerificationHeader(
            chain_id=block.chain_id,
            height=block.height,
            hash=block.hash,
            parent_hash=block.parent_hash,
            proposer=block.proposer,
            state_root=block.state_root or "",
            bridge_state_root=block.bridge_state_root or "",
        )
    )
    return sign_consensus_message(message, private_key)


def _header_message(block: Block) -> dict[str, Any]:
    return build_verification_message(
        VerificationHeader(
            chain_id=block.chain_id,
            height=block.height,
            hash=block.hash,
            parent_hash=block.parent_hash,
            proposer=block.proposer,
            state_root=block.state_root or "",
            bridge_state_root=block.bridge_state_root or "",
        )
    )


def _proof_signers(bridge: CrossChainBridge, block: Block, proof: dict[str, Any]) -> list[str]:
    vset = bridge.get_validator_set(SOURCE)
    assert vset is not None
    all_sigs = list(proof["validator_signatures"]) + [proof["proposer_signature"]]
    return recover_all_signers(_header_message(block), all_sigs)


class TestLocalKeyAugmentation:
    """Block sealed with attestations=[] — the node holds the second validator's key."""

    def test_empty_attestations_topped_up_by_local_key(
        self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount, validator_b: EthAccount
    ) -> None:
        bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
        bridge.register_validator(SOURCE, validator_b.address.lower(), "0x", 0)
        tid = _lock(bridge, engine)
        block = _seal(bridge, engine, proposer, [tid], attestations=[])
        with patch(
            "aitbc_chain.config.settings.validator_keys",
            json.dumps({validator_b.address: validator_b.key.hex()}),
        ):
            proof = bridge.build_proof(tid, source_chain=SOURCE)
        signers = {s.lower() for s in _proof_signers(bridge, block, proof)}
        assert proposer.address.lower() in signers
        assert validator_b.address.lower() in signers
        vset = bridge.get_validator_set(SOURCE)
        assert vset is not None
        meets, count, _ = check_threshold(list(signers), vset, THRESHOLD)
        assert meets and count == THRESHOLD

    def test_augmented_proof_passes_header_threshold_verification(
        self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount, validator_b: EthAccount
    ) -> None:
        bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
        bridge.register_validator(SOURCE, validator_b.address.lower(), "0x", 0)
        tid = _lock(bridge, engine)
        _seal(bridge, engine, proposer, [tid], attestations=[])
        with patch(
            "aitbc_chain.config.settings.validator_keys",
            json.dumps({validator_b.address: validator_b.key.hex()}),
        ):
            proof = bridge.build_proof(tid, source_chain=SOURCE)
        header = bridge._get_block_header(SOURCE, HEIGHT)
        assert header is not None
        assert bridge._verify_threshold_signatures(proof, header=header)

    def test_below_threshold_without_augmentation_still_fails(
        self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount, validator_b: EthAccount
    ) -> None:
        """Baseline: the verbatim-copy behaviour really is the defect."""
        bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
        bridge.register_validator(SOURCE, validator_b.address.lower(), "0x", 0)
        tid = _lock(bridge, engine)
        _seal(bridge, engine, proposer, [tid], attestations=[])
        proof = bridge.build_proof(tid, source_chain=SOURCE)
        header = bridge._get_block_header(SOURCE, HEIGHT)
        assert header is not None
        assert not bridge._verify_threshold_signatures(proof, header=header)

    def test_satisfied_sealed_attestations_kept_verbatim(
        self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount, validator_b: EthAccount
    ) -> None:
        """Cheap path: metadata attestations already meet the threshold."""
        bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
        bridge.register_validator(SOURCE, validator_b.address.lower(), "0x", 0)
        tid = _lock(bridge, engine)
        # Pre-sign so the sealed attestation is included in the block.
        block = _seal(bridge, engine, proposer, [tid], attestations=None)
        sig_b = sign_block_hash_local(block, validator_b.key.hex())
        with Session(engine) as session:
            row = session.exec(select(Block).where(Block.chain_id == SOURCE, Block.height == HEIGHT)).one()
            row.block_metadata = json.dumps({"attestations": [{"validator": validator_b.address, "signature": sig_b}]})
            session.add(row)
            session.commit()
        proof = bridge.build_proof(tid, source_chain=SOURCE)
        assert proof["validator_signatures"] == [sig_b]

    def test_no_keys_no_set_changes_nothing(self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount) -> None:
        """Graceful: no registered/env validator set — original list returned."""
        tid = _lock(bridge, engine)
        _seal(bridge, engine, proposer, [tid], attestations=[])
        proof = bridge.build_proof(tid, source_chain=SOURCE)
        assert proof["validator_signatures"] == []


class TestRemoteAttestationAugmentation:
    """No local key for the missing signer — remote collection supplies it."""

    def test_remote_attestation_fills_the_gap(
        self,
        bridge: CrossChainBridge,
        engine: Any,
        proposer: EthAccount,
        validator_b: EthAccount,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
        bridge.register_validator(SOURCE, validator_b.address.lower(), "0x", 0)
        tid = _lock(bridge, engine)
        block = _seal(bridge, engine, proposer, [tid], attestations=[])
        sig_b = sign_block_hash_local(block, validator_b.key.hex())

        async def _fake_collect(self: Any, blk: Any, min_count: int, timeout: Any = None, transactions: Any = None):
            return [{"validator": validator_b.address, "signature": sig_b}]

        monkeypatch.setattr(
            "aitbc_chain.consensus.remote_attestation.RemoteAttestationService.collect_attestations",
            _fake_collect,
        )
        # A remote round only runs when the node holds at least one key.
        with patch(
            "aitbc_chain.config.settings.validator_keys",
            json.dumps({proposer.address: proposer.key.hex()}),
        ):
            proof = bridge.build_proof(tid, source_chain=SOURCE)
        signers = {s.lower() for s in _proof_signers(bridge, block, proof)}
        assert {proposer.address.lower(), validator_b.address.lower()} <= signers
        header = bridge._get_block_header(SOURCE, HEIGHT)
        assert header is not None
        assert bridge._verify_threshold_signatures(proof, header=header)

    def test_remote_failure_degrades_to_sealed_set(
        self,
        bridge: CrossChainBridge,
        engine: Any,
        proposer: EthAccount,
        validator_b: EthAccount,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
        bridge.register_validator(SOURCE, validator_b.address.lower(), "0x", 0)
        tid = _lock(bridge, engine)
        _seal(bridge, engine, proposer, [tid], attestations=[])

        async def _boom(self: Any, blk: Any, min_count: int, timeout: Any = None, transactions: Any = None):
            raise RuntimeError("gossip down")

        monkeypatch.setattr(
            "aitbc_chain.consensus.remote_attestation.RemoteAttestationService.collect_attestations",
            _boom,
        )
        with patch(
            "aitbc_chain.config.settings.validator_keys",
            json.dumps({proposer.address: proposer.key.hex()}),
        ):
            proof = bridge.build_proof(tid, source_chain=SOURCE)
        # Proposer's own key is skipped (already covered by proposer_signature);
        # remote failed → nothing added.
        assert proof["validator_signatures"] == []
