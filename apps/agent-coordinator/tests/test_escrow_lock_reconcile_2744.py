"""#2744 pins: a consensus-REJECTED ESCROW_LOCK must reconcile the coordinator's
escrow bookkeeping to chain truth.

``PaymentEscrow.lock`` records LOCKED on mempool admission, not on seal — an
apply-time rejection (bad nonce, failed gate) used to leave the entry claiming
funds that never moved, and ``escrow_status: locked`` gated task execution.
Now ``reconcile_rejected_lock`` probes the chain tx record and flips the entry
to the terminal REJECTED state with the reason attached; the escrow read
routes surface it and the stale-escrow sweep reconciles even without a read.
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
from agent_app.services.chain_escrow import ChainEscrowClient, reconcile_rejected_lock  # noqa: E402

from aitbc.crypto import PaymentEscrow  # noqa: E402
from aitbc.crypto.payment_escrow import EscrowStatus  # noqa: E402

CHAIN_ID = "ait-test-chain"
REJECT_REASON = "Invalid nonce for 0xBuyer: expected 187, got 189"


def _locked_entry(escrow: PaymentEscrow, task_id: str = "task-recon"):
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=1,
    )
    escrow.lock(entry.escrow_id, submitter=lambda *_a: "0x" + "ab" * 32)
    return entry


def _rpc_returning(payload: dict | None, status_code: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if payload is None:
            return httpx.Response(status_code, json={"detail": "not found"})
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


class TestReconcileRejectedLock:
    def test_rejected_lock_flips_entry_with_reason(self):
        escrow = PaymentEscrow()
        entry = _locked_entry(escrow)
        client = ChainEscrowClient(
            "http://rpc.test",
            transport=_rpc_returning({"status": "rejected", "rejected_reason": REJECT_REASON}),
        )

        assert reconcile_rejected_lock(client, entry) is True
        assert entry.status == EscrowStatus.REJECTED
        assert entry.metadata["lock_rejected_reason"] == REJECT_REASON

    def test_confirmed_lock_untouched(self):
        escrow = PaymentEscrow()
        entry = _locked_entry(escrow)
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning({"status": "confirmed", "block_height": 42}))

        assert reconcile_rejected_lock(client, entry) is False
        assert entry.status == EscrowStatus.LOCKED

    def test_pending_or_unknown_never_rejected(self):
        escrow = PaymentEscrow()
        entry = _locked_entry(escrow)
        for payload in ({"status": "pending"}, None):
            client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning(payload, status_code=404))
            assert reconcile_rejected_lock(client, entry) is False
            assert entry.status == EscrowStatus.LOCKED

    def test_no_rpc_or_no_lock_hash_untouched(self):
        escrow = PaymentEscrow()
        entry = _locked_entry(escrow)
        assert reconcile_rejected_lock(None, entry) is False
        entry.tx_hash_lock = None
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning({"status": "rejected"}))
        assert reconcile_rejected_lock(client, entry) is False

    def test_pending_entry_untouched(self):
        escrow = PaymentEscrow()
        entry = escrow.create_escrow(
            task_id="task-pending",
            chain_id=CHAIN_ID,
            requester="0xBuyer",
            agent="0xAgent",
            amount=100,
        )
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning({"status": "rejected"}))
        assert reconcile_rejected_lock(client, entry) is False
        assert entry.status == EscrowStatus.PENDING


class TestTransactionStatusClient:
    def test_returns_chain_record(self):
        client = ChainEscrowClient(
            "http://rpc.test",
            transport=_rpc_returning({"status": "rejected", "rejected_reason": REJECT_REASON}),
        )
        info = client.transaction_status("0x" + "ab" * 32, chain_id=CHAIN_ID)
        assert info is not None and info["status"] == "rejected"
        assert info["rejected_reason"] == REJECT_REASON

    def test_unreadable_is_none(self):
        client = ChainEscrowClient("http://rpc.test", transport=_rpc_returning(None, status_code=404))
        assert client.transaction_status("0x" + "ab" * 32) is None


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


class TestEscrowReadSurfacesRejection:
    def test_task_escrow_reports_rejected_with_reason(self, client, fake_state):
        entry = _locked_entry(fake_state.payment_escrow)
        fake_state.escrow_rpc.transaction_status.return_value = {
            "status": "rejected",
            "rejected_reason": REJECT_REASON,
        }

        resp = client.get(f"/v1/tasks/{entry.task_id}/escrow")

        assert resp.status_code == 200, resp.text
        escrow = resp.json()["escrow"]
        assert escrow["escrow_status"] == "rejected"
        assert escrow["lock_rejected_reason"] == REJECT_REASON
        # The transition persisted: later reads agree without another probe.
        fake_state.escrow_rpc.transaction_status.assert_called_once()
        again = client.get(f"/v1/tasks/{entry.task_id}/escrow")
        assert again.json()["escrow"]["escrow_status"] == "rejected"
        fake_state.escrow_rpc.transaction_status.assert_called_once()

    def test_escrow_by_id_reports_rejected(self, client, fake_state):
        entry = _locked_entry(fake_state.payment_escrow)
        fake_state.escrow_rpc.transaction_status.return_value = {"status": "rejected"}

        resp = client.get(f"/v1/tasks/escrow/{entry.escrow_id}")

        assert resp.status_code == 200, resp.text
        escrow = resp.json()["escrow"]
        assert escrow["escrow_status"] == "rejected"
        assert escrow["lock_rejected_reason"] == "lock transaction rejected on-chain"

    def test_locked_while_chain_confirms(self, client, fake_state):
        entry = _locked_entry(fake_state.payment_escrow)
        fake_state.escrow_rpc.transaction_status.return_value = {"status": "confirmed"}

        resp = client.get(f"/v1/tasks/{entry.task_id}/escrow")

        assert resp.status_code == 200, resp.text
        escrow = resp.json()["escrow"]
        assert escrow["escrow_status"] == "locked"
        assert escrow["lock_rejected_reason"] is None

    def test_rejected_entry_is_terminal_for_task_lookup(self, client, fake_state):
        """Once REJECTED the entry leaves the active set: a same-task resubmit
        must be able to create a fresh escrow instead of shadowing the dead one."""
        entry = _locked_entry(fake_state.payment_escrow, task_id="task-reuse")
        fake_state.escrow_rpc.transaction_status.return_value = {"status": "rejected"}
        assert client.get(f"/v1/tasks/{entry.task_id}/escrow").status_code == 200

        fresh = fake_state.payment_escrow.create_escrow(
            task_id="task-reuse",
            chain_id=CHAIN_ID,
            requester="0xBuyer",
            agent="0xAgent",
            amount=100,
        )
        found = fake_state.payment_escrow.get_escrow_for_task("task-reuse")
        assert found is not None and found.escrow_id == fresh.escrow_id
