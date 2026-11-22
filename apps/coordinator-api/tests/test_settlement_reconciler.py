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
    p1, p2, _ = _patch_rpc_and_client({"/rpc/transaction/0xgood": _FakeResp(200, {"tx_hash": "0xgood"})})
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_ok"] == 1
    assert counts["hash_readopted"] == 0
    assert payment.transaction_hash == "0xgood"


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
