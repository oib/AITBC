"""Idempotency-Key ledgering on the payments mutation routes.

The routes delegate settlement to ``PaymentService`` (mocked here); the
ledger layer is what makes a retry safe across process restarts: replay the
recorded verdict, reject key reuse with a different body, and refuse to
re-drive an attempt whose outcome is unknown.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc.auth import require_admin_or_client
from aitbc.operations import OperationLedger
from coordinator_api.contexts.payments.routers.payments import router as payments_router
from coordinator_api.storage import get_session

PAYMENT_VIEW = {
    "job_id": "job1",
    "payment_id": "pay1",
    "amount": 100.0,
    "currency": "AITBC",
    "status": "escrowed",
    "payment_method": "aitbc_token",
    "escrow_address": None,
    "refund_address": None,
    "transaction_hash": None,
    "refund_transaction_hash": None,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
    "released_at": None,
    "refunded_at": None,
}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A fresh per-test ledger, installed behind get_operations_ledger."""
    ops = OperationLedger(str(tmp_path / "coordinator_operations.db"), service="coordinator-api")
    monkeypatch.setenv("COORDINATOR_OPERATIONS_DB", str(tmp_path / "coordinator_operations.db"))
    import coordinator_api.contexts.payments.operations as ops_mod

    monkeypatch.setattr(ops_mod, "_ledger", ops)
    yield ops


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(payments_router, prefix="/v1")
    app.dependency_overrides[require_admin_or_client] = lambda: {"sub": "client1", "role": "client"}
    app.dependency_overrides[get_session] = lambda: Mock()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _mock_service(view=PAYMENT_VIEW):
    svc = Mock()
    svc.create_payment = AsyncMock(return_value=Mock())
    svc.to_view.return_value = dict(view)
    svc.get_payment.return_value = Mock()  # payment exists
    svc.release_payment = AsyncMock(return_value=True)
    svc.refund_payment = AsyncMock(return_value=True)
    return svc


def test_create_payment_replays_recorded_response(client, ledger):
    with patch("coordinator_api.contexts.payments.routers.payments.PaymentService") as svc_cls:
        svc = _mock_service()
        svc_cls.return_value = svc

        body = {"job_id": "job1", "amount": 100.0, "currency": "AITBC"}
        r1 = client.post("/v1/payments", json=body, headers={"Idempotency-Key": "pay-create-1"})
        r2 = client.post("/v1/payments", json=body, headers={"Idempotency-Key": "pay-create-1"})

        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json() == r2.json()
        assert svc.create_payment.await_count == 1  # replay did not re-drive


def test_create_payment_key_conflict(client, ledger):
    with patch("coordinator_api.contexts.payments.routers.payments.PaymentService") as svc_cls:
        svc_cls.return_value = _mock_service()

        client.post(
            "/v1/payments",
            json={"job_id": "job1", "amount": 100.0, "currency": "AITBC"},
            headers={"Idempotency-Key": "pay-create-2"},
        )
        conflict = client.post(
            "/v1/payments",
            json={"job_id": "job1", "amount": 250.0, "currency": "AITBC"},
            headers={"Idempotency-Key": "pay-create-2"},
        )
        assert conflict.status_code == 409
        assert "different request" in conflict.json()["error"]


def test_release_payment_replays_recorded_response(client, ledger):
    with patch("coordinator_api.contexts.payments.routers.payments.PaymentService") as svc_cls:
        svc = _mock_service()
        svc_cls.return_value = svc

        body = {"job_id": "job1", "payment_id": "pay1", "reason": "job completed"}
        r1 = client.post("/v1/payments/pay1/release", json=body, headers={"Idempotency-Key": "pay-rel-1"})
        r2 = client.post("/v1/payments/pay1/release", json=body, headers={"Idempotency-Key": "pay-rel-1"})

        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json() == r2.json() == {"status": "released", "payment_id": "pay1"}
        assert svc.release_payment.await_count == 1


def test_refund_payment_replays_recorded_response(client, ledger):
    with patch("coordinator_api.contexts.payments.routers.payments.PaymentService") as svc_cls:
        svc = _mock_service()
        svc_cls.return_value = svc

        body = {"job_id": "job1", "payment_id": "pay1", "reason": "job failed"}
        r1 = client.post("/v1/payments/pay1/refund", json=body, headers={"Idempotency-Key": "pay-ref-1"})
        r2 = client.post("/v1/payments/pay1/refund", json=body, headers={"Idempotency-Key": "pay-ref-1"})

        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json() == r2.json() == {"status": "refunded", "payment_id": "pay1"}
        assert svc.refund_payment.await_count == 1


def test_deterministic_rejection_is_memoized(client, ledger):
    """A 404 first answer replays as the same 404 — not re-executed."""
    with patch("coordinator_api.contexts.payments.routers.payments.PaymentService") as svc_cls:
        svc = _mock_service()
        svc.get_payment.return_value = None  # payment not found
        svc_cls.return_value = svc

        body = {"job_id": "job1", "payment_id": "pay-missing", "reason": "x"}
        r1 = client.post("/v1/payments/pay-missing/release", json=body, headers={"Idempotency-Key": "pay-rel-404"})
        r2 = client.post("/v1/payments/pay-missing/release", json=body, headers={"Idempotency-Key": "pay-rel-404"})

        assert r1.status_code == 404 and r2.status_code == 404
        assert r1.json() == r2.json()
        assert svc.get_payment.call_count == 1


def test_failed_attempt_is_retryable_but_service_backstop_holds(client, ledger):
    """An in-process exception records ``failed`` — the key stays retryable,
    and the service layer's own settled-state check is what prevents a
    double-settle on the re-drive."""
    with patch("coordinator_api.contexts.payments.routers.payments.PaymentService") as svc_cls:
        svc = _mock_service()
        svc.release_payment = AsyncMock(side_effect=[RuntimeError("boom"), True])
        svc_cls.return_value = svc

        body = {"job_id": "job1", "payment_id": "pay1", "reason": "job completed"}
        r1 = client.post("/v1/payments/pay1/release", json=body, headers={"Idempotency-Key": "pay-rel-err"})
        assert r1.status_code == 500
        assert ledger.get("pay-rel-err").state == "failed"

        r2 = client.post("/v1/payments/pay1/release", json=body, headers={"Idempotency-Key": "pay-rel-err"})
        assert r2.status_code == 200
        assert svc.release_payment.await_count == 2


def test_crash_mid_operation_goes_uncertain(client, ledger):
    """A crash that leaves the row ``pending`` past its lease is not
    re-driven — ``allow_adopt=False`` flips it to ``uncertain`` and the
    caller gets a 409 until an operator resolves it."""
    import sqlite3
    import time

    with patch("coordinator_api.contexts.payments.routers.payments.PaymentService") as svc_cls:
        svc = _mock_service()
        svc_cls.return_value = svc

        body = {"job_id": "job1", "payment_id": "pay1", "reason": "job completed"}
        r1 = client.post("/v1/payments/pay1/release", json=body, headers={"Idempotency-Key": "pay-rel-crash"})
        assert r1.status_code == 200

        # Simulate the crash path: an earlier attempt stranded as pending with
        # an expired lease (as if the process died mid-settlement).
        conn = sqlite3.connect(ledger.db_path)
        conn.execute(
            "UPDATE operations SET state='pending', updated_at=?, lease_expires_at=? WHERE idempotency_key='pay-rel-crash'",
            (time.time() - 7200, time.time() - 3600),
        )
        conn.commit()
        conn.close()

        r2 = client.post("/v1/payments/pay1/release", json=body, headers={"Idempotency-Key": "pay-rel-crash"})
        assert r2.status_code == 409
        assert "outcome is unknown" in r2.json()["error"]
        assert svc.release_payment.await_count == 1  # never re-driven


def test_no_key_routes_straight_through(client, ledger):
    """Callers without a key keep the pre-ledger behavior."""
    with patch("coordinator_api.contexts.payments.routers.payments.PaymentService") as svc_cls:
        svc = _mock_service()
        svc_cls.return_value = svc

        body = {"job_id": "job1", "payment_id": "pay1", "reason": "job completed"}
        r1 = client.post("/v1/payments/pay1/release", json=body)
        r2 = client.post("/v1/payments/pay1/release", json=body)
        assert r1.status_code == 200 and r2.status_code == 200
        assert svc.release_payment.await_count == 2
