"""#3014 AUDIT-EVM-PENDING-ATTACH-1: recovery for the interrupted EVM attach.

``create_payment`` commits the pending ``JobPayment`` before
``_route_escrow`` stages the receipt hash and ``_sync_job_payment`` writes
``job.payment_id``. A crash in that window leaves a funded-but-unlinked
row: ``evm_payment_sweeper`` joined through ``Job.payment_id`` (invisible),
and ``live_payment_for_job`` returned the pending row without resuming
verification.

Pins cover: pre-commit staging (the committed row is self-describing),
sweeper discovery + attach of the unlinked row, single-payment
arbitration, and the ``create_payment`` retry resume — including the
pre-staging orphan shape where the buyer's retry resubmits the same
receipt hash (no new spend).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from aitbc.market.energy_pricing import EnergyQuote, FeeModel, SettlementRoute
from aitbc.market.evm_rental_receipt import AGREEMENT_STARTED_TOPIC0
from aitbc_shared import JobPayment
from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.evm_payment_sweeper import EvmPaymentVerifySweeper
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobPaymentCreate

CONTRACT = "0xAIPowerRental00000000000000000000000001"
CHAIN_ID = 11155111
TX_HASH = "0xfeedface"
STORED_HASH = "0xstoredhash"
AGREEMENT_ID = 42

_SVC = "coordinator_api.contexts.payments.services.payments"


def _minimal_quote(job_id: str = "job-evm") -> EnergyQuote:
    now = 1_700_000_000
    return EnergyQuote(
        domain="aitbc-energy",
        chain_id="ait-test",
        settlement_asset="AIT",
        settlement_unit_scale=10**18,
        buyer="0xBuyer0000000000000000000000000000000001",
        provider="0xProvider000000000000000000000000000001",
        job_id=job_id,
        quote_id="quote-evm",
        settlement_route=SettlementRoute.EVM,
        resource_id="gpu-1",
        model_id="model-a",
        gpu_count=1,
        duration_seconds=3600,
        eur_per_kwh_scaled=10**18,
        tbp_watts=300,
        ait_per_eur_scaled=10**18,
        rate_version=1,
        rate_observed_at=now,
        rate_source_kind="test",
        profile_revision=1,
        evm_chain_id=CHAIN_ID,
        evm_contract=CONTRACT,
        fee_model=FeeModel.BUYER_PAYS_ON_TOP,
        issued_at=now,
        expires_at=now + 300,
        principal_units=10**18,
        net_energy_floor_units=10**18,
    )


def _agreement_log(agreement_id: int) -> dict:
    topic1 = "0x" + agreement_id.to_bytes(32, "big").hex()
    return {
        "address": CONTRACT,
        "topics": [AGREEMENT_STARTED_TOPIC0, topic1],
        "data": "0x",
    }


def _confirmed_receipt(agreement_id: int = AGREEMENT_ID) -> dict:
    return {
        "status": 1,
        "to": CONTRACT.lower(),
        "chainId": CHAIN_ID,
        "log_entries": [_agreement_log(agreement_id)],
    }


def _evm_meta(quote: EnergyQuote, *, staged: bool = True, tx_hash: str = TX_HASH) -> dict:
    """Committed-row meta. ``staged=False`` models the pre-#3014 shape:
    ``energy_quote`` survives (written before the pending commit) but the
    ``evm_*`` receipt binding does not."""
    meta = {
        "energy_quote": quote.to_dict(include_signature=True),
        "energy_settlement_route": "evm",
        "energy_is_protected": True,
    }
    if staged:
        meta.update(
            {
                "evm_tx_hash": tx_hash,
                "evm_chain_id": CHAIN_ID,
                "evm_contract": CONTRACT,
                "evm_agreement_id": AGREEMENT_ID,
            }
        )
    return meta


def _seed_job(session: Session, *, payment_id: str | None, job_id: str = "job-evm") -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state="QUEUED",
        payload={"type": "inference", "model": "linear-1"},
        constraints={},
        payment_id=payment_id,
        payment_status=None,
        requested_at=datetime.now(UTC) - timedelta(seconds=600),
        expires_at=datetime.now(UTC) + timedelta(seconds=600),
    )
    session.add(job)
    session.commit()
    return job


def _seed_payment(
    session: Session,
    *,
    job_id: str = "job-evm",
    payment_id: str = "pay-evm",
    staged: bool = True,
    tx_hash: str = TX_HASH,
    created_at: datetime | None = None,
) -> JobPayment:
    quote = _minimal_quote(job_id)
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id="client-1",
        amount=Decimal("0.001"),
        currency="AITBC",
        status="pending",
        payment_method="evm",
        escrowed_at=None,
        created_at=created_at or (datetime.now(UTC) - timedelta(seconds=300)),
        meta_data=_evm_meta(quote, staged=staged, tx_hash=tx_hash),
    )
    session.add(payment)
    session.commit()
    return payment


def _payment_data(job_id: str, *, tx_hash: str = TX_HASH, agreement_id: int = AGREEMENT_ID) -> JobPaymentCreate:
    return JobPaymentCreate(
        job_id=job_id,
        amount=Decimal("0.001"),
        currency="AITBC",
        payment_method="evm",
        protected=True,
        energy_quote=_minimal_quote(job_id).to_dict(include_signature=True),
        evm_tx_hash=tx_hash,
        evm_agreement_id=agreement_id,
    )


def _rpc_settings():
    return patch(
        f"{_SVC}.settings",
        **{"eth_rpc_url": "http://127.0.0.1:8545", "energy_pricing_chain_id": CHAIN_ID},
    )


def _patched_receipt(receipt):
    return patch("aitbc.ethereum_rpc.EthereumRPCClient.get_transaction_receipt", return_value=receipt)


# ---------------------------------------------------------------------------
# Sweeper discovery + attach
# ---------------------------------------------------------------------------


def test_sweeper_recovers_unlinked_pending_evm_payment(db_engine) -> None:
    """The interrupted-attach row: job.payment_id was never written, so the
    old Job.payment_id join made it invisible. The payment's own job_id is
    the binding; on confirm the sweeper completes the attach."""
    with Session(db_engine) as session:
        _seed_job(session, payment_id=None)
        _seed_payment(session)
    with Session(db_engine) as session:
        sweeper = EvmPaymentVerifySweeper(session_factory=lambda: session, min_age_seconds=0)
        with _rpc_settings(), _patched_receipt(_confirmed_receipt()):
            counts = asyncio.run(sweeper.run_once())
        assert counts["confirmed"] == 1
        job = session.get(Job, "job-evm")
        payment = session.get(JobPayment, "pay-evm")
        assert payment.status == "confirmed"
        assert job.payment_id == "pay-evm"
        assert job.payment_status == "confirmed"


def test_sweeper_skips_job_bound_to_different_payment(db_engine) -> None:
    """Single-payment arbitration: a job already linked to another payment
    is not this row's to recover."""
    with Session(db_engine) as session:
        _seed_job(session, payment_id="pay-other")
        _seed_payment(session)
    with Session(db_engine) as session:
        sweeper = EvmPaymentVerifySweeper(session_factory=lambda: session, min_age_seconds=0)
        with _rpc_settings(), _patched_receipt(_confirmed_receipt()) as m:
            counts = asyncio.run(sweeper.run_once())
        assert counts["candidates"] == 0
        assert m.call_count == 0
        assert session.get(Job, "job-evm").payment_id == "pay-other"


# ---------------------------------------------------------------------------
# create_payment resume
# ---------------------------------------------------------------------------


def _service(session: Session) -> PaymentService:
    return PaymentService(session)


def test_resume_confirms_and_attaches_unlinked_row(db_engine) -> None:
    """Buyer retry hits live_payment_for_job → resume verifies the stored
    receipt and finishes the attach — no second payment row, no new spend."""
    with Session(db_engine) as session:
        _seed_job(session, payment_id=None)
        _seed_payment(session, staged=True)
        service = _service(session)
        with _rpc_settings(), _patched_receipt(_confirmed_receipt()):
            returned = asyncio.run(service.create_payment("client-1", "job-evm", _payment_data("job-evm")))
        assert returned.id == "pay-evm"
        rows = session.execute(select(JobPayment).where(JobPayment.job_id == "job-evm")).scalars().all()
        assert [p.id for p in rows] == ["pay-evm"]
        job = session.get(Job, "job-evm")
        payment = session.get(JobPayment, "pay-evm")
        assert payment.status == "confirmed"
        assert job.payment_id == "pay-evm"
        assert job.payment_status == "confirmed"
        assert job.energy_quote_snapshot is not None


def test_resume_adopts_incoming_hash_on_pre_staging_orphan(db_engine) -> None:
    """The exact stranded shape: the pending row committed before evm_*
    staging existed, so meta has the quote but no receipt hash. The buyer's
    retry resubmits the SAME tx hash — adopt it once, verify, attach."""
    with Session(db_engine) as session:
        _seed_job(session, payment_id=None)
        _seed_payment(session, staged=False)
        service = _service(session)
        with _rpc_settings(), _patched_receipt(_confirmed_receipt()):
            returned = asyncio.run(service.create_payment("client-1", "job-evm", _payment_data("job-evm")))
        assert returned.id == "pay-evm"
        payment = session.get(JobPayment, "pay-evm")
        assert payment.status == "confirmed"
        assert payment.meta_data["evm_tx_hash"] == TX_HASH
        assert payment.meta_data["evm_agreement_id"] == AGREEMENT_ID
        job = session.get(Job, "job-evm")
        assert job.payment_id == "pay-evm"
        assert job.payment_status == "confirmed"


def test_resume_stored_hash_wins_over_different_incoming(db_engine) -> None:
    """Arbitration binds the ORIGINAL receipt: a retry carrying a different
    evm_tx_hash must not rebind the stored row — verification runs against
    the stored hash."""
    with Session(db_engine) as session:
        _seed_job(session, payment_id=None)
        _seed_payment(session, staged=True, tx_hash=STORED_HASH)
        service = _service(session)
        seen: list[str] = []

        def _receipt_for(hash_arg):
            seen.append(hash_arg)
            return _confirmed_receipt()

        with (
            _rpc_settings(),
            patch(
                "aitbc.ethereum_rpc.EthereumRPCClient.get_transaction_receipt",
                side_effect=_receipt_for,
            ),
        ):
            returned = asyncio.run(
                service.create_payment("client-1", "job-evm", _payment_data("job-evm", tx_hash="0xother", agreement_id=999))
            )
        assert returned.id == "pay-evm"
        assert seen == [STORED_HASH]
        payment = session.get(JobPayment, "pay-evm")
        assert payment.meta_data["evm_tx_hash"] == STORED_HASH
        assert payment.status == "confirmed"


def test_resume_unmined_receipt_stays_pending(db_engine) -> None:
    with Session(db_engine) as session:
        _seed_job(session, payment_id=None)
        _seed_payment(session, staged=True)
        service = _service(session)
        with _rpc_settings(), _patched_receipt(None):
            returned = asyncio.run(service.create_payment("client-1", "job-evm", _payment_data("job-evm")))
        assert returned.id == "pay-evm"
        payment = session.get(JobPayment, "pay-evm")
        assert payment.status == "pending"
        job = session.get(Job, "job-evm")
        assert job.payment_id is None


def test_resume_failed_receipt_marks_failed_and_raises(db_engine) -> None:
    bad = {"status": 0, "to": CONTRACT.lower(), "chainId": CHAIN_ID, "log_entries": []}
    with Session(db_engine) as session:
        _seed_job(session, payment_id=None)
        _seed_payment(session, staged=True)
        service = _service(session)
        with _rpc_settings(), _patched_receipt(bad):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(service.create_payment("client-1", "job-evm", _payment_data("job-evm")))
        assert exc.value.status_code == 422
        payment = session.get(JobPayment, "pay-evm")
        assert payment.status == "failed"
        job = session.get(Job, "job-evm")
        assert job.payment_status == "failed"


# ---------------------------------------------------------------------------
# Pre-commit staging
# ---------------------------------------------------------------------------


def test_pending_commit_carries_evm_binding(db_engine) -> None:
    """#3014 root cause: the pending row must commit WITH the receipt
    binding. Simulate the interruption — _route_escrow dies after the
    pending commit — and the surviving row must still be self-describing
    so the sweeper/resume can recover it."""
    with Session(db_engine) as session:
        _seed_job(session, payment_id=None)
        service = _service(session)
        quote = _minimal_quote("job-evm")

        def fake_resolve(j, jid, pd, meta):
            meta["energy_quote"] = quote.to_dict(include_signature=True)
            meta["energy_settlement_route"] = "evm"
            meta["energy_is_protected"] = True
            return Decimal("0.001"), quote

        service._resolve_payment_quote = fake_resolve
        service._route_escrow = AsyncMock(side_effect=RuntimeError("interrupted"))
        with pytest.raises(RuntimeError):
            asyncio.run(service.create_payment("client-1", "job-evm", _payment_data("job-evm")))
    with Session(db_engine) as session:
        payment = session.execute(select(JobPayment).where(JobPayment.job_id == "job-evm")).scalars().one()
        assert payment.status == "pending"
        assert payment.meta_data["evm_tx_hash"] == TX_HASH
        assert payment.meta_data["evm_agreement_id"] == AGREEMENT_ID
        assert payment.meta_data["evm_chain_id"] == CHAIN_ID
        assert payment.meta_data["evm_contract"] == CONTRACT
        job = session.get(Job, "job-evm")
        assert job.payment_id is None
