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
    return SimpleNamespace(id=job_id, client_id="client-1", payment_id=payment_id, payment_status="escrowed")


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

    assert counts == {
        "retried": 1,
        "settled": 1,
        "failed": 0,
        "hash_ok": 0,
        "hash_readopted": 0,
        "hash_unbacked": 0,
        "hash_ambiguous": 0,
        "hash_unreachable": 0,
        "refund_hash_ok": 0,
        "refund_hash_readopted": 0,
        "refund_requeued": 0,
        "refund_hash_ambiguous": 0,
        "refund_hash_unreachable": 0,
    }
    assert job.payment_status == "released"


@pytest.mark.asyncio
async def test_failed_retry_leaves_the_job_escrowed():
    """A payout that still will not settle must stay escrowed, not be marked paid."""
    job = _job()
    reconciler = SettlementReconciler(session_factory=_factory([job]))

    with patch("coordinator_api.contexts.payments.services.payments.PaymentService") as svc:
        svc.return_value.release_payment = AsyncMock(return_value=False)
        counts = await reconciler.run_once()

    assert counts == {
        "retried": 1,
        "settled": 0,
        "failed": 1,
        "hash_ok": 0,
        "hash_readopted": 0,
        "hash_unbacked": 0,
        "hash_ambiguous": 0,
        "hash_unreachable": 0,
        "refund_hash_ok": 0,
        "refund_hash_readopted": 0,
        "refund_requeued": 0,
        "refund_hash_ambiguous": 0,
        "refund_hash_unreachable": 0,
    }
    assert job.payment_status == "escrowed"


@pytest.mark.asyncio
async def test_a_raising_job_does_not_abort_the_batch():
    first, second = _job("job-1"), _job("job-2")
    reconciler = SettlementReconciler(session_factory=_factory([first, second]))

    with patch("coordinator_api.contexts.payments.services.payments.PaymentService") as svc:
        svc.return_value.release_payment = AsyncMock(side_effect=[RuntimeError("rpc down"), True])
        counts = await reconciler.run_once()

    assert counts == {
        "retried": 2,
        "settled": 1,
        "failed": 1,
        "hash_ok": 0,
        "hash_readopted": 0,
        "hash_unbacked": 0,
        "hash_ambiguous": 0,
        "hash_unreachable": 0,
        "refund_hash_ok": 0,
        "refund_hash_readopted": 0,
        "refund_requeued": 0,
        "refund_hash_ambiguous": 0,
        "refund_hash_unreachable": 0,
    }
    assert first.payment_status == "escrowed"
    assert second.payment_status == "released"


@pytest.mark.asyncio
async def test_jobs_without_a_payment_are_skipped():
    reconciler = SettlementReconciler(session_factory=_factory([_job(payment_id=None)]))

    with patch("coordinator_api.contexts.payments.services.payments.PaymentService") as svc:
        svc.return_value.release_payment = AsyncMock(return_value=True)
        counts = await reconciler.run_once()

    assert counts == {
        "retried": 0,
        "settled": 0,
        "failed": 0,
        "hash_ok": 0,
        "hash_readopted": 0,
        "hash_unbacked": 0,
        "hash_ambiguous": 0,
        "hash_unreachable": 0,
        "refund_hash_ok": 0,
        "refund_hash_readopted": 0,
        "refund_requeued": 0,
        "refund_hash_ambiguous": 0,
        "refund_hash_unreachable": 0,
    }
    svc.return_value.release_payment.assert_not_awaited()


# --- #2483: released-payment tx-hash audit ---------------------------------


def _payment(tx_hash="0xrecorded", job_id="job-1", status="released"):
    from datetime import UTC, datetime, timedelta

    return SimpleNamespace(
        id="pay-1",
        job_id=job_id,
        status=status,
        transaction_hash=tx_hash,
        meta_data={},
        released_at=datetime.now(UTC) - timedelta(hours=1),
        updated_at=None,
    )


def _audit_factory(payments):
    @contextmanager
    def _factory():
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = payments
        yield session

    return _factory


class _FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class _FakeClient:
    """Routes GETs by URL suffix; ``routes`` maps substring -> _FakeResp or Exception."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.calls.append((url, params))
        for needle, outcome in self.routes.items():
            if needle in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        return _FakeResp(404)


def _patch_rpc_and_client(routes):
    client = _FakeClient(routes)
    settings = SimpleNamespace(blockchain_rpc_url="http://rpc.test")
    return (
        patch("coordinator_api.contexts.payments.services.payments.settings", settings),
        patch("coordinator_api.contexts.payments.services.settlement_reconciler.httpx.AsyncClient", return_value=client),
        client,
    )


@pytest.mark.asyncio
async def test_audit_adopts_the_sealed_release_hash_when_the_recorded_one_never_landed():
    """#2483: the node recorded a pending envelope that died; the real release sealed under another hash."""
    payment = _payment(tx_hash="0xbb81dead")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, client = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xbb81dead": _FakeResp(404),
            "/rpc/transactions": _FakeResp(
                200,
                [{"transaction_hash": "0x88aedb3f", "status": "confirmed", "job_id": "job-1"}],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_readopted"] == 1
    assert payment.transaction_hash == "0x88aedb3f"
    assert payment.meta_data["release_tx_hash_corrected"]["from"] == "0xbb81dead"
    assert payment.meta_data["release_tx_hash_corrected"]["to"] == "0x88aedb3f"


@pytest.mark.asyncio
async def test_audit_counts_a_confirmed_recorded_hash_as_ok():
    payment = _payment(tx_hash="0xgood")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xgood": _FakeResp(
                200, {"tx_hash": "0xgood", "status": "confirmed", "block_height": 42, "type": "ESCROW_RELEASE"}
            )
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_ok"] == 1
    assert counts["hash_readopted"] == 0
    assert payment.transaction_hash == "0xgood"


@pytest.mark.asyncio
async def test_audit_treats_apply_rejected_row_as_missing_and_readopts():
    """#2516: a 200 with status=rejected/block_height=None is a persisted
    apply-rejected envelope, not a sealed tx — the audit must run the
    adopt branch and pick up the real sealed release hash."""
    payment = _payment(tx_hash="0xrejected-hash")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xrejected-hash": _FakeResp(200, {"status": "rejected", "block_height": None}),
            "/rpc/transactions": _FakeResp(
                200,
                [{"transaction_hash": "0x88aedb3f", "status": "confirmed", "job_id": "job-1"}],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_readopted"] == 1
    assert payment.transaction_hash == "0x88aedb3f"


@pytest.mark.asyncio
async def test_audit_apply_rejected_with_no_sealed_release_is_unbacked():
    """#2516: rejected recorded hash + no sealed ESCROW_RELEASE anywhere →
    hash_unbacked/critical, never stamped healthy."""
    payment = _payment(tx_hash="0xrejected-hash")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xrejected-hash": _FakeResp(200, {"status": "rejected", "block_height": None}),
            "/rpc/transactions": _FakeResp(200, []),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_unbacked"] == 1
    assert payment.transaction_hash == "0xrejected-hash"


@pytest.mark.asyncio
async def test_audit_mempool_pending_view_is_unverifiable_not_ok():
    """#2516: the #2457 pending view (state=pending, no status) must not
    count as sealed — unverifiable, retried next pass, no stamp."""
    payment = _payment(tx_hash="0xpending-hash")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {"/rpc/transaction/0xpending-hash": _FakeResp(200, {"state": "pending", "tx_hash": "0xpending-hash"})}
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_unreachable"] == 1
    assert counts["hash_ok"] == 0
    assert "release_hash_audit_at" not in (payment.meta_data or {})


@pytest.mark.asyncio
async def test_audit_sealed_wrong_type_is_a_miss_and_readopts():
    """#2516: a hash that sealed as a different transaction type is not the
    recorded release — definitive miss, the real release is adopted."""
    payment = _payment(tx_hash="0xother-tx")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xother-tx": _FakeResp(200, {"status": "confirmed", "block_height": 7, "type": "TRANSFER"}),
            "/rpc/transactions": _FakeResp(
                200,
                [{"transaction_hash": "0x88aedb3f", "status": "confirmed", "job_id": "job-1"}],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_readopted"] == 1
    assert payment.transaction_hash == "0x88aedb3f"


@pytest.mark.asyncio
async def test_audit_flags_a_release_with_no_sealed_evidence():
    payment = _payment(tx_hash="0xghost")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xghost": _FakeResp(404),
            "/rpc/transactions": _FakeResp(200, []),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_unbacked"] == 1
    assert payment.transaction_hash == "0xghost"  # never guessed


@pytest.mark.asyncio
async def test_audit_refuses_to_pick_between_multiple_sealed_releases():
    payment = _payment(tx_hash="0xrecorded")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xrecorded": _FakeResp(404),
            "/rpc/transactions": _FakeResp(
                200,
                [
                    {"transaction_hash": "0xaaa", "status": "confirmed"},
                    {"transaction_hash": "0xbbb", "status": "confirmed"},
                ],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_ambiguous"] == 1
    assert payment.transaction_hash == "0xrecorded"


@pytest.mark.asyncio
async def test_audit_leaves_the_row_alone_when_the_chain_is_unreachable():
    import httpx

    payment = _payment(tx_hash="0xmaybe")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client({"/rpc/transaction/0xmaybe": httpx.ConnectError("down")})
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_unreachable"] == 1
    assert payment.transaction_hash == "0xmaybe"


@pytest.mark.asyncio
async def test_audit_ignores_rejected_rows_when_adopting_a_hash():
    payment = _payment(tx_hash="0xrecorded")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xrecorded": _FakeResp(404),
            "/rpc/transactions": _FakeResp(
                200,
                [
                    {"transaction_hash": "0xrejected", "status": "rejected"},
                    {"transaction_hash": "0xsealed", "status": "confirmed"},
                ],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_readopted"] == 1
    assert payment.transaction_hash == "0xsealed"


# --- #3007: refunded-payment tx-hash audit -----------------------------------


def _refund_payment(tx_hash="0xdeadbeef", job_id="job-1"):
    from datetime import UTC, datetime, timedelta

    return SimpleNamespace(
        id="pay-1",
        job_id=job_id,
        status="refunded",
        refund_transaction_hash=tx_hash,
        refunded_at=datetime.now(UTC) - timedelta(hours=1),
        meta_data={},
        updated_at=None,
    )


def _refund_audit_factory(payment, escrow=None, job=None):
    @contextmanager
    def _factory():
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [payment]
        session.execute.return_value.scalars.return_value.first.return_value = escrow
        session.get.return_value = job
        yield session

    return _factory


@pytest.mark.asyncio
async def test_refund_audit_requeues_a_payment_whose_refund_hash_never_sealed():
    """#3007 headline: refund submitted, apply-rejected, no sealed ESCROW_REFUND —
    the payment must return to a retryable state, never stay terminally refunded."""
    from coordinator_api.contexts.payments.acceptance import REFUNDABLE_STATES

    payment = _refund_payment(tx_hash="0xrejected")
    escrow = SimpleNamespace(is_refunded=True, is_active=False, refunded_at="2026-01-01")
    job = SimpleNamespace(payment_status="refunded")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment, escrow, job))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xrejected": _FakeResp(200, {"status": "rejected", "block_height": None}),
            "/rpc/transactions": _FakeResp(200, []),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_requeued"] == 1
    assert payment.status == "settlement_failed"
    assert payment.status in REFUNDABLE_STATES
    assert payment.refund_transaction_hash is None
    assert payment.refunded_at is None
    assert payment.meta_data["refund_hash_rejected"]["hash"] == "0xrejected"
    assert escrow.is_refunded is False
    assert escrow.is_active is True
    assert escrow.refunded_at is None
    assert job.payment_status == "settlement_failed"


@pytest.mark.asyncio
async def test_refund_audit_readopts_when_a_different_refund_sealed():
    """The recorded envelope died but another ESCROW_REFUND sealed — the payment
    *was* refunded; adopt the real hash like the release audit does."""
    payment = _refund_payment(tx_hash="0xdead")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xdead": _FakeResp(404),
            "/rpc/transactions": _FakeResp(
                200,
                [{"transaction_hash": "0xalive", "status": "confirmed", "job_id": "job-1"}],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_readopted"] == 1
    assert payment.status == "refunded"
    assert payment.refund_transaction_hash == "0xalive"
    assert payment.meta_data["refund_tx_hash_corrected"]["to"] == "0xalive"


@pytest.mark.asyncio
async def test_refund_audit_counts_a_confirmed_recorded_hash_as_ok():
    payment = _refund_payment(tx_hash="0xgood")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xgood": _FakeResp(
                200, {"tx_hash": "0xgood", "status": "confirmed", "block_height": 42, "type": "ESCROW_REFUND"}
            )
        }
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_ok"] == 1
    assert counts["refund_requeued"] == 0
    assert payment.refund_transaction_hash == "0xgood"


@pytest.mark.asyncio
async def test_refund_audit_sealed_wrong_type_is_a_miss_and_requeues():
    """A hash that sealed as another tx type is not the recorded refund —
    definitive miss; with no sealed refund the row is requeued."""
    payment = _refund_payment(tx_hash="0xother")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xother": _FakeResp(200, {"status": "confirmed", "block_height": 7, "type": "TRANSFER"}),
            "/rpc/transactions": _FakeResp(200, []),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_requeued"] == 1
    assert payment.status == "settlement_failed"


@pytest.mark.asyncio
async def test_refund_audit_refuses_to_pick_between_multiple_sealed_refunds():
    payment = _refund_payment(tx_hash="0xrecorded")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xrecorded": _FakeResp(404),
            "/rpc/transactions": _FakeResp(
                200,
                [
                    {"transaction_hash": "0xaaa", "status": "confirmed"},
                    {"transaction_hash": "0xbbb", "status": "confirmed"},
                ],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_ambiguous"] == 1
    assert payment.status == "refunded"
    assert payment.refund_transaction_hash == "0xrecorded"


@pytest.mark.asyncio
async def test_refund_audit_leaves_the_row_alone_when_the_chain_is_unreachable():
    import httpx

    payment = _refund_payment(tx_hash="0xmaybe")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client({"/rpc/transaction/0xmaybe": httpx.ConnectError("down")})
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_unreachable"] == 1
    assert payment.status == "refunded"
    assert payment.refund_transaction_hash == "0xmaybe"


@pytest.mark.asyncio
async def test_refund_audit_mempool_pending_view_is_unverifiable_not_ok():
    payment = _refund_payment(tx_hash="0xpending")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client(
        {"/rpc/transaction/0xpending": _FakeResp(200, {"state": "pending", "tx_hash": "0xpending"})}
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_unreachable"] == 1
    assert counts["refund_requeued"] == 0
    assert payment.status == "refunded"
    assert "refund_hash_audit_at" not in (payment.meta_data or {})
