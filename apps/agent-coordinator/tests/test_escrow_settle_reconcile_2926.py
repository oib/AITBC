"""#2926 pins: release()/refund() record terminal on mempool admission, so a
proven on-chain rejection must reconcile the entry back to LOCKED — the
honest pre-settle state — instead of stranding escrowed funds on a
falsely-settled row the expire sweep never touches.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_app.config import settings  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402
from agent_app.routing.agent_discovery import AgentRegistry  # noqa: E402
from agent_app.services import agent_auth as agent_auth_svc  # noqa: E402
from agent_app.services import chain_escrow  # noqa: E402
from agent_app.services.chain_escrow import ChainEscrowClient  # noqa: E402

from aitbc.crypto import PaymentEscrow  # noqa: E402
from aitbc.crypto.payment_escrow import EscrowStatus  # noqa: E402

CHAIN_ID = "ait-test-chain"
REJECT_REASON = "Invalid nonce for 0xAgent: expected 42, got 43"


def _released_entry(escrow: PaymentEscrow, task_id: str = "task-settle"):
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=1,
    )
    escrow.lock(entry.escrow_id, submitter=lambda *_a: "0x" + "aa" * 32)
    escrow.release(entry.escrow_id, submitter=lambda *_a: "0x" + "bb" * 32)
    return entry


def _refunded_entry(escrow: PaymentEscrow, task_id: str = "task-settle-f"):
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=1,
    )
    escrow.lock(entry.escrow_id, submitter=lambda *_a: "0x" + "aa" * 32)
    escrow.refund(entry.escrow_id, submitter=lambda *_a: "0x" + "cc" * 32)
    return entry


def _rpc_returning(payload: dict | None, status_code: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if payload is None:
            return httpx.Response(status_code, json={"detail": "not found"})
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


class TestReconcileRejectedRelease:
    def test_rejected_release_reverts_to_locked(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        released_at = entry.released_at
        assert released_at is not None
        client = ChainEscrowClient(
            "http://rpc.test",
            transport=_rpc_returning({"status": "rejected", "rejected_reason": REJECT_REASON}),
        )

        assert chain_escrow.reconcile_rejected_release(client, entry) is True
        assert entry.status == EscrowStatus.LOCKED
        assert entry.released_at is None
        assert entry.metadata["release_rejected_reason"] == REJECT_REASON
        # Dead hash kept for audit.
        assert entry.tx_hash_release == "0x" + "bb" * 32

    def test_confirmed_release_untouched(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning({"status": "confirmed"}))

        assert chain_escrow.reconcile_rejected_release(client, entry) is False
        assert entry.status == EscrowStatus.RELEASED

    def test_pending_view_never_rejected(self):
        """A mempool-pending view tagged state=pending is not proof of death."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        client = ChainEscrowClient(
            "http://rpc.test",
            transport=_rpc_returning({"status": "rejected", "state": "pending"}),
        )

        assert chain_escrow.reconcile_rejected_release(client, entry) is False
        assert entry.status == EscrowStatus.RELEASED

    def test_unreadable_never_rejected(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning(None, status_code=404))

        assert chain_escrow.reconcile_rejected_release(client, entry) is False
        assert entry.status == EscrowStatus.RELEASED

    def test_no_rpc_or_no_hash_untouched(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        assert chain_escrow.reconcile_rejected_release(None, entry) is False
        entry.tx_hash_release = None
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning({"status": "rejected"}))
        assert chain_escrow.reconcile_rejected_release(client, entry) is False

    def test_locked_entry_untouched_by_release_probe(self):
        escrow = PaymentEscrow()
        entry = escrow.create_escrow(task_id="task-locked", chain_id=CHAIN_ID, requester="0xB", agent="0xA", amount=100)
        escrow.lock(entry.escrow_id, submitter=lambda *_a: "0x" + "aa" * 32)
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning({"status": "rejected"}))
        assert chain_escrow.reconcile_rejected_release(client, entry) is False
        assert entry.status == EscrowStatus.LOCKED


class TestReconcileRejectedRefund:
    def test_rejected_refund_reverts_to_locked(self):
        escrow = PaymentEscrow()
        entry = _refunded_entry(escrow)
        client = ChainEscrowClient(
            "http://rpc.test",
            transport=_rpc_returning({"status": "rejected", "rejected_reason": REJECT_REASON}),
        )

        assert chain_escrow.reconcile_rejected_refund(client, entry) is True
        assert entry.status == EscrowStatus.LOCKED
        assert entry.metadata["refund_rejected_reason"] == REJECT_REASON
        assert entry.tx_hash_refund == "0x" + "cc" * 32

    def test_confirmed_refund_untouched(self):
        escrow = PaymentEscrow()
        entry = _refunded_entry(escrow)
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning({"status": "confirmed"}))

        assert chain_escrow.reconcile_rejected_refund(client, entry) is False
        assert entry.status == EscrowStatus.REFUNDED

    def test_released_entry_untouched_by_refund_probe(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning({"status": "rejected"}))
        assert chain_escrow.reconcile_rejected_refund(client, entry) is False
        assert entry.status == EscrowStatus.RELEASED


@pytest.fixture
def fake_state(monkeypatch):
    state = MagicMock()
    state.agent_registry = AgentRegistry()
    state.payment_escrow = PaymentEscrow()
    state.escrow_rpc = MagicMock()
    state.task_distributor = MagicMock()
    return state


@pytest.fixture
def client(monkeypatch, fake_state):
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/v1")
    monkeypatch.setattr(tasks_router, "state", fake_state)
    monkeypatch.setattr(agent_auth_svc, "state", fake_state)
    return TestClient(app)


class TestEscrowReadSurfacesSettleRejection:
    def test_task_escrow_reports_reverted_release(self, client, fake_state):
        entry = _released_entry(fake_state.payment_escrow)
        fake_state.escrow_rpc.transaction_status.return_value = {
            "status": "rejected",
            "rejected_reason": REJECT_REASON,
        }

        resp = client.get(f"/v1/tasks/{entry.task_id}/escrow")

        assert resp.status_code == 200, resp.text
        escrow = resp.json()["escrow"]
        # Falsely-settled RELEASED reconciles back to the honest LOCKED.
        assert escrow["escrow_status"] == "locked"
        assert escrow["release_rejected_reason"] == REJECT_REASON

    def test_escrow_by_id_reports_reverted_refund(self, client, fake_state):
        entry = _refunded_entry(fake_state.payment_escrow)
        fake_state.escrow_rpc.transaction_status.return_value = {"status": "rejected"}

        resp = client.get(f"/v1/tasks/escrow/{entry.escrow_id}")

        assert resp.status_code == 200, resp.text
        escrow = resp.json()["escrow"]
        assert escrow["escrow_status"] == "locked"
        assert escrow["refund_rejected_reason"] == "settlement transaction rejected on-chain"

    def test_settled_entry_untouched_when_chain_confirms(self, client, fake_state):
        entry = _released_entry(fake_state.payment_escrow)
        fake_state.escrow_rpc.transaction_status.return_value = {"status": "confirmed"}

        resp = client.get(f"/v1/tasks/{entry.task_id}/escrow")

        assert resp.status_code == 200, resp.text
        escrow = resp.json()["escrow"]
        assert escrow["escrow_status"] == "released"
        assert escrow["release_rejected_reason"] is None
