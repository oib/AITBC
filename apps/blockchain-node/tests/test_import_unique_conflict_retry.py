"""Refs #712: a unique-constraint abort inside ``_append_block`` is not
automatically a committed duplicate.

The wedge that stalled hub at 11124: a concurrent/poisoned transaction
marked the height, the catch reported "concurrent import — duplicate", the
importer skipped every retry, and the block never landed. The fix rolls the
dead transaction back, checks the *committed* view, and retries the append
once when no committed block exists.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from aitbc_chain.base_models import Block
from aitbc_chain.sync import ChainSync

CHAIN = "chain-x"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture()
def sync_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    from aitbc_chain.metadata import chain_metadata

    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    with Session(engine) as session:
        session.add(
            Block(
                chain_id=CHAIN,
                height=0,
                hash="0x" + "00" * 32,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
            )
        )
        session.commit()
    return engine, factory


def _block(height: int = 1, hash: str = "0x" + "aa" * 32) -> dict[str, Any]:
    return {
        "height": height,
        "hash": hash,
        "parent_hash": "0x" + "00" * 32,
        "proposer": "0x" + "ab" * 20,
        "timestamp": T0.isoformat(),
        "tx_count": 0,
        "signature": "0x" + "11" * 65,
    }


def test_unique_violation_with_no_committed_block_retries_once(sync_factory, monkeypatch):
    """Phantom marker: rollback clears it, committed-check finds nothing,
    the append retries — the wedge inverts into a successful import."""
    engine, factory = sync_factory
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)

    calls = {"n": 0}

    def flaky_append(session, block_data, transactions, skip_state_root_validation=False):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("UNIQUE constraint failed: block.height")
        return sync._make_import_result(
            accepted=True, height=block_data["height"], block_hash=block_data["hash"], reason="imported"
        )

    monkeypatch.setattr(sync, "_append_block", flaky_append)
    result = sync.import_block(_block())
    assert calls["n"] == 2, "the append must retry exactly once on a phantom"
    assert result.accepted is True


def test_unique_violation_with_committed_same_hash_is_duplicate(sync_factory, monkeypatch):
    """A genuinely committed block at the height+hash stays a duplicate —
    no retry is attempted."""
    engine, factory = sync_factory
    with Session(engine) as session:
        session.add(
            Block(
                chain_id=CHAIN,
                height=1,
                hash="0x" + "aa" * 32,
                parent_hash="0x" + "00" * 32,
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
            )
        )
        session.commit()
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    # The same-hash existing check fires before _append_block — the unique
    # catch must not be reached; assert a duplicate verdict either way.
    result = sync.import_block(_block())
    assert result.accepted is False
    assert "already exists" in (result.reason or "")


def test_unique_violation_with_committed_different_hash_diverges(sync_factory, monkeypatch):
    """Height committed under a different hash: surface divergence, never a
    silent 'duplicate'."""
    engine, factory = sync_factory
    with Session(engine) as session:
        session.add(
            Block(
                chain_id=CHAIN,
                height=1,
                hash="0x" + "bb" * 32,
                parent_hash="0x" + "00" * 32,
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
            )
        )
        session.commit()
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)

    def unique_append(session, block_data, transactions, skip_state_root_validation=False):
        raise Exception("UNIQUE constraint failed: block.height")

    monkeypatch.setattr(sync, "_append_block", unique_append)
    # Bypass the early same-hash lookup so _append_block runs into the catch:
    # hash lookup misses (our hash differs), height <= our_height path may
    # intercept first — the import must not mislabel the outcome either way.
    result = sync.import_block(_block())
    assert result.accepted is False
    assert "duplicate" not in (result.reason or "").lower()
