"""Tests for the stuck-escrow auto-refund sweeper."""

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
from coordinator_api.contexts.payments.acceptance import DISPUTED
from coordinator_api.contexts.payments.services.stuck_escrow_sweeper import (
    LOCK_ABSENT,
    LOCK_IN_MEMPOOL,
    LOCK_SEALED,
    META_REFUND_SKIPPED,
    META_UNSEALED_SINCE,
    REFUND_SKIPPED_NEVER_SEALED,
    StuckEscrowSweeper,
    stuck_escrow_sweeper_enabled,
)

_SWEEPER = "coordinator_api.contexts.payments.services.stuck_escrow_sweeper"


@pytest.fixture
def sweep_session(db_engine) -> Generator[Session]:
    with Session(db_engine) as session:
        yield session


def _make_job_and_payment(
    session: Session,
    job_id: str,
    payment_id: str,
    *,
    state: str = "CANCELED",
    payment_status: str = "escrowed",
    updated_at: datetime | None = None,
    meta_data: dict | None = None,
    window_seconds: int = 0,
) -> tuple[Job, JobPayment]:
    """Create a job/payment/escrow row for stuck-escrow tests."""
    client_id = "client-1"
    if updated_at is None:
        updated_at = datetime.now(UTC) - timedelta(seconds=300)

    job = Job(
        id=job_id,
        client_id=client_id,
        state=state,
        payload={"type": "inference", "model": "linear-1"},
        constraints={},
        payment_id=payment_id,
        payment_status=payment_status,
        requested_at=datetime.now(UTC) - timedelta(seconds=600),
        expires_at=datetime.now(UTC) + timedelta(seconds=600),
    )
    if meta_data and window_seconds > 0:
        opened_at = updated_at
        meta_data = dict(meta_data)
        meta_data["acceptance_opened_at"] = opened_at.isoformat()
        meta_data["acceptance_deadline"] = (opened_at + timedelta(seconds=window_seconds)).isoformat()

    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id=client_id,
        amount=Decimal("0.001"),
        currency="AITBC",
        status=payment_status,
        payment_method="aitbc_token",
        escrow_address="escrow_abc123",
        escrowed_at=updated_at,
        updated_at=updated_at,
        meta_data=meta_data or {},
    )
    escrow = PaymentEscrow(
        payment_id=payment_id,
        amount=Decimal("0.001"),
        currency="AITBC",
        address="escrow_address_for_payment",
        is_active=True,
        is_released=False,
        is_refunded=False,
    )
    session.add(job)
    session.add(payment)
    session.add(escrow)
    session.commit()
    return job, payment


def _mark_refunded(session: Session, payment_id: str, tx_hash: str | None) -> None:
    """Record a refund on the payment row (sync Session, called from the async fakes)."""
    payment = session.get(JobPayment, payment_id)
    if payment:
        payment.status = "refunded"
        payment.refund_transaction_hash = tx_hash
        payment.refunded_at = datetime.now(UTC)
        payment.updated_at = datetime.now(UTC)
        session.add(payment)
        session.commit()


def _fake_refund_with_hash(session: Session, tx_hash: str = "0xdeadbeef") -> AsyncMock:
    """Return an async callable that simulates a real, on-chain refund."""

    async def _refund(client_id: str, job_id: str, payment_id: str, reason: str, *, is_admin: bool = False) -> bool:
        _mark_refunded(session, payment_id, tx_hash)
        return True

    return AsyncMock(side_effect=_refund)


@pytest.mark.unit
class TestStuckEscrowSweeper:
    """StuckEscrowSweeper refunds held escrows for terminal job states."""

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_refunds_canceled_job(self, mock_service_cls, sweep_session):
        """A canceled job with an escrowed payment is refunded."""
        _make_job_and_payment(sweep_session, "job-cancel-1", "pay-cancel-1", state="CANCELED")

        mock_service = MagicMock()
        mock_service.refund_payment = _fake_refund_with_hash(sweep_session)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1
        assert counts["failed"] == 0
        mock_service.refund_payment.assert_called_once()

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_refunds_failed_job(self, mock_service_cls, sweep_session):
        """A failed job with an escrowed payment is refunded."""
        _make_job_and_payment(sweep_session, "job-fail-1", "pay-fail-1", state="FAILED")

        mock_service = MagicMock()
        mock_service.refund_payment = _fake_refund_with_hash(sweep_session)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_refunds_expired_job(self, mock_service_cls, sweep_session):
        """An expired job with an escrowed payment is refunded."""
        _make_job_and_payment(sweep_session, "job-expire-1", "pay-expire-1", state="EXPIRED")

        mock_service = MagicMock()
        mock_service.refund_payment = _fake_refund_with_hash(sweep_session)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_refunds_disputed_job(self, mock_service_cls, sweep_session):
        """A disputed payment older than the dispute grace period is refunded."""
        disputed_at = datetime.now(UTC) - timedelta(seconds=90000)
        _make_job_and_payment(
            sweep_session,
            "job-dispute-1",
            "pay-dispute-1",
            state="COMPLETED",
            payment_status=DISPUTED,
            meta_data={"disputed_at": disputed_at.isoformat()},
        )

        mock_service = MagicMock()
        mock_service.refund_payment = _fake_refund_with_hash(sweep_session)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 1

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_skips_recent_dispute(self, mock_service_cls, sweep_session):
        """A recent dispute is not refunded before the operator can rule."""
        disputed_at = datetime.now(UTC) - timedelta(seconds=60)
        _make_job_and_payment(
            sweep_session,
            "job-dispute-2",
            "pay-dispute-2",
            state="COMPLETED",
            payment_status=DISPUTED,
            meta_data={"disputed_at": disputed_at.isoformat()},
        )

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_skips_recent_cancel(self, mock_service_cls, sweep_session):
        """A recently canceled job is not refunded until the min-age passes."""
        _make_job_and_payment(
            sweep_session,
            "job-cancel-2",
            "pay-cancel-2",
            state="CANCELED",
            updated_at=datetime.now(UTC) - timedelta(seconds=10),
        )

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(
            StuckEscrowSweeper(
                session_factory=lambda: sweep_session,
                min_age_seconds=120,
            ).run_once()
        )

        assert counts["candidates"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_skips_released_payments(self, mock_service_cls, sweep_session):
        """A canceled job whose payment is already released is not a candidate."""
        _make_job_and_payment(sweep_session, "job-cancel-3", "pay-cancel-3", state="CANCELED", payment_status="released")

        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 0
        mock_service.refund_payment.assert_not_called()

    @patch("coordinator_api.contexts.payments.services.stuck_escrow_sweeper.PaymentService")
    def test_sweeper_downgrades_unbacked_refund_without_hash(self, mock_service_cls, sweep_session):
        """A refund with no on-chain hash is downgraded to failed."""
        _make_job_and_payment(sweep_session, "job-unbacked-1", "pay-unbacked-1", state="CANCELED")

        async def _fake_unbacked_refund(
            client_id: str, job_id: str, payment_id: str, reason: str, *, is_admin: bool = False
        ) -> bool:
            _mark_refunded(sweep_session, payment_id, None)
            return True

        mock_service = MagicMock()
        mock_service.refund_payment = AsyncMock(side_effect=_fake_unbacked_refund)
        mock_service_cls.return_value = mock_service

        counts = asyncio.run(StuckEscrowSweeper(session_factory=lambda: sweep_session).run_once())

        assert counts["candidates"] == 1
        assert counts["refunded"] == 0
        assert counts["failed"] == 1
        payment = sweep_session.get(JobPayment, "pay-unbacked-1")
        assert payment.status == "failed"
        assert payment.refund_transaction_hash is None

    def test_stuck_escrow_sweeper_enabled_default(self):
        """The stuck-escrow sweeper is enabled by default."""
        old = os.environ.pop("COORDINATOR_STUCK_ESCROW_SWEEP_ENABLED", None)
        try:
            assert stuck_escrow_sweeper_enabled() is True
        finally:
            if old is not None:
                os.environ["COORDINATOR_STUCK_ESCROW_SWEEP_ENABLED"] = old


def _rpc_refusal(status_code: int) -> NetworkError:
    """A NetworkError chained to the node's HTTP refusal, as AsyncAITBCHTTPClient raises it."""
    request = httpx.Request("POST", "http://rpc.test/rpc/escrow/job/refund")
    response = httpx.Response(
        status_code,
        request=request,
        json={"detail": "escrow lock for job_id=job is not yet sealed in a block (absent or still in mempool)"},
    )
    error = NetworkError(f"HTTP {status_code}")
    error.__cause__ = httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=response)
    return error


def _refund_raising(error: Exception) -> MagicMock:
    service = MagicMock()
    service.refund_payment = AsyncMock(side_effect=error)
    return service


def _unsealed_meta(seconds_ago: int) -> dict:
    return {META_UNSEALED_SINCE: (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()}


@pytest.mark.unit
class TestUnsealedLockGiveUp:
    """A refund deferred by 425 'lock not sealed' is retried only for a bounded time."""

    @patch(f"{_SWEEPER}.PaymentService")
    def test_first_425_stamps_and_keeps_the_payment_held(self, mock_service_cls, sweep_session):
        _make_job_and_payment(sweep_session, "job-425-first", "pay-425-first", state="EXPIRED")
        mock_service_cls.return_value = _refund_raising(_rpc_refusal(425))
        sweeper = StuckEscrowSweeper(session_factory=lambda: sweep_session)

        with patch.object(StuckEscrowSweeper, "_lock_presence", AsyncMock()) as presence:
            counts = asyncio.run(sweeper.run_once())

        assert counts["deferred"] == 1
        assert counts["failed"] == 0
        assert counts["demoted"] == 0
        presence.assert_not_called()
        sweep_session.expire_all()
        payment = sweep_session.get(JobPayment, "pay-425-first")
        assert payment.status == "escrowed"
        assert datetime.fromisoformat(payment.meta_data[META_UNSEALED_SINCE]) <= datetime.now(UTC)
        assert META_REFUND_SKIPPED not in payment.meta_data

    @patch(f"{_SWEEPER}.PaymentService")
    def test_425_inside_the_window_does_not_ask_the_node(self, mock_service_cls, sweep_session):
        _make_job_and_payment(sweep_session, "job-425-wait", "pay-425-wait", state="EXPIRED", meta_data=_unsealed_meta(600))
        mock_service_cls.return_value = _refund_raising(_rpc_refusal(425))
        sweeper = StuckEscrowSweeper(session_factory=lambda: sweep_session, unsealed_giveup_seconds=3600)

        with patch.object(StuckEscrowSweeper, "_lock_presence", AsyncMock()) as presence:
            counts = asyncio.run(sweeper.run_once())

        assert counts["deferred"] == 1
        presence.assert_not_called()
        sweep_session.expire_all()
        assert sweep_session.get(JobPayment, "pay-425-wait").status == "escrowed"

    @patch(f"{_SWEEPER}.PaymentService")
    def test_lock_absent_after_the_window_demotes_once(self, mock_service_cls, sweep_session):
        _make_job_and_payment(sweep_session, "job-425-gone", "pay-425-gone", state="EXPIRED", meta_data=_unsealed_meta(7200))
        service = _refund_raising(_rpc_refusal(425))
        mock_service_cls.return_value = service
        sweeper = StuckEscrowSweeper(session_factory=lambda: sweep_session, unsealed_giveup_seconds=3600)

        with patch.object(StuckEscrowSweeper, "_lock_presence", AsyncMock(return_value=(LOCK_ABSENT, "0xlock"))):
            counts = asyncio.run(sweeper.run_once())
            again = asyncio.run(sweeper.run_once())

        assert counts["demoted"] == 1
        assert counts["failed"] == 0
        sweep_session.expire_all()
        payment = sweep_session.get(JobPayment, "pay-425-gone")
        assert payment.status == "failed"
        assert payment.refund_transaction_hash is None
        assert payment.meta_data[META_REFUND_SKIPPED] == REFUND_SKIPPED_NEVER_SEALED
        assert sweep_session.get(Job, "job-425-gone").payment_status == "failed"
        escrow = sweep_session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == "pay-425-gone")).scalars().one()
        assert escrow.is_active is False
        assert escrow.is_refunded is False
        # The demoted payment is no longer a candidate, so the refund is not retried.
        assert again["candidates"] == 0
        service.refund_payment.assert_called_once()

    @pytest.mark.parametrize("presence", [LOCK_IN_MEMPOOL, LOCK_SEALED])
    @patch(f"{_SWEEPER}.PaymentService")
    def test_lock_still_known_to_the_node_is_not_demoted(self, mock_service_cls, presence, sweep_session):
        _make_job_and_payment(sweep_session, "job-425-pend", "pay-425-pend", state="EXPIRED", meta_data=_unsealed_meta(7200))
        mock_service_cls.return_value = _refund_raising(_rpc_refusal(425))
        sweeper = StuckEscrowSweeper(session_factory=lambda: sweep_session, unsealed_giveup_seconds=3600)

        with patch.object(StuckEscrowSweeper, "_lock_presence", AsyncMock(return_value=(presence, None))):
            counts = asyncio.run(sweeper.run_once())

        assert counts["deferred"] == 1
        assert counts["demoted"] == 0
        sweep_session.expire_all()
        payment = sweep_session.get(JobPayment, "pay-425-pend")
        assert payment.status == "escrowed"
        assert META_REFUND_SKIPPED not in payment.meta_data

    @patch(f"{_SWEEPER}.PaymentService")
    def test_unanswered_lock_probe_is_not_demoted(self, mock_service_cls, sweep_session):
        _make_job_and_payment(sweep_session, "job-425-rpc", "pay-425-rpc", state="EXPIRED", meta_data=_unsealed_meta(7200))
        mock_service_cls.return_value = _refund_raising(_rpc_refusal(425))
        sweeper = StuckEscrowSweeper(session_factory=lambda: sweep_session, unsealed_giveup_seconds=3600)

        probe = AsyncMock(side_effect=NetworkError("connection refused"))
        with patch.object(StuckEscrowSweeper, "_lock_presence", probe):
            counts = asyncio.run(sweeper.run_once())

        assert counts["deferred"] == 1
        assert counts["demoted"] == 0
        sweep_session.expire_all()
        assert sweep_session.get(JobPayment, "pay-425-rpc").status == "escrowed"

    @pytest.mark.parametrize("error", [_rpc_refusal(500), _rpc_refusal(409), RuntimeError("boom")])
    @patch(f"{_SWEEPER}.PaymentService")
    def test_other_refund_errors_behave_as_before(self, mock_service_cls, error, sweep_session):
        _make_job_and_payment(sweep_session, "job-err", "pay-err", state="EXPIRED", meta_data=_unsealed_meta(7200))
        mock_service_cls.return_value = _refund_raising(error)
        sweeper = StuckEscrowSweeper(session_factory=lambda: sweep_session, unsealed_giveup_seconds=3600)

        with patch.object(StuckEscrowSweeper, "_lock_presence", AsyncMock()) as presence:
            counts = asyncio.run(sweeper.run_once())

        assert counts["failed"] == 1
        assert counts["deferred"] == 0
        presence.assert_not_called()
        sweep_session.expire_all()
        payment = sweep_session.get(JobPayment, "pay-err")
        assert payment.status == "escrowed"
        assert META_REFUND_SKIPPED not in payment.meta_data

    def test_demotion_leaves_a_payment_another_worker_already_settled(self, sweep_session):
        """The second of two concurrent sweepers changes nothing."""
        job, _payment = _make_job_and_payment(sweep_session, "job-race", "pay-race", state="EXPIRED")
        # The other worker settled the payment after this one selected it.
        payment = sweep_session.get(JobPayment, "pay-race")
        payment.status = "refunded"
        payment.refund_transaction_hash = "0xrefund"
        sweep_session.add(payment)
        sweep_session.commit()

        demoted = StuckEscrowSweeper(session_factory=lambda: sweep_session)._demote_never_sealed(
            sweep_session, job, "pay-race", {}, datetime.now(UTC)
        )

        assert demoted is False
        sweep_session.expire_all()
        payment = sweep_session.get(JobPayment, "pay-race")
        assert payment.status == "refunded"
        assert META_REFUND_SKIPPED not in (payment.meta_data or {})
        assert sweep_session.get(Job, "job-race").payment_status == "escrowed"
        escrow = sweep_session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == "pay-race")).scalars().one()
        assert escrow.is_active is True


def _probe_client(mempool: object, record: object = None) -> MagicMock:
    async def _get_json(url: str) -> object:
        if "/rpc/mempool" in url:
            if isinstance(mempool, Exception):
                raise mempool
            return mempool
        if "/rpc/escrow/" in url:
            return record
        raise AssertionError(f"unexpected GET {url}")

    client = MagicMock()
    client.get_json = AsyncMock(side_effect=_get_json)
    return client


@pytest.mark.unit
class TestLockPresenceProbe:
    """_lock_presence answers sealed / mempool / absent and raises when it cannot tell."""

    def _probe(self, client: MagicMock, sealed_hash: str | None = None) -> tuple[str, str | None]:
        with (
            patch(f"{_SWEEPER}.AsyncAITBCHTTPClient", return_value=client),
            patch(f"{_SWEEPER}._lookup_chain_lock", AsyncMock(return_value=sealed_hash)),
        ):
            return asyncio.run(StuckEscrowSweeper()._lock_presence("job-p"))

    def test_sealed_lock(self):
        assert self._probe(_probe_client({"transactions": []}), sealed_hash="0xsealed")[0] == LOCK_SEALED

    def test_lock_in_mempool(self):
        pending = {"transactions": [{"type": "ESCROW_LOCK", "payload": {"job_id": "job-p"}}], "count": 1}
        assert self._probe(_probe_client(pending))[0] == LOCK_IN_MEMPOOL

    def test_absent_lock_names_the_recorded_hash(self):
        pending = {"transactions": [{"type": "TRANSFER", "payload": {"job_id": "other"}}], "count": 1}
        assert self._probe(_probe_client(pending, {"lock_tx_hash": "0xlock"})) == (LOCK_ABSENT, "0xlock")

    def test_absent_lock_without_an_escrow_record(self):
        client = MagicMock()

        async def _get_json(url: str) -> object:
            if "/rpc/escrow/" in url:
                raise NetworkError("HTTP 404")
            return {"transactions": [], "count": 0}

        client.get_json = AsyncMock(side_effect=_get_json)
        assert self._probe(client) == (LOCK_ABSENT, None)

    @pytest.mark.parametrize(
        "mempool",
        [
            {"transactions": [], "count": 0, "error": "mempool unavailable"},
            {"success": False, "transactions": [], "count": 0},
            {"count": 0},
            [],
            {"transactions": [{"payload": {}}] * 1000, "count": 1000},
            NetworkError("timeout"),
        ],
        ids=["error-key", "success-false", "no-list", "not-a-dict", "full-page", "transport"],
    )
    def test_unusable_mempool_answer_raises(self, mempool):
        with pytest.raises((RuntimeError, NetworkError)):
            self._probe(_probe_client(mempool))
