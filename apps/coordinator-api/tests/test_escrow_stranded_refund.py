"""Tests for the stranded late-seal escrow refund sweeper (#2996).

A paid ``aitbc ai submit`` whose /v1/payments escrow-create response was lost
can still land the ESCROW_LOCK minutes later: the payment stays ``failed``
while the chain escrow reads locked — buyer funds stranded. The sweeper
point-reads the node's escrow record and refunds only live, unsettled locks.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlmodel import Session, select

from aitbc.exceptions import NetworkError
from aitbc_shared import JobPayment, PaymentEscrow
from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.payments.services.stuck_escrow_sweeper import (
    META_ESCROW_LOCK_TX_HASH,
    META_STRANDED_REFUND,
    StrandedEscrowRefundSweeper,
    _escrow_record_is_stranded,
    stranded_escrow_refund_sweeper_enabled,
)

_SWEEPER = "coordinator_api.contexts.payments.services.stuck_escrow_sweeper"


@pytest.fixture
def sweep_session(db_engine) -> Generator[Session]:
    with Session(db_engine) as session:
        yield session


def _make_failed_payment(
    session: Session,
    job_id: str,
    payment_id: str,
    *,
    payment_status: str = "failed",
    payment_method: str = "aitbc_token",
    updated_at: datetime | None = None,
    meta_data: dict | None = None,
    with_escrow_row: bool = False,
) -> tuple[Job, JobPayment]:
    """Create a job + payment row in the stranded-refund shape.

    Mirrors the live specimen: the payment was marked ``failed`` when the
    escrow-create response was lost, so ``escrowed_at`` stays NULL and no
    PaymentEscrow row exists unless the test asks for one.
    """
    client_id = "client-1"
    if updated_at is None:
        updated_at = datetime.now(UTC) - timedelta(seconds=3600)

    job = Job(
        id=job_id,
        client_id=client_id,
        state="FAILED",
        payload={"type": "inference", "model": "linear-1"},
        constraints={},
        payment_id=payment_id,
        payment_status=payment_status,
        requested_at=datetime.now(UTC) - timedelta(seconds=7200),
        expires_at=datetime.now(UTC) - timedelta(seconds=600),
    )
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id=client_id,
        amount=Decimal("0.1"),
        currency="AITBC",
        status=payment_status,
        payment_method=payment_method,
        escrowed_at=None,
        updated_at=updated_at,
        meta_data=meta_data or {"escrow_error_kind": "unavailable"},
    )
    session.add(job)
    session.add(payment)
    if with_escrow_row:
        session.add(
            PaymentEscrow(
                payment_id=payment_id,
                amount=Decimal("0.1"),
                currency="AITBC",
                address="",
                is_active=True,
                is_released=False,
                is_refunded=False,
            )
        )
    session.commit()
    return job, payment


def _locked_record(job_id: str, **overrides) -> dict:
    """The node's GET /rpc/escrow/{job_id} answer for a live locked escrow."""
    record = {
        "job_id": job_id,
        "contract_id": "0xcontract",
        "state": "funded",
        "status": "locked",
        "buyer": "0xbuyer",
        "provider": "0xprovider",
        "amount": "0.1",
        "released_amount": "0",
        "refunded_amount": "0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "released_at": None,
        "refunded_at": None,
        "release_tx_hash": None,
        "refund_tx_hash": None,
        "lock_tx_hash": "0xlockhash",
    }
    record.update(overrides)
    return record


def _chain_client(record=None, post_result=None, post_error=None) -> MagicMock:
    """Fake AsyncAITBCHTTPClient: .get serves the escrow record, .post the refund."""
    client = MagicMock()
    client.get = AsyncMock(return_value=record)
    if post_error is not None:
        client.post = AsyncMock(side_effect=post_error)
    else:
        client.post = AsyncMock(
            return_value=post_result if post_result is not None else {"success": True, "refund_tx_hash": "0xrefundtx"}
        )
    return client


def _run(sweeper: StrandedEscrowRefundSweeper, client: MagicMock):
    with patch(f"{_SWEEPER}.AsyncAITBCHTTPClient", return_value=client):
        return asyncio.run(sweeper.run_once())


@pytest.mark.unit
class TestStrandedEscrowRecordPredicate:
    """_escrow_record_is_stranded is the chain-truth gate; pins its edges."""

    def test_locked_record_is_stranded(self):
        assert _escrow_record_is_stranded(_locked_record("job-1")) is True

    @pytest.mark.parametrize(
        "record",
        [
            None,
            {},
            _locked_record("job-1", state="released", released_at="2026-01-02T00:00:00+00:00"),
            _locked_record("job-1", state="refunded", refunded_at="2026-01-02T00:00:00+00:00", refund_tx_hash="0xr"),
            _locked_record("job-1", refund_tx_hash="0xr"),
            _locked_record("job-1", released_amount="0.05"),
            _locked_record("job-1", state="job_completed"),
            _locked_record("job-1", status="released"),
            # Settled-by-timestamp records _escrow_record_is_settled also catches.
            _locked_record("job-1", released_at="2026-01-02T00:00:00+00:00"),
        ],
    )
    def test_non_stranded_records(self, record):
        assert _escrow_record_is_stranded(record) is False


@pytest.mark.unit
class TestStrandedEscrowRefundSweeper:
    """End-to-end sweep behaviour against a fake chain client."""

    def test_refunds_failed_payment_with_locked_chain_escrow(self, sweep_session):
        """failed payment + chain locked → refund POSTed, row marked refunded."""
        _make_failed_payment(sweep_session, "job-strand-1", "pay-strand-1", with_escrow_row=True)
        client = _chain_client(record=_locked_record("job-strand-1"))
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        counts = _run(sweeper, client)

        assert counts["candidates"] == 1
        assert counts["stranded"] == 1
        assert counts["refunded"] == 1
        assert counts["failed"] == 0
        client.post.assert_awaited_once()
        args, kwargs = client.post.await_args
        assert args[0].endswith("/rpc/escrow/job-strand-1/refund")
        assert kwargs["json"]["reason"]

        sweep_session.expire_all()
        payment = sweep_session.get(JobPayment, "pay-strand-1")
        assert payment.status == "refunded"
        assert payment.refunded_at is not None
        assert payment.refund_transaction_hash == "0xrefundtx"
        assert payment.meta_data[META_STRANDED_REFUND] is True
        assert payment.meta_data[META_ESCROW_LOCK_TX_HASH] == "0xlockhash"
        job = sweep_session.get(Job, "job-strand-1")
        assert job.payment_status == "refunded"
        escrow = sweep_session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == "pay-strand-1")).scalars().one()
        assert escrow.is_refunded is True
        assert escrow.is_active is False

    @pytest.mark.parametrize(
        "record",
        [
            None,  # no escrow on chain — nothing was ever locked
            _locked_record("job-x", state="released", released_at="2026-01-02T00:00:00+00:00"),
            _locked_record("job-x", state="refunded", refunded_at="2026-01-02T00:00:00+00:00"),
            _locked_record("job-x", released_amount="0.1"),
        ],
    )
    def test_failed_payment_with_settled_or_absent_escrow_is_untouched(self, sweep_session, record):
        """Chain says refunded/released/absent/paid-out → no refund POST, row stays failed."""
        _make_failed_payment(sweep_session, "job-settled", "pay-settled", meta_data={})
        client = _chain_client(record=record)
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        counts = _run(sweeper, client)

        assert counts["candidates"] == 1
        assert counts["stranded"] == 0
        assert counts["refunded"] == 0
        client.post.assert_not_awaited()
        sweep_session.expire_all()
        assert sweep_session.get(JobPayment, "pay-settled").status == "failed"

    def test_payment_younger_than_grace_is_skipped(self, sweep_session):
        """A failure inside the grace window may still be mid-recovery; skip it."""
        _make_failed_payment(
            sweep_session,
            "job-young",
            "pay-young",
            updated_at=datetime.now(UTC) - timedelta(seconds=60),
        )
        client = _chain_client(record=_locked_record("job-young"))
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        counts = _run(sweeper, client)

        assert counts["candidates"] == 0
        client.get.assert_not_awaited()
        client.post.assert_not_awaited()
        sweep_session.expire_all()
        assert sweep_session.get(JobPayment, "pay-young").status == "failed"

    @pytest.mark.parametrize("held_status", ["escrowed", "pending_acceptance", "disputed", "settlement_failed"])
    def test_non_failed_payment_with_locked_escrow_is_untouched(self, sweep_session, held_status):
        """Held payments belong to StuckEscrowSweeper; this pass never touches them."""
        _make_failed_payment(sweep_session, f"job-held-{held_status}", f"pay-held-{held_status}", payment_status=held_status)
        client = _chain_client(record=_locked_record(f"job-held-{held_status}"))
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        counts = _run(sweeper, client)

        assert counts["candidates"] == 0
        client.post.assert_not_awaited()
        sweep_session.expire_all()
        assert sweep_session.get(JobPayment, f"pay-held-{held_status}").status == held_status

    def test_non_token_payment_is_untouched(self, sweep_session):
        """EVM/other-method failures never reach the AITBC escrow refund path."""
        _make_failed_payment(sweep_session, "job-evm", "pay-evm", payment_method="evm")
        client = _chain_client(record=_locked_record("job-evm"))
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        counts = _run(sweeper, client)

        assert counts["candidates"] == 0
        client.post.assert_not_awaited()

    def test_second_run_after_refund_posts_nothing(self, sweep_session):
        """Idempotent: once the row is refunded it leaves the candidate set."""
        _make_failed_payment(sweep_session, "job-once", "pay-once")
        client = _chain_client(record=_locked_record("job-once"))
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        first = _run(sweeper, client)
        second = _run(sweeper, client)

        assert first["refunded"] == 1
        assert second["candidates"] == 0
        assert client.post.await_count == 1

    def test_cas_loser_does_not_double_mark(self, sweep_session):
        """A worker that loses the status CAS reports skipped, not refunded."""
        _make_failed_payment(sweep_session, "job-cas", "pay-cas")
        client = _chain_client(record=_locked_record("job-cas"))
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        # Simulate the other worker winning between the chain POST and the
        # local write by moving the row first.
        real_mark = sweeper._mark_stranded_refunded

        def _mark_then_race(session, payment, job, tx_hash, record):
            raced = session.get(JobPayment, payment.id)
            raced.status = "released"
            session.add(raced)
            session.commit()
            return real_mark(session, payment, job, tx_hash, record)

        with patch.object(sweeper, "_mark_stranded_refunded", side_effect=_mark_then_race):
            counts = _run(sweeper, client)

        assert counts["refunded"] == 0
        assert counts["skipped"] == 1
        sweep_session.expire_all()
        payment = sweep_session.get(JobPayment, "pay-cas")
        assert payment.status == "released"

    def test_425_deferral_keeps_payment_failed(self, sweep_session):
        """A 'lock not yet sealed' refusal is retried next sweep, never marked."""
        _make_failed_payment(sweep_session, "job-425", "pay-425")
        request = httpx.Request("POST", "http://rpc.test/rpc/escrow/job-425/refund")
        response = httpx.Response(425, request=request, json={"detail": "lock not yet sealed"})
        status_error = httpx.HTTPStatusError("425", request=request, response=response)
        error = NetworkError("HTTP 425")
        error.__cause__ = status_error
        client = _chain_client(record=_locked_record("job-425"), post_error=error)
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        counts = _run(sweeper, client)

        assert counts["deferred"] == 1
        assert counts["refunded"] == 0
        sweep_session.expire_all()
        assert sweep_session.get(JobPayment, "pay-425").status == "failed"

    def test_refund_post_refusal_keeps_payment_failed(self, sweep_session):
        """success:false from the node is a failure, not a mark."""
        _make_failed_payment(sweep_session, "job-refused", "pay-refused")
        client = _chain_client(record=_locked_record("job-refused"), post_result={"success": False, "message": "no"})
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        counts = _run(sweeper, client)

        assert counts["failed"] == 1
        assert counts["refunded"] == 0
        sweep_session.expire_all()
        assert sweep_session.get(JobPayment, "pay-refused").status == "failed"

    def test_chain_read_error_is_counted_failed(self, sweep_session):
        """A transport failure on the point-read must not read as 'no escrow'."""
        _make_failed_payment(sweep_session, "job-rpcerr", "pay-rpcerr")
        client = _chain_client()
        client.get = AsyncMock(side_effect=NetworkError("connection refused"))
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        counts = _run(sweeper, client)

        assert counts["failed"] == 1
        assert counts["stranded"] == 0
        client.post.assert_not_awaited()

    def test_meta_data_without_escrow_error_kind_is_still_a_candidate(self, sweep_session):
        """The chain record is the truth — escrow_error_kind is not required."""
        _make_failed_payment(sweep_session, "job-nometa", "pay-nometa", meta_data={})
        client = _chain_client(record=_locked_record("job-nometa"))
        sweeper = StrandedEscrowRefundSweeper(session_factory=lambda: sweep_session, grace_seconds=900)

        counts = _run(sweeper, client)

        assert counts["refunded"] == 1

    def test_enabled_by_default(self):
        old = os.environ.pop("COORDINATOR_STRANDED_ESCROW_SWEEP_ENABLED", None)
        try:
            assert stranded_escrow_refund_sweeper_enabled() is True
        finally:
            if old is not None:
                os.environ["COORDINATOR_STRANDED_ESCROW_SWEEP_ENABLED"] = old
