"""Phantom-lock void pass (#2390).

``create_escrow`` persists ``status="locked"`` + ``lock_tx_hash`` once the
lock is sealed OR merely mempool-admitted. An evicted mempool lock leaves a
row that reads funded forever while ``_ensure_lock_sealed`` 425s every
settlement attempt. The pass voids rows whose recorded hash resolves
nowhere — not sealed, not pending — past the min age.
"""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, create_engine
from sqlalchemy.pool import StaticPool

from aitbc_chain.base_models import Escrow, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import escrow_settlement_sweeper as ess
from aitbc_chain.rpc import escrow_settlement_sweeper_scan as scan

CHAIN = "test-chain"
JOB = "sw_job_20261120133522_2a4a4675"
LOCK_HASH = "0xf42a808f1ceaccd10efdb6a33f065d914bbcbc82c9c6250ab2d4e739c9451bad"
BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"

NOW = datetime(2026, 11, 21, 12, 0, 0, tzinfo=UTC)
OLD = NOW - timedelta(hours=2)
FRESH = NOW - timedelta(minutes=30)
MIN_AGE = 3600


@pytest.fixture
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    chain_metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


@pytest.fixture
def wire_session(session, monkeypatch):
    """Point the sweeper's session_scope at the test session and arm flags."""

    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr(ess, "session_scope", _scope)
    monkeypatch.setattr(ess.settings, "escrow_phantom_void_min_age_seconds", MIN_AGE)
    monkeypatch.setattr(ess.settings, "escrow_phantom_void_max_rows", 50)
    monkeypatch.setenv("ESCROW_PHANTOM_VOID_PASS_ENABLED", "true")
    monkeypatch.delenv("ESCROW_PHANTOM_VOID_PASS_DRY_RUN", raising=False)
    return session


def _escrow_row(session, *, job_id=JOB, status="locked", lock_hash=LOCK_HASH, at=OLD, **kw):
    row = Escrow(
        job_id=job_id,
        chain_id=CHAIN,
        buyer=BUYER,
        provider=PROVIDER,
        amount=360000,
        status=status,
        lock_tx_hash=lock_hash,
        created_at=at,
        **kw,
    )
    session.add(row)
    session.commit()
    return row


def _sealed_lock_tx(session, tx_hash=LOCK_HASH, chain_id=CHAIN):
    tx = Transaction(
        chain_id=chain_id,
        tx_hash=tx_hash,
        sender=BUYER,
        recipient=PROVIDER,
        type="ESCROW_LOCK",
        value=360000,
        block_height=33000,
        created_at=OLD,
        payload={"action": "escrow_lock", "job_id": JOB},
    )
    session.add(tx)
    session.commit()
    return tx


def _candidates(session, **kw):
    args = {"min_age_seconds": MIN_AGE, "max_rows": 50}
    args.update(kw)
    return scan.phantom_void_candidates(session, NOW, **args)


# ------------------------------------------------------------------ scan


def test_locked_old_row_is_candidate(session):
    _escrow_row(session)
    cands = _candidates(session)
    assert [c.job_id for c in cands] == [JOB]
    assert cands[0].lock_tx_hash == LOCK_HASH
    assert cands[0].chain_id == CHAIN


def test_fresh_row_deferred(session):
    _escrow_row(session, at=FRESH)
    assert _candidates(session) == []


def test_settled_row_excluded(session):
    _escrow_row(session, released_at=OLD)
    assert _candidates(session) == []


def test_non_locked_status_excluded(session):
    _escrow_row(session, status="released")
    _escrow_row(session, job_id="job2", status="refunded")
    assert _candidates(session) == []


def test_missing_lock_hash_excluded(session):
    _escrow_row(session, lock_hash=None)
    assert _candidates(session) == []


# ------------------------------------------------------------------ pass


@pytest.mark.asyncio
async def test_dead_lock_row_goes_void(wire_session, monkeypatch):
    session = wire_session
    _escrow_row(session)
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value=set()))

    stats = await ess._phantom_void_pass_once(NOW)

    assert stats["voided"] == 1
    row = session.get(Escrow, JOB)
    assert row.status == "void"
    assert row.lock_tx_hash == LOCK_HASH  # kept for forensics


@pytest.mark.asyncio
async def test_sealed_lock_stays_locked(wire_session, monkeypatch):
    session = wire_session
    _escrow_row(session)
    _sealed_lock_tx(session)
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value=set()))

    stats = await ess._phantom_void_pass_once(NOW)

    assert stats["alive"] == 1
    assert stats["voided"] == 0
    assert session.get(Escrow, JOB).status == "locked"


@pytest.mark.asyncio
async def test_pending_lock_stays_locked(wire_session, monkeypatch):
    session = wire_session
    _escrow_row(session)
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value={LOCK_HASH}))

    stats = await ess._phantom_void_pass_once(NOW)

    assert stats["alive"] == 1
    assert session.get(Escrow, JOB).status == "locked"


@pytest.mark.asyncio
async def test_mempool_probe_failure_keeps_locked(wire_session, monkeypatch):
    """Unknown is never dead: a failed mempool probe skips the candidate."""
    session = wire_session
    _escrow_row(session)
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value=None))

    stats = await ess._phantom_void_pass_once(NOW)

    assert stats["probe_error"] == 1
    assert stats["voided"] == 0
    assert session.get(Escrow, JOB).status == "locked"


@pytest.mark.asyncio
async def test_dry_run_counts_but_does_not_write(wire_session, monkeypatch):
    session = wire_session
    _escrow_row(session)
    monkeypatch.setenv("ESCROW_PHANTOM_VOID_PASS_DRY_RUN", "true")
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value=set()))

    stats = await ess._phantom_void_pass_once(NOW)

    assert stats["would_void"] == 1
    assert stats["voided"] == 0
    assert session.get(Escrow, JOB).status == "locked"


@pytest.mark.asyncio
async def test_disabled_pass_is_inert(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr(ess, "session_scope", _scope)
    monkeypatch.delenv("ESCROW_PHANTOM_VOID_PASS_ENABLED", raising=False)
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value=set()))
    _escrow_row(session)

    stats = await ess._phantom_void_pass_once(NOW)

    assert stats == {"scanned": 0, "alive": 0, "voided": 0, "would_void": 0, "probe_error": 0, "error": 0}
    assert session.get(Escrow, JOB).status == "locked"


@pytest.mark.asyncio
async def test_sealed_on_other_chain_does_not_count(wire_session, monkeypatch):
    """A same-hash transaction on a different chain must not mark it alive."""
    session = wire_session
    _escrow_row(session)
    _sealed_lock_tx(session, chain_id="other-chain")
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value=set()))

    stats = await ess._phantom_void_pass_once(NOW)

    assert stats["voided"] == 1
    assert session.get(Escrow, JOB).status == "void"


@pytest.mark.asyncio
async def test_row_that_settled_between_scan_and_write_survives(wire_session, monkeypatch):
    """The row lock re-check refuses to void a row that gained a leg."""
    session = wire_session
    _escrow_row(session)
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value=set()))

    real_void = ess._void_phantom_rows

    def _void_then_settle(cands):
        # Simulate a settlement landing between the scan and the write.
        row = session.get(Escrow, JOB)
        row.refunded_at = OLD
        session.add(row)
        session.commit()
        return real_void(cands)

    monkeypatch.setattr(ess, "_void_phantom_rows", _void_then_settle)

    stats = await ess._phantom_void_pass_once(NOW)

    assert stats["voided"] == 0
    row = session.get(Escrow, JOB)
    assert row.status == "locked"
    assert row.refunded_at is not None
