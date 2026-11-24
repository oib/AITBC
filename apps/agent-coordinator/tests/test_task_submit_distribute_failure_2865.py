"""#2865: POST /v1/tasks/submit locks the escrow on-chain BEFORE the task is
distributed — a distributor failure stranded buyer funds until the timeout
sweep. The submit path now refunds a LOCKED escrow immediately (or expires
it early for the sweeper when the refund itself fails)."""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitbc.crypto.payment_escrow import EscrowStatus, PaymentEscrow  # noqa: E402

from agent_app.config import settings  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402
from agent_app.services.chain_escrow import EscrowRPCError  # noqa: E402


class FakeEscrowRPC:
    """Chain escrow client stand-in: create locks, refund is scripted."""

    def __init__(self, refund_error: Exception | None = None) -> None:
        self.refund_calls: list[tuple[str, str]] = []
        self._refund_error = refund_error

    def create(self, **_kwargs) -> dict:
        return {"lock_tx_hash": "0x" + "ab" * 32, "contract_id": "contract-1"}

    def refund(self, job_id: str, *, reason: str = "timeout") -> str:
        self.refund_calls.append((job_id, reason))
        if self._refund_error is not None:
            raise self._refund_error
        return f"0xrefund_{job_id}"


@pytest.fixture
def client(monkeypatch):
    fake_state = MagicMock()
    fake_state.task_distributor = MagicMock()
    fake_state.task_distributor.submit_task = AsyncMock(side_effect=RuntimeError("distributor down"))
    fake_state.payment_escrow = PaymentEscrow()
    fake_state.escrow_rpc = FakeEscrowRPC()
    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/v1")
    monkeypatch.setattr(tasks_router, "state", fake_state)
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
    monkeypatch.setattr(settings, "task_payment_escrow_enabled", True)
    return TestClient(app), fake_state


def _submission(task_id: str, **payment_overrides) -> dict:
    payment = {"requester": "0xBuyer", "agent": "0xAgent", "amount": 100}
    payment.update(payment_overrides)
    return {"task_data": {"task_id": task_id}, "payment": payment}


class TestDistributionFailureRefund:
    def test_locked_escrow_refunded_on_distribution_failure(self, client):
        """The headline bug: lock lands, distribution fails — buyer funds must
        be refunded now, not after timeout_seconds."""
        test_client, fake_state = client
        resp = test_client.post(
            "/v1/tasks/submit",
            json=_submission("t-df", lock_tx={"type": "ESCROW_LOCK"}, lock_signature="0xsig"),
        )
        assert resp.status_code == 500

        entry = fake_state.payment_escrow.get_escrow_for_task("t-df")
        assert entry is not None
        assert entry.status == EscrowStatus.REFUNDED
        assert entry.tx_hash_refund == "0xrefund_t-df"
        assert fake_state.escrow_rpc.refund_calls == [("t-df", "distribution_failed")]

    def test_refund_failure_expires_escrow_for_sweeper(self, client, monkeypatch):
        """When the immediate refund fails, expires_at is pulled to now so the
        next expire_stale sweep retries promptly instead of the full timeout."""
        test_client, fake_state = client
        fake_state.escrow_rpc = FakeEscrowRPC(refund_error=EscrowRPCError("chain unreachable"))

        resp = test_client.post(
            "/v1/tasks/submit",
            json=_submission("t-df2", lock_tx={"type": "ESCROW_LOCK"}, lock_signature="0xsig"),
        )
        assert resp.status_code == 500

        entry = fake_state.payment_escrow.get_escrow_for_task("t-df2")
        assert entry is not None
        assert entry.status == EscrowStatus.LOCKED  # refund failed — still locked
        # expires_at was ~3600s out; it must now be ~now for the sweeper.
        assert entry.expires_at is not None
        assert entry.expires_at <= time.time() + 5

    def test_pending_escrow_untouched_on_distribution_failure(self, client):
        """Guard: a bookkeeping-only (PENDING) escrow has no on-chain funds —
        the failure path must not touch it; a same-task_id retry reuses it."""
        test_client, fake_state = client
        resp = test_client.post("/v1/tasks/submit", json=_submission("t-df3"))
        assert resp.status_code == 500

        entry = fake_state.payment_escrow.get_escrow_for_task("t-df3")
        assert entry is not None
        assert entry.status == EscrowStatus.PENDING
        assert fake_state.escrow_rpc.refund_calls == []

    def test_successful_distribution_leaves_escrow_locked(self, client):
        """Guard: a healthy submit must not refund anything."""
        test_client, fake_state = client
        fake_state.task_distributor.submit_task = AsyncMock(return_value=True)

        resp = test_client.post(
            "/v1/tasks/submit",
            json=_submission("t-df4", lock_tx={"type": "ESCROW_LOCK"}, lock_signature="0xsig"),
        )
        assert resp.status_code == 200, resp.text

        entry = fake_state.payment_escrow.get_escrow_for_task("t-df4")
        assert entry is not None
        assert entry.status == EscrowStatus.LOCKED
        assert fake_state.escrow_rpc.refund_calls == []
