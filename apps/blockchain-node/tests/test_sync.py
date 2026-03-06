"""Tests for chain synchronization, conflict resolution, and signature validation."""

import hashlib
import time
import pytest
from datetime import datetime
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine, select

from aitbc_chain.models import Block, Transaction
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.sync import ChainSync, ProposerSignatureValidator, ImportResult


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


@pytest.fixture
def db_engine(tmp_path):
    db_path = tmp_path / "test_sync.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


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
                height=h, hash=bh, parent_hash=parent_hash,
                proposer=proposer, timestamp=ts, tx_count=0,
            )
            session.add(block)
            blocks.append({"height": h, "hash": bh, "parent_hash": parent_hash,
                           "proposer": proposer, "timestamp": ts.isoformat()})
            parent_hash = bh
        session.commit()
    return blocks


class TestProposerSignatureValidator:

    def test_valid_block(self):
        v = ProposerSignatureValidator()
        ts = datetime.utcnow()
        bh = _make_block_hash("test", 1, "0x00", ts)
        ok, reason = v.validate_block_signature({
            "height": 1, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-a", "timestamp": ts.isoformat(),
        })
        assert ok is True
        assert reason == "Valid"

    def test_missing_proposer(self):
        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature({
            "height": 1, "hash": "0x" + "a" * 64, "parent_hash": "0x00",
            "timestamp": datetime.utcnow().isoformat(),
        })
        assert ok is False
        assert "Missing proposer" in reason

    def test_invalid_hash_format(self):
        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature({
            "height": 1, "hash": "badhash", "parent_hash": "0x00",
            "proposer": "node-a", "timestamp": datetime.utcnow().isoformat(),
        })
        assert ok is False
        assert "Invalid block hash" in reason

    def test_invalid_hash_length(self):
        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature({
            "height": 1, "hash": "0xabc", "parent_hash": "0x00",
            "proposer": "node-a", "timestamp": datetime.utcnow().isoformat(),
        })
        assert ok is False
        assert "Invalid hash length" in reason

    def test_untrusted_proposer_rejected(self):
        v = ProposerSignatureValidator(trusted_proposers=["node-a", "node-b"])
        ts = datetime.utcnow()
        bh = _make_block_hash("test", 1, "0x00", ts)
        ok, reason = v.validate_block_signature({
            "height": 1, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-evil", "timestamp": ts.isoformat(),
        })
        assert ok is False
        assert "not in trusted set" in reason

    def test_trusted_proposer_accepted(self):
        v = ProposerSignatureValidator(trusted_proposers=["node-a"])
        ts = datetime.utcnow()
        bh = _make_block_hash("test", 1, "0x00", ts)
        ok, reason = v.validate_block_signature({
            "height": 1, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-a", "timestamp": ts.isoformat(),
        })
        assert ok is True

    def test_add_remove_trusted(self):
        v = ProposerSignatureValidator()
        assert len(v.trusted_proposers) == 0
        v.add_trusted("node-x")
        assert "node-x" in v.trusted_proposers
        v.remove_trusted("node-x")
        assert "node-x" not in v.trusted_proposers

    def test_missing_required_field(self):
        v = ProposerSignatureValidator()
        ok, reason = v.validate_block_signature({
            "hash": "0x" + "a" * 64, "proposer": "node-a",
            # missing height, parent_hash, timestamp
        })
        assert ok is False
        assert "Missing required field" in reason


class TestChainSyncAppend:

    def test_append_to_empty_chain(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        ts = datetime.utcnow()
        bh = _make_block_hash("test", 0, "0x00", ts)
        result = sync.import_block({
            "height": 0, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-a", "timestamp": ts.isoformat(),
        })
        assert result.accepted is True
        assert result.height == 0

    def test_append_sequential(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        blocks = _seed_chain(session_factory, count=3, chain_id="test")
        last = blocks[-1]

        ts = datetime(2026, 1, 1, 0, 0, 3)
        bh = _make_block_hash("test", 3, last["hash"], ts)
        result = sync.import_block({
            "height": 3, "hash": bh, "parent_hash": last["hash"],
            "proposer": "node-a", "timestamp": ts.isoformat(),
        })
        assert result.accepted is True
        assert result.height == 3

    def test_duplicate_rejected(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        blocks = _seed_chain(session_factory, count=2, chain_id="test")
        result = sync.import_block({
            "height": 0, "hash": blocks[0]["hash"], "parent_hash": "0x00",
            "proposer": "proposer-a", "timestamp": blocks[0]["timestamp"],
        })
        assert result.accepted is False
        assert "already exists" in result.reason

    def test_stale_block_rejected(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=5, chain_id="test")
        ts = datetime(2026, 6, 1)
        bh = _make_block_hash("test", 2, "0x00", ts)
        result = sync.import_block({
            "height": 2, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-b", "timestamp": ts.isoformat(),
        })
        assert result.accepted is False
        assert "Stale" in result.reason or "Fork" in result.reason or "longer" in result.reason

    def test_gap_detected(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=3, chain_id="test")
        ts = datetime(2026, 6, 1)
        bh = _make_block_hash("test", 10, "0x00", ts)
        result = sync.import_block({
            "height": 10, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-a", "timestamp": ts.isoformat(),
        })
        assert result.accepted is False
        assert "Gap" in result.reason

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
        result = sync.import_block({
            "height": 1, "hash": bh, "parent_hash": last["hash"],
            "proposer": "node-a", "timestamp": ts.isoformat(), "tx_count": 2,
        }, transactions=txs)

        assert result.accepted is True
        # Verify transactions were stored
        with session_factory() as session:
            stored_txs = session.exec(select(Transaction).where(Transaction.block_height == 1)).all()
            assert len(stored_txs) == 2


class TestChainSyncSignatureValidation:

    def test_untrusted_proposer_rejected_on_import(self, session_factory):
        validator = ProposerSignatureValidator(trusted_proposers=["node-a"])
        sync = ChainSync(session_factory, chain_id="test", validator=validator, validate_signatures=True)
        ts = datetime.utcnow()
        bh = _make_block_hash("test", 0, "0x00", ts)
        result = sync.import_block({
            "height": 0, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-evil", "timestamp": ts.isoformat(),
        })
        assert result.accepted is False
        assert "not in trusted set" in result.reason

    def test_trusted_proposer_accepted_on_import(self, session_factory):
        validator = ProposerSignatureValidator(trusted_proposers=["node-a"])
        sync = ChainSync(session_factory, chain_id="test", validator=validator, validate_signatures=True)
        ts = datetime.utcnow()
        bh = _make_block_hash("test", 0, "0x00", ts)
        result = sync.import_block({
            "height": 0, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-a", "timestamp": ts.isoformat(),
        })
        assert result.accepted is True

    def test_validation_disabled(self, session_factory):
        validator = ProposerSignatureValidator(trusted_proposers=["node-a"])
        sync = ChainSync(session_factory, chain_id="test", validator=validator, validate_signatures=False)
        ts = datetime.utcnow()
        bh = _make_block_hash("test", 0, "0x00", ts)
        result = sync.import_block({
            "height": 0, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-evil", "timestamp": ts.isoformat(),
        })
        assert result.accepted is True  # validation disabled


class TestChainSyncConflictResolution:

    def test_fork_at_same_height_rejected(self, session_factory):
        """Fork at same height as our chain — our chain wins (equal length)."""
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        blocks = _seed_chain(session_factory, count=5, chain_id="test")

        # Try to import a different block at height 3
        ts = datetime(2026, 6, 15)
        bh = _make_block_hash("test", 3, "0xdifferent", ts)
        result = sync.import_block({
            "height": 3, "hash": bh, "parent_hash": "0xdifferent",
            "proposer": "node-b", "timestamp": ts.isoformat(),
        })
        assert result.accepted is False
        assert "longer" in result.reason or "Fork" in result.reason

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
        ts = datetime.utcnow()
        bh = _make_block_hash("test", 0, "0x00", ts)
        sync.import_block({
            "height": 0, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-a", "timestamp": ts.isoformat(),
        })
        prom = metrics_registry.render_prometheus()
        assert "sync_blocks_received_total" in prom
        assert "sync_blocks_accepted_total" in prom

    def test_rejected_block_increments_metrics(self, session_factory):
        validator = ProposerSignatureValidator(trusted_proposers=["node-a"])
        sync = ChainSync(session_factory, chain_id="test", validator=validator, validate_signatures=True)
        ts = datetime.utcnow()
        bh = _make_block_hash("test", 0, "0x00", ts)
        sync.import_block({
            "height": 0, "hash": bh, "parent_hash": "0x00",
            "proposer": "node-evil", "timestamp": ts.isoformat(),
        })
        prom = metrics_registry.render_prometheus()
        assert "sync_blocks_rejected_total" in prom

    def test_duplicate_increments_metrics(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=1, chain_id="test")
        with session_factory() as session:
            block = session.exec(select(Block).where(Block.height == 0)).first()
        sync.import_block({
            "height": 0, "hash": block.hash, "parent_hash": "0x00",
            "proposer": "proposer-a", "timestamp": block.timestamp.isoformat(),
        })
        prom = metrics_registry.render_prometheus()
        assert "sync_blocks_duplicate_total" in prom

    def test_fork_increments_metrics(self, session_factory):
        sync = ChainSync(session_factory, chain_id="test", validate_signatures=False)
        _seed_chain(session_factory, count=5, chain_id="test")
        ts = datetime(2026, 6, 15)
        bh = _make_block_hash("test", 3, "0xdifferent", ts)
        sync.import_block({
            "height": 3, "hash": bh, "parent_hash": "0xdifferent",
            "proposer": "node-b", "timestamp": ts.isoformat(),
        })
        prom = metrics_registry.render_prometheus()
        assert "sync_forks_detected_total" in prom
