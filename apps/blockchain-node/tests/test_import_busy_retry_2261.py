"""Refs #2261 SYNC-IMPORT-DB-BUSY-1: WAL snapshot conflicts
(SQLITE_BUSY_SNAPSHOT) bypass sqlite busy_timeout — the append loses the
race against a concurrent chain.db writer (rpc bridge-release finalizer)
and fails immediately. ``_append_with_conflict_retry`` now routes lock
errors through ``_append_with_busy_retry``: fresh NullPool session,
precondition re-check, linear backoff, bounded at 3 retries.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, Block
from aitbc_chain.base_models import Transaction as ChainTransaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.sync import ChainSync
from aitbc.crypto.crypto import derive_ethereum_address

CHAIN = "chain-x"
T0 = datetime(2026, 1, 1, tzinfo=UTC)

KEY_A = "0x" + "11" * 32
ADDR_A = derive_ethereum_address(KEY_A)
ADDR_B = derive_ethereum_address("0x" + "33" * 32)


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


def _lock_error() -> OperationalError:
    return OperationalError(
        "INSERT INTO block ...",
        {},
        sqlite3.OperationalError("database is locked"),
    )


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)


def test_append_retries_sqlite_lock_and_imports(sync_factory, monkeypatch):
    """First append hits a WAL snapshot conflict; the bounded retry on a
    fresh session lands the block — no ERROR-path failure result."""
    engine, factory = sync_factory
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)

    calls = {"n": 0}

    def flaky_append(session, block_data, transactions, skip_state_root_validation=False):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _lock_error()
        return sync._make_import_result(
            accepted=True, height=block_data["height"], block_hash=block_data["hash"], reason="imported"
        )

    monkeypatch.setattr(sync, "_append_block", flaky_append)
    result = sync.import_block(_block())
    assert calls["n"] == 2, "the append must retry once on a transient lock"
    assert result.accepted is True


def test_append_lock_retries_exhausted_fails(sync_factory, monkeypatch):
    """Persistent lock errors exhaust the 3-retry budget and take the
    failure path — bounded, never an infinite retry loop."""
    engine, factory = sync_factory
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)

    calls = {"n": 0}

    def always_locked(session, block_data, transactions, skip_state_root_validation=False):
        calls["n"] += 1
        raise _lock_error()

    monkeypatch.setattr(sync, "_append_block", always_locked)
    result = sync.import_block(_block())
    assert calls["n"] == 4, "1 original attempt + 3 bounded retries"
    assert result.accepted is False
    assert "lock retries" in (result.reason or "")


def test_append_lock_retry_sees_concurrent_commit_as_duplicate(sync_factory, monkeypatch):
    """If a concurrent import lands the block while we back off, the retry's
    fresh-session precondition check reports a duplicate instead of
    double-appending."""
    engine, factory = sync_factory
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)

    calls = {"n": 0}

    def lock_then_commit_elsewhere(session, block_data, transactions, skip_state_root_validation=False):
        calls["n"] += 1
        # Simulate the racing writer: commit the same block on a separate
        # connection, then fail our append with the snapshot conflict.
        with Session(engine) as other:
            other.add(
                Block(
                    chain_id=CHAIN,
                    height=1,
                    hash="0x" + "aa" * 32,
                    parent_hash="0x" + "00" * 32,
                    proposer="0x" + "ab" * 20,
                    timestamp=T0,
                    tx_count=0,
                )
            )
            other.commit()
        raise _lock_error()

    monkeypatch.setattr(sync, "_append_block", lock_then_commit_elsewhere)
    result = sync.import_block(_block())
    assert calls["n"] == 1, "no re-append once the block is committed elsewhere"
    assert result.accepted is False
    assert "already exists" in (result.reason or "")


def test_append_non_lock_error_does_not_retry(sync_factory, monkeypatch):
    """Non-lock append failures keep the existing single-attempt path — the
    busy retry is scoped to sqlite lock errors only."""
    engine, factory = sync_factory
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)

    calls = {"n": 0}

    def boom(session, block_data, transactions, skip_state_root_validation=False):
        calls["n"] += 1
        raise RuntimeError("apply exploded")

    monkeypatch.setattr(sync, "_append_block", boom)
    result = sync.import_block(_block())
    assert calls["n"] == 1
    assert result.accepted is False


# ---------------------------------------------------------------------------
# #2276 SYNC-IMPORT-BUSY-RETRY-CACHE-1: the busy retry reuses the process-global
# StateTransition._processed_tx_hashes cache. A lock error that fires *at
# commit* leaves the failed attempt's tx hashes in that set; the retry then
# re-validates them against an empty DB and the replay guard reports
# "already processed" — the retried block can import with the tx wrongly
# marked rejected (silent divergence) or fail outright.
# ---------------------------------------------------------------------------


@pytest.fixture()
def tx_sync_factory(tmp_path, monkeypatch):
    """Sync factory whose FIRST session commit raises a sqlite lock error —
    the WAL snapshot conflict lands at ``_commit_import``'s commit, after the
    tx apply has already populated the in-memory processed cache."""
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    state = {"armed": True}

    class LockOnceSession(Session):
        def commit(self):
            if state["armed"]:
                state["armed"] = False
                raise _lock_error()
            return super().commit()

    @contextmanager
    def factory():
        with LockOnceSession(engine) as session:
            yield session
            session.commit()

    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=10**9, nonce=0))
        session.add(Account(chain_id=CHAIN, address=ADDR_B, balance=0, nonce=0))
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


def _signed_tx(tx_hash: str = "0x" + "bb" * 32) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": ADDR_A,
        "to": ADDR_B,
        "amount": 1_000,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "payload": {},
        "type": "TRANSFER",
        "chain_id": CHAIN,
        "tx_hash": tx_hash,
    }
    tx["signature"] = sign_transaction_data(tx, KEY_A)
    return tx


def _tx_block(tx: dict[str, Any], *, version: int = 22) -> dict[str, Any]:
    """A v20+ block whose hash reproduces over the delivered tx list (#1064)."""
    from aitbc_chain.consensus.block_hash import compute_block_hash

    timestamp = (T0.replace(hour=0, minute=0, second=0)).isoformat()
    block: dict[str, Any] = {
        "chain_id": CHAIN,
        "height": 1,
        "hash": "",
        "parent_hash": "0x" + "00" * 32,
        "proposer": ADDR_A,
        "timestamp": timestamp,
        "tx_count": 1,
        "state_root": None,
        "aux_state_root": None,
        "block_metadata": f'{{"state_transition_version": {version}}}',
        "signature": "",
        "transactions": [tx],
    }
    block["hash"] = compute_block_hash(
        CHAIN,
        1,
        block["parent_hash"],
        timestamp,
        [str(tx.get("tx_hash", ""))],
        ADDR_A,
        None,
        None,
        None,
    )
    return block


def test_append_lock_retry_resets_processed_cache(tx_sync_factory, monkeypatch):
    """First append commits-fails on a WAL snapshot conflict *after* the tx
    was applied in-memory; the bounded retry must clear the processed cache
    or the tx re-validates as a replay and lands rejected."""
    engine, factory = tx_sync_factory
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    tx = _signed_tx()
    result = sync.import_block(_tx_block(tx), transactions=[tx], skip_state_root_validation=True)

    assert result.accepted is True, f"retry must land the block: {result.reason}"
    with Session(engine) as session:
        row = session.exec(
            select(ChainTransaction).where(ChainTransaction.chain_id == CHAIN, ChainTransaction.tx_hash == tx["tx_hash"])
        ).first()
        recipient = session.exec(select(Account).where(Account.chain_id == CHAIN, Account.address == ADDR_B)).one()
    assert row is not None
    # The dirty-cache failure mode is subtle: the retried block still commits,
    # but the tx is recorded "failed" (replay-attack validation) instead of
    # "confirmed" — accepted=True while the money never moved.
    assert row.status == "confirmed", f"tx-bearing retry must apply the tx, got status={row.status}"
    assert recipient.balance == 1_000
