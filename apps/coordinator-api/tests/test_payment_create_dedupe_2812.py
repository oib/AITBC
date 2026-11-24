"""#2812: ``create_payment`` must not open a second escrow for a job that
already has a live payment.

``JobPayment.job_id`` is indexed, not unique, and the route-level
Idempotency-Key only dedupes identical keys — a retry with a fresh key (or
a plain duplicate POST) used to insert a second row, run a second escrow,
and leave ``GET /jobs/{id}/payment`` returning an arbitrary ``.first()``
row while settlement keyed on whichever row it found. These pins cover the
sequential duplicate, the terminal-state re-pay allowance, the stale
``pending`` orphan, the concurrent-create yield, and deterministic
``get_job_payment`` ordering.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, select

from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobPaymentCreate

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
NODE_WALLET = "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01"


@pytest.fixture
def payment_session(db_engine, monkeypatch) -> Session:
    monkeypatch.setenv("NODE_WALLET_ADDRESS", NODE_WALLET)
    with Session(db_engine) as session:
        yield session


def _job(session: Session, job_id: str = "job-dup") -> Job:
    job = Job(id=job_id, client_id="client-1", state="QUEUED", payload={})
    session.add(job)
    session.commit()
    return job


def _payment_data(job_id: str) -> JobPaymentCreate:
    return JobPaymentCreate(
        job_id=job_id,
        amount=Decimal("0.1"),
        currency="AITBC",
        payment_method="aitbc_token",
        buyer_address=BUYER,
        provider_address=PROVIDER,
        buyer_lock_signature="0xdeadbeef",
        buyer_lock_nonce=7,
    )


def _service(session: Session) -> PaymentService:
    service = PaymentService(session)

    async def fake_route_escrow(payment, payment_data, quote):
        payment.status = "escrowed"

    service._route_escrow = fake_route_escrow
    return service


def _payments(session: Session, job_id: str) -> list[JobPayment]:
    return list(session.execute(select(JobPayment).where(JobPayment.job_id == job_id)).scalars().all())


def test_second_create_returns_existing_live_payment(payment_session):
    job = _job(payment_session)
    service = _service(payment_session)

    first = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id)))
    second = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id)))

    assert second.id == first.id
    assert len(_payments(payment_session, job.id)) == 1


def test_create_after_failed_payment_is_allowed(payment_session):
    job = _job(payment_session)
    dead = JobPayment(job_id=job.id, amount=Decimal("0.1"), status="failed")
    payment_session.add(dead)
    payment_session.commit()

    service = _service(payment_session)
    created = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id)))

    assert created.id != dead.id
    assert created.status == "escrowed"
    assert len(_payments(payment_session, job.id)) == 2


def test_fresh_pending_payment_blocks_duplicate(payment_session):
    job = _job(payment_session)
    pending = JobPayment(job_id=job.id, amount=Decimal("0.1"), status="pending")
    payment_session.add(pending)
    payment_session.commit()

    service = _service(payment_session)
    service._route_escrow = AsyncMock(side_effect=AssertionError("must not escrow"))
    returned = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id)))

    assert returned.id == pending.id
    service._route_escrow.assert_not_called()
    assert len(_payments(payment_session, job.id)) == 1


def test_stale_pending_orphan_does_not_block(payment_session):
    job = _job(payment_session)
    orphan = JobPayment(
        job_id=job.id,
        amount=Decimal("0.1"),
        status="pending",
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    payment_session.add(orphan)
    payment_session.commit()

    service = _service(payment_session)
    created = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id)))

    assert created.id != orphan.id
    assert created.status == "escrowed"


def test_concurrent_create_loser_yields_to_earlier_pending(payment_session, monkeypatch):
    """Simulates the race window: the sibling's pending row commits after our
    pre-insert check but before our post-commit recheck. The earlier row
    wins; the loser deletes its pending row and returns the winner without
    ever reaching escrow."""
    job = _job(payment_session)
    winner = JobPayment(
        job_id=job.id,
        amount=Decimal("0.1"),
        status="pending",
        created_at=datetime.now(UTC) - timedelta(seconds=5),
    )
    payment_session.add(winner)
    payment_session.commit()

    service = _service(payment_session)
    # Pre-check saw nothing (sibling committed later); the post-commit
    # recheck must still see it.
    monkeypatch.setattr(service, "live_payment_for_job", lambda job_id: None)
    service._route_escrow = AsyncMock(side_effect=AssertionError("must not escrow"))

    returned = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id)))

    assert returned.id == winner.id
    service._route_escrow.assert_not_called()
    remaining = _payments(payment_session, job.id)
    assert [p.id for p in remaining] == [winner.id]


def test_earlier_live_payment_ignores_later_and_dead_siblings(payment_session):
    job = _job(payment_session)
    service = PaymentService(payment_session)
    now = datetime.now(UTC)
    dead = JobPayment(job_id=job.id, amount=Decimal("0.1"), status="failed")
    later = JobPayment(
        job_id=job.id,
        amount=Decimal("0.1"),
        status="escrowed",
        created_at=now + timedelta(seconds=10),
    )
    payment_session.add_all([dead, later])
    payment_session.commit()

    ours = JobPayment(job_id=job.id, amount=Decimal("0.1"), status="pending", created_at=now)
    payment_session.add(ours)
    payment_session.commit()

    # `later` sorts after us, `dead` is not live — nothing earlier exists.
    from coordinator_api.contexts.payments.services.payments_core import _payment_order_key

    assert service.earlier_live_payment(job.id, ours.id, _payment_order_key(ours)) is None


def test_get_job_payment_prefers_live_row_and_is_deterministic(payment_session):
    job = _job(payment_session)
    escrowed = JobPayment(
        job_id=job.id, amount=Decimal("0.1"), status="escrowed", created_at=datetime.now(UTC) - timedelta(minutes=5)
    )
    failed = JobPayment(job_id=job.id, amount=Decimal("0.1"), status="failed", created_at=datetime.now(UTC))
    payment_session.add_all([escrowed, failed])
    payment_session.commit()

    service = PaymentService(payment_session)
    got = service.get_job_payment("client-1", job.id)
    assert got is not None and got.id == escrowed.id


def test_get_job_payment_returns_latest_when_all_dead(payment_session):
    job = _job(payment_session)
    old_failed = JobPayment(
        job_id=job.id,
        amount=Decimal("0.1"),
        status="failed",
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    new_refunded = JobPayment(job_id=job.id, amount=Decimal("0.1"), status="refunded", created_at=datetime.now(UTC))
    payment_session.add_all([old_failed, new_refunded])
    payment_session.commit()

    service = PaymentService(payment_session)
    got = service.get_job_payment("client-1", job.id)
    assert got is not None and got.id == new_refunded.id
