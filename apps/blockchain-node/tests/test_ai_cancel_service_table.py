"""AI-CANCEL-SEALED-TX-1 (#386).

``POST /ai/job/{job_id}/cancel`` used to rewrite ``tx.status``/``tx.payload``
on the sealed ``transaction`` row of the serving host — a canonical copy of a
sealed row diverging per node. The cancel now lands in the per-node
``ai_job_cancellation`` service table (in no committed fingerprint set) and
read paths overlay ``status="cancelled"`` from it; the sealed row is never
touched.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from aitbc_chain.base_models import AIJobCancellation, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import ai_services
from fastapi import HTTPException
from sqlmodel import Session, create_engine, select

CHAIN = "ai-cancel-fixture"
JOB_TX_HASH = "0x" + "12" * 32
JOB_ID = "job-cancel-me"


def _engine():
    engine = create_engine("sqlite:///:memory:")
    chain_metadata.create_all(engine)
    return engine


def _bind_session_scope(monkeypatch, engine) -> None:
    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    # ai_services binds `session_scope` at module import time — patch the name
    # in ITS namespace, not on the database module (unlike gpu_resources, which
    # re-imports it lazily inside each handler).
    monkeypatch.setattr("aitbc_chain.rpc.ai_services.session_scope", scope)


def _seed_job(engine, *, status: str = "pending", job_id: str = JOB_ID) -> Transaction:
    with Session(engine) as session:
        tx = Transaction(
            chain_id=CHAIN,
            tx_hash=JOB_TX_HASH,
            block_height=100,
            sender="0x" + "aa" * 20,
            recipient="ai_service",
            payload={"job_id": job_id, "job_type": "text", "prompt": "hi", "payment": 1.0},
            type="AI_JOB",
            status=status,
            nonce=1,
        )
        session.add(tx)
        session.commit()
        session.refresh(tx)
        return tx


def _tx_row(engine) -> Transaction:
    with Session(engine) as session:
        return session.exec(select(Transaction).where(Transaction.tx_hash == JOB_TX_HASH)).one()


def _cancellation_rows(engine) -> list[AIJobCancellation]:
    with Session(engine) as session:
        return session.exec(select(AIJobCancellation)).all()


@pytest.mark.asyncio
async def test_cancel_writes_service_row_and_leaves_sealed_tx_untouched(monkeypatch):
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)
    seeded = _seed_job(engine, status="pending")
    sealed_payload = dict(seeded.payload)

    result = ai_services.ai_cancel_job(JOB_ID)

    assert result["status"] == "cancelled"
    rows = _cancellation_rows(engine)
    assert len(rows) == 1 and rows[0].job_id == JOB_ID and rows[0].tx_hash == JOB_TX_HASH
    tx = _tx_row(engine)
    assert tx.status == "pending" and tx.payload == sealed_payload


@pytest.mark.asyncio
async def test_second_cancel_refuses(monkeypatch):
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)
    _seed_job(engine, status="pending")

    ai_services.ai_cancel_job(JOB_ID)
    with pytest.raises(HTTPException) as exc:
        ai_services.ai_cancel_job(JOB_ID)

    assert exc.value.status_code == 400 and "cancelled" in exc.value.detail
    assert len(_cancellation_rows(engine)) == 1


@pytest.mark.asyncio
async def test_completed_job_refuses(monkeypatch):
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)
    _seed_job(engine, status="completed")

    with pytest.raises(HTTPException) as exc:
        ai_services.ai_cancel_job(JOB_ID)

    assert exc.value.status_code == 400 and "completed" in exc.value.detail
    assert _cancellation_rows(engine) == []


@pytest.mark.asyncio
async def test_unknown_job_404s(monkeypatch):
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)

    with pytest.raises(HTTPException) as exc:
        ai_services.ai_cancel_job("nope")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cancel_overlay_reaches_list_get_and_stats(monkeypatch):
    engine = _engine()
    _bind_session_scope(monkeypatch, engine)
    _seed_job(engine, status="pending")

    ai_services.ai_cancel_job(JOB_ID)

    listed = ai_services.ai_list_jobs()
    assert listed["jobs"][0]["status"] == "cancelled"
    cancelled_only = ai_services.ai_list_jobs(status="cancelled")
    assert len(cancelled_only["jobs"]) == 1
    pending_only = ai_services.ai_list_jobs(status="pending")
    assert pending_only["jobs"] == []

    got = ai_services.ai_get_job(JOB_ID)
    assert got["job"]["status"] == "cancelled"

    stats = ai_services.ai_stats()
    assert stats["status_breakdown"] == {"cancelled": 1}
