"""Tests for the escrow settlement reconciler."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from coordinator_api.contexts.payments.services.settlement_reconciler import (
    SettlementReconciler,
    reconciler_enabled,
)


@contextmanager
def _fake_session(jobs):
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = jobs
    yield session


def _factory(jobs):
    return lambda: _fake_session(jobs)


def _job(job_id="job-1", payment_id="pay-1"):
    return SimpleNamespace(
        id=job_id, client_id="client-1", payment_id=payment_id, payment_status="escrowed"
    )


def test_disabled_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("ESCROW_RECONCILER_ENABLED", raising=False)
    assert reconciler_enabled() is False
    monkeypatch.setenv("ESCROW_RECONCILER_ENABLED", "true")
    assert reconciler_enabled() is True
    monkeypatch.setenv("ESCROW_RECONCILER_ENABLED", "no")
    assert reconciler_enabled() is False


@pytest.mark.asyncio
async def test_successful_retry_marks_the_job_released():
    job = _job()
    reconciler = SettlementReconciler(session_factory=_factory([job]))

    with patch("coordinator_api.contexts.payments.services.payments.PaymentService") as svc:
        svc.return_value.release_payment = AsyncMock(return_value=True)
        counts = await reconciler.run_once()

    assert counts == {"retried": 1, "settled": 1, "failed": 0}
    assert job.payment_status == "released"


@pytest.mark.asyncio
async def test_failed_retry_leaves_the_job_escrowed():
    """A payout that still will not settle must stay escrowed, not be marked paid."""
    job = _job()
    reconciler = SettlementReconciler(session_factory=_factory([job]))

    with patch("coordinator_api.contexts.payments.services.payments.PaymentService") as svc:
        svc.return_value.release_payment = AsyncMock(return_value=False)
        counts = await reconciler.run_once()

    assert counts == {"retried": 1, "settled": 0, "failed": 1}
    assert job.payment_status == "escrowed"


@pytest.mark.asyncio
async def test_a_raising_job_does_not_abort_the_batch():
    first, second = _job("job-1"), _job("job-2")
    reconciler = SettlementReconciler(session_factory=_factory([first, second]))

    with patch("coordinator_api.contexts.payments.services.payments.PaymentService") as svc:
        svc.return_value.release_payment = AsyncMock(side_effect=[RuntimeError("rpc down"), True])
        counts = await reconciler.run_once()

    assert counts == {"retried": 2, "settled": 1, "failed": 1}
    assert first.payment_status == "escrowed"
    assert second.payment_status == "released"


@pytest.mark.asyncio
async def test_jobs_without_a_payment_are_skipped():
    reconciler = SettlementReconciler(session_factory=_factory([_job(payment_id=None)]))

    with patch("coordinator_api.contexts.payments.services.payments.PaymentService") as svc:
        svc.return_value.release_payment = AsyncMock(return_value=True)
        counts = await reconciler.run_once()

    assert counts == {"retried": 0, "settled": 0, "failed": 0}
    svc.return_value.release_payment.assert_not_awaited()
