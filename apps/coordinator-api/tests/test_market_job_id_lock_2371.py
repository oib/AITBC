"""#2371: the coordinator must mirror ``market_job_id`` into the rebuilt
ESCROW_LOCK payload.

The buyer CLI signs a lock tx whose payload carries ``market_job_id`` (the
#2326 alias binding). ``/v1/payments`` previously dropped the field, so the
coordinator rebuilt a different canonical tx and the chain refused the
buyer signature (``403 Invalid transaction signature``) — every paid
transcribe submit failed escrow. These pins cover the three hops: schema →
meta_data → lock payload.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session

from aitbc_shared import JobPayment

from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobPaymentCreate

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
NODE_WALLET = "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01"
MARKET_JOB_ID = "ai_job_0123456789abcdef"


@pytest.fixture
def payment_session(db_engine, monkeypatch) -> Session:
    monkeypatch.setenv("NODE_WALLET_ADDRESS", NODE_WALLET)
    with Session(db_engine) as session:
        yield session


def _payment_data(job_id: str, **overrides) -> JobPaymentCreate:
    data = {
        "job_id": job_id,
        "amount": Decimal("0.1"),
        "currency": "AITBC",
        "payment_method": "aitbc_token",
        "buyer_address": BUYER,
        "provider_address": PROVIDER,
        "buyer_lock_signature": "0xdeadbeef",
        "buyer_lock_nonce": 7,
    }
    data.update(overrides)
    return JobPaymentCreate(**data)


def _payment(meta_data: dict | None) -> JobPayment:
    return JobPayment(
        job_id="job-mj",
        amount=Decimal("0.1"),
        currency="AITBC",
        payment_method="aitbc_token",
        meta_data=meta_data,
    )


def test_payment_meta_carries_market_job_id(payment_session):
    service = PaymentService(payment_session)
    meta = service._payment_meta(_payment_data("job-mj", market_job_id=MARKET_JOB_ID))
    assert meta["market_job_id"] == MARKET_JOB_ID


def test_payment_meta_omits_market_job_id_when_absent(payment_session):
    service = PaymentService(payment_session)
    assert "market_job_id" not in service._payment_meta(_payment_data("job-mj"))


def test_lock_tx_payload_mirrors_market_job_id(payment_session):
    service = PaymentService(payment_session)
    lock_tx, _ = service._build_escrow_lock_tx(_payment({"market_job_id": MARKET_JOB_ID}), BUYER, PROVIDER, 3)
    assert lock_tx["payload"]["market_job_id"] == MARKET_JOB_ID
    assert lock_tx["payload"]["action"] == "escrow_lock"
    assert lock_tx["payload"]["job_id"] == "job-mj"


def test_lock_tx_payload_unchanged_without_market_job_id(payment_session):
    """Payments without the binding must rebuild the pre-#2371 payload
    byte-for-byte — otherwise in-flight buyer signatures break again."""
    service = PaymentService(payment_session)
    lock_tx, _ = service._build_escrow_lock_tx(_payment(None), BUYER, PROVIDER, 3)
    assert "market_job_id" not in lock_tx["payload"]


def test_create_payment_rejects_market_job_id_mismatch(payment_session):
    """A payment may only bind the market job the coordinator job declared —
    otherwise the signed lock would authorize an alias token this job never
    asked for."""
    import asyncio

    from fastapi import HTTPException

    from coordinator_api.contexts.infrastructure.domain.job import Job

    job = Job(id="job-mismatch", client_id="client-1", state="QUEUED", payload={"market_job_id": "ai_job_real"})
    payment_session.add(job)
    payment_session.commit()

    service = PaymentService(payment_session)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.create_payment("client-1", job.id, _payment_data(job.id, market_job_id="ai_job_evil")))
    assert exc_info.value.status_code == 422
