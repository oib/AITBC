"""Tests for chain synchronization, conflict resolution, and signature validation."""

import hashlib
import json
import time
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.models import Block, Transaction
from aitbc_chain.sync import ChainSync, ProposerSignatureValidator
from aitbc_chain.sync import settings as sync_settings
from sqlmodel import Session, create_engine, select

from aitbc_chain.metadata import chain_metadata


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


@pytest.fixture
def db_engine(tmp_path):
    db_path = tmp_path / "test_sync.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    @contextmanager
    def _factory():
        with Session(db_engine) as session:
            yield session

    return _factory


def _make_block_hash(chain_id, height, parent_hash, timestamp):
    payload = f"{chain_id}|{height}|{parent_hash}|{timestamp.isoformat()}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()


def _seed_chain(session_factory, count=5, chain_id="test-chain", proposer="proposer-a"):
    """Seed a chain with `count` blocks."""
    parent_hash = "0x00"
    blocks = []
    with session_factory() as session:
        for h in range(count):
            ts = datetime(2026, 1, 1, 0, 0, h)
            bh = _make_block_hash(chain_id, h, parent_hash, ts)
            block = Block(
                chain_id=chain_id,
                height=h,
                hash=bh,
                parent_hash=parent_hash,
                proposer=proposer,
                timestamp=ts,
                tx_count=0,
            )
            session.add(block)
            blocks.append(
                {"height": h, "hash": bh, "parent_hash": parent_hash, "proposer": proposer, "timestamp": ts.isoformat()}
            )
            parent_hash = bh
        session.commit()
    return blocks


class TestProposerSignatureValidator:
    def test_unsigned_block_rejected_without_trusted_set(self):
        """Fail closed: unsigned block + empty trusted set = no way to authenticate."""
        v = ProposerSignatureValidator()
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 1, "0x00", ts)
        ok, reason = v.validate_block_signature(
            {
                "height": 1,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
            }
        )
        assert ok is False
        assert "no trusted proposer set" in reason

    def test_signed_block_accepted(self):
        """A block signed by its proposer verifies cryptographically."""
        from eth_account import Account as EthAccount

        from aitbc.crypto.consensus_signing import sign_block_hash

        proposer = EthAccount.create()
        v = ProposerSignatureValidator()
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 1, "0x00", ts)
        ok, reason = v.validate_block_signature(
            {
                "height": 1,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": proposer.address,
                "timestamp": ts.isoformat(),
                "signature": sign_block_hash(bh, proposer.key.hex()),
            }
        )
        assert ok is True
        assert reason == "Valid"

    def test_signed_block_wrong_key_rejected(self):
        """A signature recovering to a different address is rejected."""
        from eth_account import Account as EthAccount

        from aitbc.crypto.consensus_signing import sign_block_hash

        proposer = EthAccount.create()
        impostor = EthAccount.create()
        v = ProposerSignatureValidator()
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 1, "0x00", ts)
        ok, reason = v.validate_block_signature(
            {
                "height": 1,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": proposer.address,
                "timestamp": ts.isoformat(),
                "signature": sign_block_hash(bh, impostor.key.hex()),
            }
        )
        assert ok is False
        assert "Invalid proposer signature" in reason

    def test_missing_proposer(self):
        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature(
            {
                "height": 1,
                "hash": "0x" + "a" * 64,
                "parent_hash": "0x00",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        assert ok is False
        assert "Missing proposer" in reason

    def test_invalid_hash_format(self):
        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature(
            {
                "height": 1,
                "hash": "badhash",
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        assert ok is False
        assert "Invalid hash length" in reason

    def test_invalid_hash_length(self):
        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature(
            {
                "height": 1,
                "hash": "0xabc",
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        assert ok is False
        assert "Invalid hash length" in reason

    def test_untrusted_proposer_rejected(self):
        v = ProposerSignatureValidator(trusted_proposers=["node-a", "node-b"])
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 1, "0x00", ts)
        ok, reason = v.validate_block_signature(
            {
                "height": 1,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-evil",
                "timestamp": ts.isoformat(),
            }
        )
        assert ok is False
        assert "not in trusted set" in reason

    def test_trusted_proposer_accepted(self):
        v = ProposerSignatureValidator(trusted_proposers=["node-a"])
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 1, "0x00", ts)
        ok, reason = v.validate_block_signature(
            {
                "height": 1,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
            }
        )
        assert ok is True

    def test_add_remove_trusted(self):
        v = ProposerSignatureValidator()
        assert len(v.trusted_proposers) == 0
        v.add_trusted("node-x")
        assert "node-x" in v.trusted_proposers
        v.remove_trusted("node-x")
        assert "node-x" not in v.trusted_proposers

    def test_pbft_certificate_block_accepted(self, monkeypatch):
        """A multi-validator block carrying a PBFT commit certificate is accepted."""
        from eth_account import Account as EthAccount

        from aitbc.crypto.consensus_signing import sign_block_hash, sign_consensus_message

        proposer = EthAccount.create()
        validator = EthAccount.create()
        proposer_addr = proposer.address
        validator_addr = validator.address
        validator_set = json.dumps([{"address": proposer_addr}, {"address": validator_addr}])

        monkeypatch.setattr(sync_settings, "multi_validator_consensus_enabled", True)
        monkeypatch.setattr(sync_settings, "multi_validator_min_attestations", 1)
        monkeypatch.setattr(sync_settings, "validator_set", validator_set)

        ts = datetime.now(UTC)
        chain_id = "test"
        height = 1
        block_hash = _make_block_hash(chain_id, height, "0x00", ts)
        state_root = "0x" + "11" * 32
        bridge_state_root = "0x" + "22" * 32

        block_header = {
            "chain_id": chain_id,
            "height": height,
            "hash": block_hash,
            "parent_hash": "0x00",
            "proposer": proposer_addr,
            "state_root": state_root,
            "bridge_state_root": bridge_state_root,
        }
        proposer_signature = sign_block_hash(block_header, proposer.key.hex())

        view_number = 0
        sequence_number = height
        digest = hashlib.sha256(f"{block_hash}:{sequence_number}:{view_number}".encode()).hexdigest()
        commit_msg = {
            "message_type": "commit",
            "sender": validator_addr,
            "view_number": view_number,
            "sequence_number": sequence_number,
            "digest": digest,
        }
        commit_signature = sign_consensus_message(commit_msg, validator.key.hex())
        certificate = [
            {
                "message_type": "commit",
                "sender": validator_addr,
                "view_number": view_number,
                "sequence_number": sequence_number,
                "digest": digest,
                "signature": commit_signature,
                "timestamp": time.time(),
                "block_hash": block_hash,
            }
        ]
        block_metadata = json.dumps({"pbft_certificate": certificate})

        block_data = {
            "height": height,
            "hash": block_hash,
            "parent_hash": "0x00",
            "proposer": proposer_addr,
            "timestamp": ts.isoformat(),
            "chain_id": chain_id,
            "state_root": state_root,
            "bridge_state_root": bridge_state_root,
            "signature": proposer_signature,
            "block_metadata": block_metadata,
        }

        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature(block_data)
        assert ok is True, reason

    def test_pbft_certificate_with_insufficient_commits_rejected(self, monkeypatch):
        """A PBFT block with fewer valid commits than required is rejected."""
        from eth_account import Account as EthAccount

        from aitbc.crypto.consensus_signing import sign_block_hash

        proposer = EthAccount.create()
        proposer_addr = proposer.address
        validator = EthAccount.create()
        validator_addr = validator.address
        validator_set = json.dumps([{"address": proposer_addr}, {"address": validator_addr}])

        monkeypatch.setattr(sync_settings, "multi_validator_consensus_enabled", True)
        monkeypatch.setattr(sync_settings, "multi_validator_min_attestations", 2)
        monkeypatch.setattr(sync_settings, "validator_set", validator_set)

        ts = datetime.now(UTC)
        chain_id = "test"
        height = 1
        block_hash = _make_block_hash(chain_id, height, "0x00", ts)

        block_header = {
            "chain_id": chain_id,
            "height": height,
            "hash": block_hash,
            "parent_hash": "0x00",
            "proposer": proposer_addr,
            "state_root": "0x" + "11" * 32,
            "bridge_state_root": "0x" + "22" * 32,
        }
        proposer_signature = sign_block_hash(block_header, proposer.key.hex())

        block_metadata = json.dumps({"pbft_certificate": []})
        block_data = {
            **block_header,
            "timestamp": ts.isoformat(),
            "signature": proposer_signature,
            "block_metadata": block_metadata,
        }

        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature(block_data)
        assert ok is False
        assert "0 valid PBFT commits" in reason

    def test_missing_required_field(self):
        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature(
            {
                "hash": "0x" + "a" * 64,
                "proposer": "node-a",
                # missing height, parent_hash, timestamp
            }
        )
        assert ok is False
        assert "Missing required field" in reason


class TestChainSyncAppend:
    def test_append_to_empty_chain(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 0, "0x00", ts)
        result = sync.import_block(
            {
                "height": 0,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
            }
        )
        assert result.accepted is True
        assert result.height == 0

    def test_append_sequential(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        blocks = _seed_chain(session_factory, count=3, chain_id="test")
        last = blocks[-1]

        ts = datetime(2026, 1, 1, 0, 0, 3)
        bh = _make_block_hash("test", 3, last["hash"], ts)
        result = sync.import_block(
            {
                "height": 3,
                "hash": bh,
                "parent_hash": last["hash"],
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
            }
        )
        assert result.accepted is True
        assert result.height == 3

    def test_duplicate_rejected(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        blocks = _seed_chain(session_factory, count=2, chain_id="test")
        result = sync.import_block(
            {
                "height": 0,
                "hash": blocks[0]["hash"],
                "parent_hash": "0x00",
                "proposer": "proposer-a",
                "timestamp": blocks[0]["timestamp"],
            }
        )
        assert result.accepted is False
        assert "already exists" in result.reason

    def test_lower_height_block_with_different_hash_rejected(self, session_factory):
        """Renamed from test_stale_block_rejected: a different hash at a height we already hold is
        divergence, not staleness, and import_block routes it to _resolve_fork (V23-90)."""
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=5, chain_id="test")
        ts = datetime(2026, 6, 1)
        bh = _make_block_hash("test", 2, "0x00", ts)
        result = sync.import_block(
            {
                "height": 2,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-b",
                "timestamp": ts.isoformat(),
            }
        )
        assert result.accepted is False
        assert result.diverged is True
        assert "different block at height 2" in result.reason

    def test_gap_detected(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=3, chain_id="test")
        ts = datetime(2026, 6, 1)
        bh = _make_block_hash("test", 10, "0x00", ts)
        result = sync.import_block(
            {
                "height": 10,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
            }
        )
        assert result.accepted is False
        assert "Gap" in result.reason

    def test_next_height_with_unknown_parent_is_divergence(self, session_factory):
        """Peer one height ahead whose parent is not our tip is a fork, not unhandled.

        Production symptom: shop at 6936 with a local proposer tip could not import
        hub 6937 (parent = hub 6936) and logged "Unhandled import case" forever.
        """
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=3, chain_id="test")
        ts = datetime(2026, 6, 1)
        alien_parent = "0x" + "ab" * 32
        bh = _make_block_hash("test", 3, alien_parent, ts)
        result = sync.import_block(
            {
                "height": 3,
                "hash": bh,
                "parent_hash": alien_parent,
                "proposer": "node-b",
                "timestamp": ts.isoformat(),
            }
        )
        assert result.accepted is False
        assert result.diverged is True
        assert "Divergent chain" in result.reason
        assert "Unhandled" not in result.reason

    def test_bridge_state_root_preserved_on_import(self, session_factory):
        """bridge_state_root from a P2P broadcast must survive the DB write (v0.7.6)."""
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        blocks = _seed_chain(session_factory, count=2, chain_id="test")
        last = blocks[-1]

        ts = datetime(2026, 1, 1, 0, 0, 2)
        bh = _make_block_hash("test", 2, last["hash"], ts)
        bridge_root = "0x" + "cd" * 32
        result = sync.import_block(
            {
                "height": 2,
                "hash": bh,
                "parent_hash": last["hash"],
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
                "state_root": "0x" + "ab" * 32,
                "bridge_state_root": bridge_root,
                "signature": "0x" + "01" * 65,
                "block_metadata": None,
            },
            skip_state_root_validation=True,
        )
        assert result.accepted is True

        with session_factory() as session:
            stored = session.exec(select(Block).where(Block.hash == bh)).first()
            assert stored is not None
            assert stored.bridge_state_root == bridge_root

    def test_bridge_state_root_derived_when_missing(self, session_factory):
        """A missing bridge_state_root is derived (empty trie root) instead of NULL."""
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        blocks = _seed_chain(session_factory, count=2, chain_id="test")
        last = blocks[-1]

        ts = datetime(2026, 1, 1, 0, 0, 2)
        bh = _make_block_hash("test", 2, last["hash"], ts)
        result = sync.import_block(
            {
                "height": 2,
                "hash": bh,
                "parent_hash": last["hash"],
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
                "state_root": "0x" + "ab" * 32,
                "signature": "0x" + "01" * 65,
            },
            skip_state_root_validation=True,
        )
        assert result.accepted is True

        from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie

        expected = "0x" + MerklePatriciaTrie().get_root().hex()
        with session_factory() as session:
            stored = session.exec(select(Block).where(Block.hash == bh)).first()
            assert stored is not None
            assert stored.bridge_state_root == expected


class TestChainSyncBulkImport:
    def test_append_with_transactions(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        blocks = _seed_chain(session_factory, count=1, chain_id="test")
        last = blocks[-1]

        ts = datetime(2026, 1, 1, 0, 0, 1)
        bh = _make_block_hash("test", 1, last["hash"], ts)
        txs = [
            {"tx_hash": "0x" + "a" * 64, "sender": "alice", "recipient": "bob"},
            {"tx_hash": "0x" + "b" * 64, "sender": "charlie", "recipient": "dave"},
        ]
        result = sync.import_block(
            {
                "height": 1,
                "hash": bh,
                "parent_hash": last["hash"],
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
                "tx_count": 2,
            },
            transactions=txs,
        )

        assert result.accepted is True
        # Verify transactions were stored
        with session_factory() as session:
            stored_txs = session.exec(select(Transaction).where(Transaction.block_height == 1)).all()
            assert len(stored_txs) == 2

    def test_enforced_state_root_mismatch_rolls_back_block(self, session_factory, monkeypatch):
        monkeypatch.setattr(sync_settings, "enforce_state_root_validation", True)
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        blocks = _seed_chain(session_factory, count=1, chain_id="test")
        last = blocks[-1]
        ts = datetime(2026, 1, 1, 0, 0, 1)
        bh = _make_block_hash("test", 1, last["hash"], ts)

        result = sync.import_block(
            {
                "height": 1,
                "hash": bh,
                "parent_hash": last["hash"],
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
                "state_root": "0x" + "11" * 32,
            }
        )

        assert result.accepted is False
        assert "State root mismatch" in result.reason
        with session_factory() as session:
            stored_block = session.exec(select(Block).where(Block.chain_id == "test", Block.height == 1)).first()
            assert stored_block is None


class TestChainSyncSignatureValidation:
    def test_untrusted_proposer_rejected_on_import(self, session_factory):
        validator = ProposerSignatureValidator(trusted_proposers=["node-a"])
        sync = ChainSync(session_factory, chain_id="test", validator=validator, validate_signatures=True)
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 0, "0x00", ts)
        result = sync.import_block(
            {
                "height": 0,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-evil",
                "timestamp": ts.isoformat(),
            }
        )
        assert result.accepted is False
        assert "not in trusted set" in result.reason

    def test_trusted_proposer_accepted_on_import(self, session_factory):
        validator = ProposerSignatureValidator(trusted_proposers=["node-a"])
        sync = ChainSync(session_factory, chain_id="test", validator=validator, validate_signatures=True)
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 0, "0x00", ts)
        result = sync.import_block(
            {
                "height": 0,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
            }
        )
        assert result.accepted is True

    def test_validation_disabled(self, session_factory):
        validator = ProposerSignatureValidator(trusted_proposers=["node-a"])
        sync = ChainSync(session_factory, chain_id="test", validator=validator, validate_signatures=False)
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 0, "0x00", ts)
        result = sync.import_block(
            {
                "height": 0,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-evil",
                "timestamp": ts.isoformat(),
            }
        )
        assert result.accepted is True  # validation disabled


class TestChainSyncConflictResolution:
    def test_fork_at_same_height_rejected(self, session_factory):
        """Fork below our head — our chain stands, and the result says why (V23-90)."""
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=5, chain_id="test")

        # Try to import a different block at height 3
        ts = datetime(2026, 6, 15)
        bh = _make_block_hash("test", 3, "0xdifferent", ts)
        result = sync.import_block(
            {
                "height": 3,
                "hash": bh,
                "parent_hash": "0xdifferent",
                "proposer": "node-b",
                "timestamp": ts.isoformat(),
            }
        )
        assert result.accepted is False
        assert result.diverged is True
        assert "different block at height 3" in result.reason

    def test_sync_status(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test-chain", validate_signatures=False)
        _seed_chain(session_factory, count=5, chain_id="test-chain")
        status = sync.get_sync_status()
        assert status["chain_id"] == "test-chain"
        assert status["head_height"] == 4
        assert status["total_blocks"] == 5
        assert status["max_reorg_depth"] == 10


class TestSyncMetrics:
    def test_accepted_block_increments_metrics(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 0, "0x00", ts)
        sync.import_block(
            {
                "height": 0,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": ts.isoformat(),
            }
        )
        prom = metrics_registry.render_prometheus()
        assert "sync_blocks_received_total" in prom
        assert "sync_blocks_accepted_total" in prom

    def test_rejected_block_increments_metrics(self, session_factory):
        validator = ProposerSignatureValidator(trusted_proposers=["node-a"])
        sync = ChainSync(session_factory, chain_id="test", validator=validator, validate_signatures=True)
        ts = datetime.now(UTC)
        bh = _make_block_hash("test", 0, "0x00", ts)
        sync.import_block(
            {
                "height": 0,
                "hash": bh,
                "parent_hash": "0x00",
                "proposer": "node-evil",
                "timestamp": ts.isoformat(),
            }
        )
        prom = metrics_registry.render_prometheus()
        assert "sync_blocks_rejected_total" in prom

    def test_duplicate_increments_metrics(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=1, chain_id="test")
        with session_factory() as session:
            block = session.exec(select(Block).where(Block.height == 0)).first()
        sync.import_block(
            {
                "height": 0,
                "hash": block.hash,
                "parent_hash": "0x00",
                "proposer": "proposer-a",
                "timestamp": block.timestamp.isoformat(),
            }
        )
        prom = metrics_registry.render_prometheus()
        assert "sync_blocks_duplicate_total" in prom

    def test_fork_increments_metrics(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=5, chain_id="test")
        ts = datetime(2026, 6, 15)
        bh = _make_block_hash("test", 3, "0xdifferent", ts)
        sync.import_block(
            {
                "height": 3,
                "hash": bh,
                "parent_hash": "0xdifferent",
                "proposer": "node-b",
                "timestamp": ts.isoformat(),
            }
        )
        prom = metrics_registry.render_prometheus()
        assert "sync_forks_detected_total" in prom
