"""
Regression test for the denormalised-receipt drift (settlement triage, S-5).

``Job.receipt`` is a denormalised copy of the signed ``JobReceipt`` row. The
triage found the two drifting apart — always in the payer-harmful direction —
because a later write path overwrote the copy with a caller-supplied receipt.
``execute_job`` now adopts ``result["receipt"]`` only when the job has no
signed receipt of record (``receipt_id`` unset); a job whose receipt was
already signed keeps its copy.
"""

from __future__ import annotations

from sqlmodel import Session

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.services.jobs import JobService


def _make_running_job(session: Session, job_id: str, *, receipt_id: str | None, receipt: dict | None) -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state="RUNNING",
        payload={},
        receipt_id=receipt_id,
        receipt=receipt,
    )
    session.add(job)
    session.commit()
    return job


def test_execute_job_keeps_signed_receipt_copy(db_engine):
    """A caller-supplied receipt must not clobber a signed receipt of record."""
    signed_copy = {"receipt_id": "r-signed", "price": 0.086, "status": "COMPLETED"}
    caller_copy = {"receipt_id": "r-signed", "price": 9.99, "status": "COMPLETED"}

    with Session(db_engine) as session:
        job = _make_running_job(session, "job-signed", receipt_id="r-signed", receipt=signed_copy)
        JobService(session).execute_job(job.id, {"output": {"text": "done"}, "receipt": caller_copy})
        session.refresh(job)
        assert job.receipt == signed_copy, "caller-supplied receipt overwrote the signed copy"
        assert job.receipt_id == "r-signed"
        assert job.state == "COMPLETED"


def test_execute_job_adopts_receipt_when_unsigned(db_engine):
    """Backward compat: with no receipt of record, the caller's receipt is used."""
    caller_copy = {"receipt_id": "r-new", "price": 0.01, "status": "COMPLETED"}

    with Session(db_engine) as session:
        job = _make_running_job(session, "job-unsigned", receipt_id=None, receipt=None)
        JobService(session).execute_job(job.id, {"output": {"text": "done"}, "receipt": caller_copy})
        session.refresh(job)
        assert job.receipt == caller_copy
        assert job.state == "COMPLETED"


def test_execute_job_adopts_none_when_unsigned(db_engine):
    """No receipt_id and no caller receipt leaves the column empty, not stale."""
    with Session(db_engine) as session:
        job = _make_running_job(session, "job-bare", receipt_id=None, receipt=None)
        JobService(session).execute_job(job.id, {"output": {"text": "done"}})
        session.refresh(job)
        assert job.receipt is None
        assert job.state == "COMPLETED"
