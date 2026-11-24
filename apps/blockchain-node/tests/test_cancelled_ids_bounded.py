"""#2871: _cancelled_job_ids ran an unbounded .all() of ai_job_cancellation
on every /ai/jobs, /ai/job/{id} and /ai/stats request. Now bounded to the
newest _CANCELLED_IDS_LIMIT rows. No chain_id filter — the table lives in
the per-chain chain.db, and rows carry the origin tx's chain_id spelling.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, create_engine

from aitbc_chain.base_models import AIJobCancellation
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import ai_services


def _engine():
    engine = create_engine("sqlite:///:memory:")
    chain_metadata.create_all(engine)
    return engine


def _seed_cancellations(engine, n: int, chain_id: str = "c") -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as s:
        for i in range(n):
            s.add(
                AIJobCancellation(
                    job_id=f"job-{i:04d}",
                    chain_id=chain_id,
                    tx_hash=f"0x{i:064x}",
                    cancelled_at=base + timedelta(seconds=i),
                )
            )
        s.commit()


def test_cancelled_ids_returns_all_under_limit():
    engine = _engine()
    _seed_cancellations(engine, 5)
    with Session(engine) as s:
        ids = ai_services._cancelled_job_ids(s)
    assert ids == {f"job-{i:04d}" for i in range(5)}


def test_cancelled_ids_bounded_keeps_newest(monkeypatch):
    engine = _engine()
    _seed_cancellations(engine, 5)
    monkeypatch.setattr(ai_services, "_CANCELLED_IDS_LIMIT", 2)
    with Session(engine) as s:
        ids = ai_services._cancelled_job_ids(s)
    # newest cancelled_at wins: job-0004, job-0003
    assert ids == {"job-0003", "job-0004"}


def test_cancelled_ids_not_filtered_by_chain_id():
    """Rows carry the origin tx's chain_id — the per-chain DB is the
    isolation boundary, so differing spellings must still overlay."""
    engine = _engine()
    _seed_cancellations(engine, 2, chain_id="other-chain")
    with Session(engine) as s:
        ids = ai_services._cancelled_job_ids(s)
    assert ids == {"job-0000", "job-0001"}
