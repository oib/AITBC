"""#831: the sweeper and the backfill heal serialise against route settlements.

Both writers committed outside ``escrow_mutation`` from a snapshot taken before
the lock existed, so a route's release/refund landing mid-pass was overwritten
by a ``state`` value derived from stale timestamps. The fix takes the same
stripe flock the routes poll and refreshes the row inside it; a row still
locked when the budget ends is skipped (sweep) or left unhealed (backfill).

The interleave test drives the ordering deterministically: a "route" thread
holds the flock while the sweep waits on it, commits the refund, then lets go —
the sweep must see the settled row, not its pre-lock snapshot.
"""

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Escrow
from aitbc_chain.contracts.escrow import backfill_settlement_legs, row_state_for, EscrowState
from aitbc_chain.contracts.escrow_txn import escrow_row_lock
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import escrow_settlement_sweeper as ess

JOB = "sw_job_stale831"
NOW = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def engine(tmp_path: Path):
    eng = create_engine(f"sqlite:///{tmp_path / 'chain.db'}", connect_args={"check_same_thread": False})
    chain_metadata.create_all(eng)
    yield eng
    eng.dispose()


def _seed(engine, **overrides) -> None:
    fields = {
        "job_id": JOB,
        "chain_id": "test-chain",
        "buyer": "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F",
        "provider": "0xD4d85501E6cD447972Db19370307F1E3B1510016",
        "amount": 3_600_000,
        "status": "released",  # status-only claim: no timestamps, no hashes
        "state": EscrowState.RELEASED.value,
    }
    fields.update(overrides)
    with Session(engine) as s:
        s.add(Escrow(**fields))
        s.commit()


def test_sweep_refreshes_under_the_lock(engine, monkeypatch):
    """A route refund landing while the sweep waits on the stripe lock must not
    be overwritten by a state derived from the pre-lock snapshot."""
    monkeypatch.setenv("ESCROW_ROW_LOCK_TIMEOUT_SECONDS", "10")
    _seed(engine)

    def _route() -> None:
        with Session(engine) as s, escrow_row_lock(s, JOB) as locked:
            assert locked
            time.sleep(0.5)  # the sweep is parked on the flock by now
            row = s.get(Escrow, JOB)
            row.refunded_at = NOW
            row.status = "refunded"
            row.state = row_state_for(row.released_at, row.refunded_at)
            s.add(row)
            s.commit()

    t = threading.Thread(target=_route)
    t.start()
    time.sleep(0.2)  # route holds the lock before the sweep reaches this row
    with Session(engine) as s:
        ess.sweep_once(s, NOW + timedelta(seconds=1), set())
    t.join(timeout=10)

    with Session(engine) as s:
        row = s.get(Escrow, JOB)
    assert row.status == "refunded"
    assert row.state == row_state_for(row.released_at, row.refunded_at) == EscrowState.REFUNDED.value


def test_sweep_skips_a_row_whose_lock_outlives_the_budget(engine, monkeypatch):
    """Still contended when the budget ends: the row is skipped, not written."""
    monkeypatch.setenv("ESCROW_ROW_LOCK_TIMEOUT_SECONDS", "0.2")
    _seed(engine)
    stop = threading.Event()

    def _hold() -> None:
        with Session(engine) as s, escrow_row_lock(s, JOB) as locked:
            assert locked
            stop.wait(2.0)

    t = threading.Thread(target=_hold)
    t.start()
    time.sleep(0.2)
    with Session(engine) as s:
        stats = ess.sweep_once(s, NOW + timedelta(seconds=1), set())
    stop.set()
    t.join(timeout=10)

    assert stats["skipped_locked"] == 1
    with Session(engine) as s:
        row = s.get(Escrow, JOB)
    assert row.status == "released" and row.state == EscrowState.RELEASED.value  # untouched


def test_backfill_skips_the_heal_when_the_row_is_locked(engine, monkeypatch):
    monkeypatch.setenv("ESCROW_ROW_LOCK_TIMEOUT_SECONDS", "0.2")
    _seed(engine, refunded_at=NOW, status="refunded")

    def _hold() -> None:
        with Session(engine) as s, escrow_row_lock(s, JOB) as locked:
            assert locked
            time.sleep(1.0)

    t = threading.Thread(target=_hold)
    t.start()
    time.sleep(0.2)
    with Session(engine) as s:
        record = s.get(Escrow, JOB)
        assert backfill_settlement_legs(s, record) is False
    t.join(timeout=10)
