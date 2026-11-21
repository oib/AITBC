"""#2402: ``POST /v1/jobs/{id}/accept`` reconciles a not-yet-settled release
in-request instead of answering 502 on the first "did not settle".

Round-5 evidence: three jobs in a row returned 502 "the escrow release did
not settle on-chain" on first accept and released on a manual retry seconds
later — the first call's tx was still sealing (or its submit response was
lost). The accept path now re-runs the idempotent release a bounded number
of times; the node's sealed+mempool dedup returns the in-flight hash rather
than double-submitting, so each retry is also the reconciliation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.routers import client as client_router
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.payments.acceptance import PENDING_ACCEPTANCE
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobCreate


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


def _acceptable_job(job_service, db_session):
    """A completed job whose payment awaits acceptance and whose receipt
    passes the computation-correctness gate."""
    req = JobCreate(
        payload={"type": "inference", "prompt": "test prompt"},
        ttl_seconds=900,
        payment_amount=Decimal("5"),
        payment_currency="AITBC",
    )
    job = job_service.create_job(client_id="client1", req=req)
    payment = JobPayment(
        job_id=job.id,
        amount=Decimal("5"),
        currency="AITBC",
        payment_method="aitbc_token",
        status=PENDING_ACCEPTANCE,
        meta_data={"provider_address": "0x" + "a" * 40},
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    job.state = "COMPLETED"
    job.completed_at = datetime.now(UTC)
    job.payment_id = payment.id
    job.payment_status = PENDING_ACCEPTANCE
    job.receipt_id = "r-accept-2402"
    job.receipt = {"computation_correct": True, "zk_status": "not_required"}
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job, payment


@pytest.fixture(autouse=True)
def _fast_reconcile(monkeypatch):
    monkeypatch.setattr(client_router, "_ACCEPT_RELEASE_RETRIES", 3)
    monkeypatch.setattr(client_router, "_ACCEPT_RELEASE_POLL_SECONDS", 0)


@pytest.mark.asyncio
async def test_accept_retries_release_until_it_settles(db_session, job_service, monkeypatch):
    """First release answer False (seal latency), second reconciles → 200 path."""
    job, _payment = _acceptable_job(job_service, db_session)
    calls = []

    async def flaky_release(self, client_id, job_id, payment_id, reason=None):
        calls.append(payment_id)
        return len(calls) >= 2

    monkeypatch.setattr(PaymentService, "release_payment", flaky_release)

    view = await client_router._accept_job_impl(job.id, db_session, {"sub": "client1"})

    assert len(calls) == 2
    assert view.job_id == job.id


@pytest.mark.asyncio
async def test_accept_502_only_after_retries_exhausted(db_session, job_service, monkeypatch):
    job, _payment = _acceptable_job(job_service, db_session)
    calls = []

    async def never_settles(self, client_id, job_id, payment_id, reason=None):
        calls.append(payment_id)
        return False

    monkeypatch.setattr(PaymentService, "release_payment", never_settles)

    with pytest.raises(HTTPException) as excinfo:
        await client_router._accept_job_impl(job.id, db_session, {"sub": "client1"})

    assert excinfo.value.status_code == 502
    assert "did not settle" in excinfo.value.detail
    # 1 initial attempt + _ACCEPT_RELEASE_RETRIES reconciles
    assert len(calls) == 1 + client_router._ACCEPT_RELEASE_RETRIES


@pytest.mark.asyncio
async def test_accept_stops_retrying_once_payment_leaves_held_set(db_session, job_service, monkeypatch):
    """settlement_failed is definitive — no point burning reconcile calls."""
    job, payment = _acceptable_job(job_service, db_session)
    calls = []

    async def fails_terminally(self, client_id, job_id, payment_id, reason=None):
        calls.append(payment_id)
        payment.status = "settlement_failed"
        db_session.add(payment)
        db_session.commit()
        return False

    monkeypatch.setattr(PaymentService, "release_payment", fails_terminally)

    with pytest.raises(HTTPException) as excinfo:
        await client_router._accept_job_impl(job.id, db_session, {"sub": "client1"})

    assert excinfo.value.status_code == 502
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_accept_treats_released_during_reconcile_as_success(db_session, job_service, monkeypatch):
    """#2462: a concurrent accept retry or the acceptance sweeper can settle
    the escrow while this loop is still polling — release_payment then
    answers False (the row is no longer held) but the payment is released.
    The route must answer 200, not a false 502."""
    job, payment = _acceptable_job(job_service, db_session)
    calls = []

    async def settles_elsewhere(self, client_id, job_id, payment_id, reason=None):
        calls.append(payment_id)
        payment.status = "released"
        db_session.add(payment)
        db_session.commit()
        return False

    monkeypatch.setattr(PaymentService, "release_payment", settles_elsewhere)

    view = await client_router._accept_job_impl(job.id, db_session, {"sub": "client1"})

    assert view.job_id == job.id
    db_session.refresh(job)
    assert job.payment_status == "released"
    # The loop observed the released row on the first reconcile pass and
    # stopped — no further release calls were burned.
    assert len(calls) == 1
