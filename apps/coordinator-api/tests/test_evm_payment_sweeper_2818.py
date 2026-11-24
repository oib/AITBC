"""Tests for the EVM payment re-verify sweeper (#2818)."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlmodel import Session

from aitbc.market.energy_pricing import FeeModel, SettlementRoute
from aitbc.market.evm_rental_receipt import AGREEMENT_STARTED_TOPIC0
from aitbc_shared import JobPayment
from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.evm_payment_sweeper import EvmPaymentVerifySweeper

CONTRACT = "0xAIPowerRental00000000000000000000000001"
CHAIN_ID = 11155111
TX_HASH = "0xfeedface"
AGREEMENT_ID = 42

_SVC = "coordinator_api.contexts.payments.services.payments"


def _minimal_quote():
    from aitbc.market.energy_pricing import EnergyQuote

    now = 1_700_000_000
    return EnergyQuote(
        domain="aitbc-energy",
        chain_id="ait-test",
        settlement_asset="AIT",
        settlement_unit_scale=10**18,
        buyer="0xBuyer0000000000000000000000000000000001",
        provider="0xProvider000000000000000000000000000001",
        job_id="job-evm",
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


@pytest.fixture
def sweep_session(db_engine) -> Generator[Session]:
    with Session(db_engine) as session:
        yield session


def _seed_evm_payment(
    session: Session,
    *,
    job_id: str = "job-evm",
    payment_id: str = "pay-evm",
    payment_status: str = "pending",
    job_payment_status: str = "pending",
    with_snapshot: bool = True,
    created_at: datetime | None = None,
    meta_data: dict | None = None,
) -> tuple[Job, JobPayment]:
    quote = _minimal_quote()
    job = Job(
        id=job_id,
        client_id="client-1",
        state="QUEUED",
        payload={"type": "inference", "model": "linear-1"},
        constraints={},
        payment_id=payment_id,
        payment_status=job_payment_status,
        requested_at=datetime.now(UTC) - timedelta(seconds=600),
        expires_at=datetime.now(UTC) + timedelta(seconds=600),
        energy_quote_snapshot=quote.to_dict(include_signature=False) if with_snapshot else None,
    )
    meta = {
        "evm_tx_hash": TX_HASH,
        "evm_chain_id": CHAIN_ID,
        "evm_contract": CONTRACT,
        "evm_agreement_id": AGREEMENT_ID,
        "energy_settlement_route": "evm",
        "energy_is_protected": True,
    }
    meta.update(meta_data or {})
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id="client-1",
        amount=Decimal("0.001"),
        currency="AITBC",
        status=payment_status,
        payment_method="evm",
        escrowed_at=None,
        created_at=created_at or (datetime.now(UTC) - timedelta(seconds=300)),
        meta_data=meta,
    )
    session.add(job)
    session.add(payment)
    session.commit()
    return job, payment


def _patched_receipt(receipt):
    return patch("aitbc.ethereum_rpc.EthereumRPCClient.get_transaction_receipt", return_value=receipt)


def _rpc_settings():
    return patch(
        f"{_SVC}.settings",
        **{"eth_rpc_url": "http://127.0.0.1:8545", "energy_pricing_chain_id": CHAIN_ID},
    )


def test_confirmed_receipt_confirms_payment_and_job(sweep_session) -> None:
    _seed_evm_payment(sweep_session)
    receipt = {
        "status": 1,
        "to": CONTRACT.lower(),
        "chainId": CHAIN_ID,
        "log_entries": [_agreement_log(AGREEMENT_ID)],
    }
    sweeper = EvmPaymentVerifySweeper(session_factory=lambda: sweep_session, min_age_seconds=0)
    with _rpc_settings(), _patched_receipt(receipt):
        counts = asyncio.run(sweeper.run_once())
    assert counts["confirmed"] == 1
    assert sweep_session.get(JobPayment, "pay-evm").status == "confirmed"
    assert sweep_session.get(Job, "job-evm").payment_status == "confirmed"


def test_unmined_receipt_stays_pending(sweep_session) -> None:
    _seed_evm_payment(sweep_session)
    sweeper = EvmPaymentVerifySweeper(session_factory=lambda: sweep_session, min_age_seconds=0)
    with _rpc_settings(), _patched_receipt(None):
        counts = asyncio.run(sweeper.run_once())
    assert counts["pending"] == 1
    payment = sweep_session.get(JobPayment, "pay-evm")
    assert payment.status == "pending"


def test_failed_receipt_marks_payment_and_job_failed(sweep_session) -> None:
    _seed_evm_payment(sweep_session)
    receipt = {"status": 0, "to": CONTRACT.lower(), "chainId": CHAIN_ID, "log_entries": []}
    sweeper = EvmPaymentVerifySweeper(session_factory=lambda: sweep_session, min_age_seconds=0)
    with _rpc_settings(), _patched_receipt(receipt):
        counts = asyncio.run(sweeper.run_once())
    assert counts["failed"] == 1
    assert sweep_session.get(JobPayment, "pay-evm").status == "failed"
    assert sweep_session.get(Job, "job-evm").payment_status == "failed"


def test_non_evm_and_hashless_payments_are_not_candidates(sweep_session) -> None:
    _seed_evm_payment(sweep_session, payment_id="pay-evm")
    # A pending non-EVM payment and an EVM payment without a tx hash.
    job2 = Job(
        id="job-plain",
        client_id="client-1",
        state="QUEUED",
        payload={"type": "inference"},
        constraints={},
        payment_id="pay-plain",
        payment_status="pending",
        requested_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(seconds=600),
    )
    plain = JobPayment(
        id="pay-plain",
        job_id="job-plain",
        client_id="client-1",
        amount=Decimal("0.001"),
        currency="AITBC",
        status="pending",
        payment_method="aitbc_token",
        created_at=datetime.now(UTC) - timedelta(seconds=300),
    )
    hashless = JobPayment(
        id="pay-hashless",
        job_id="job-evm",
        client_id="client-1",
        amount=Decimal("0.001"),
        currency="AITBC",
        status="pending",
        payment_method="evm",
        created_at=datetime.now(UTC) - timedelta(seconds=300),
        meta_data={"energy_is_protected": True},
    )
    sweep_session.add(job2)
    sweep_session.add(plain)
    sweep_session.add(hashless)
    sweep_session.commit()
    # The hashless row shares job-evm's payment_id slot? No — job.payment_id
    # points at pay-evm only; the hashless row simply has no join. Give it its
    # own job to exercise the meta filter instead.
    job3 = Job(
        id="job-hashless",
        client_id="client-1",
        state="QUEUED",
        payload={"type": "inference"},
        constraints={},
        payment_id="pay-hashless",
        payment_status="pending",
        requested_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(seconds=600),
    )
    hashless.job_id = "job-hashless"
    sweep_session.add(job3)
    sweep_session.commit()

    sweeper = EvmPaymentVerifySweeper(session_factory=lambda: sweep_session, min_age_seconds=0)
    with _rpc_settings(), _patched_receipt(None) as m:
        counts = asyncio.run(sweeper.run_once())
    assert counts["candidates"] == 1
    assert m.call_count == 1


def test_missing_quote_snapshot_is_skipped(sweep_session) -> None:
    _seed_evm_payment(sweep_session, with_snapshot=False)
    sweeper = EvmPaymentVerifySweeper(session_factory=lambda: sweep_session, min_age_seconds=0)
    with _rpc_settings(), _patched_receipt({"status": 1}) as m:
        counts = asyncio.run(sweeper.run_once())
    assert counts["skipped"] == 1
    assert m.call_count == 0
    payment = sweep_session.get(JobPayment, "pay-evm")
    assert payment.status == "pending"


def test_min_age_filters_fresh_payments(sweep_session) -> None:
    _seed_evm_payment(sweep_session, created_at=datetime.now(UTC))
    sweeper = EvmPaymentVerifySweeper(session_factory=lambda: sweep_session, min_age_seconds=3600)
    counts = asyncio.run(sweeper.run_once())
    assert counts["candidates"] == 0
