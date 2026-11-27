"""#3066: ``POST /v1/payments`` must fund the job's agreed price, not a
caller-controlled amount.

``POST /v1/jobs`` validates ``payment_amount`` against the offer quote at
creation and stores it on ``job.payment_amount`` — but payment creation
returned ``payment_data.amount`` verbatim, so a buyer could escrow-pay
arbitrarily less than agreed and ``_sync_job_payment`` then overwrote the
agreed price with the funded one, erasing the evidence. These pins cover the
underfund repro, the exact-match control, overpayment refusal, the payee
binding (same defect class: the offer decides the provider), the unpriced-job
pricing act, and the agreed-price preservation on the job row.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobPaymentCreate

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
OTHER_PROVIDER = "0x1111111111111111111111111111111111111111"
NODE_WALLET = "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01"

AGREED = Decimal("100")


@pytest.fixture
def payment_session(db_engine, monkeypatch) -> Session:
    monkeypatch.setenv("NODE_WALLET_ADDRESS", NODE_WALLET)
    with Session(db_engine) as session:
        yield session


def _job(
    session: Session,
    job_id: str,
    payment_amount: Decimal | None = AGREED,
    provider_address: str | None = PROVIDER,
) -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state="QUEUED",
        payload={},
        payment_amount=payment_amount,
        payment_status="pending" if payment_amount else None,
        provider_address=provider_address,
    )
    session.add(job)
    session.commit()
    return job


def _payment_data(job_id: str, amount: Decimal, provider_address: str | None = PROVIDER) -> JobPaymentCreate:
    return JobPaymentCreate(
        job_id=job_id,
        amount=amount,
        currency="AITBC",
        payment_method="aitbc_token",
        buyer_address=BUYER,
        provider_address=provider_address,
        buyer_lock_signature="0xdeadbeef",
        buyer_lock_nonce=7,
    )


def _service(session: Session, captured: dict | None = None) -> PaymentService:
    service = PaymentService(session)

    async def fake_route_escrow(payment, payment_data, quote):
        if captured is not None:
            captured["provider_address"] = payment_data.provider_address
        payment.status = "escrowed"

    service._route_escrow = fake_route_escrow
    return service


def _live_payment(session: Session, job_id: str) -> JobPayment | None:
    return session.execute(select(JobPayment).where(JobPayment.job_id == job_id)).scalars().first()


def test_underfund_rejected_and_evidence_preserved(payment_session):
    """The audit repro: amount=0.0001 against a 100-AIT agreed price."""
    job = _job(payment_session, "job-under")
    service = _service(payment_session)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id, Decimal("0.0001"))))

    assert exc.value.status_code == 422
    assert _live_payment(payment_session, job.id) is None
    payment_session.refresh(job)
    assert job.payment_amount == AGREED


def test_exact_agreed_amount_escrows(payment_session):
    job = _job(payment_session, "job-exact")
    service = _service(payment_session)

    payment = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id, AGREED)))

    assert payment.status == "escrowed"
    assert payment.amount == AGREED
    payment_session.refresh(job)
    assert job.payment_amount == AGREED


def test_overpayment_rejected(payment_session):
    job = _job(payment_session, "job-over")
    service = _service(payment_session)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id, Decimal("100.00000001"))))

    assert exc.value.status_code == 422
    assert _live_payment(payment_session, job.id) is None


def test_agreed_price_rounds_to_payment_precision(payment_session):
    """A sub-8dp agreed price binds at the schema's own precision."""
    job = _job(payment_session, "job-precision", payment_amount=Decimal("1.234567891"))
    service = _service(payment_session)

    payment = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id, Decimal("1.23456789"))))

    assert payment.status == "escrowed"
    payment_session.refresh(job)
    # sqlite Numeric round-trips through float; compare at nanosecond scale.
    assert job.payment_amount is not None
    assert job.payment_amount.quantize(Decimal("0.000000001")) == Decimal("1.234567891")


def test_different_provider_rejected(payment_session):
    job = _job(payment_session, "job-payee")
    service = _service(payment_session)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id, AGREED, provider_address=OTHER_PROVIDER)))

    assert exc.value.status_code == 422
    assert _live_payment(payment_session, job.id) is None


def test_missing_provider_defaults_to_bound(payment_session):
    job = _job(payment_session, "job-payee-default")
    captured: dict = {}
    service = _service(payment_session, captured)

    payment = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id, AGREED, provider_address=None)))

    assert payment.status == "escrowed"
    assert captured["provider_address"] == PROVIDER


def test_provider_case_variant_accepted(payment_session):
    job = _job(payment_session, "job-payee-case")
    service = _service(payment_session)
    checksummed = PROVIDER  # already mixed-case; lower() is the same address

    payment = asyncio.run(
        service.create_payment("client-1", job.id, _payment_data(job.id, AGREED, provider_address=checksummed.lower()))
    )

    assert payment.status == "escrowed"


def test_unpriced_job_payment_sets_agreed_price(payment_session):
    """A job with no recorded price is priced by its first payment."""
    job = _job(payment_session, "job-unpriced", payment_amount=None, provider_address=None)
    service = _service(payment_session)

    payment = asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id, Decimal("0.5"), None)))

    assert payment.status == "escrowed"
    payment_session.refresh(job)
    assert job.payment_amount == Decimal("0.5")
