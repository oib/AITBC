"""Durable persistence for task payment escrows.

``PaymentEscrow`` used to keep its bookkeeping purely in memory: a coordinator
restart dropped every entry, ``/v1/tasks/{id}/escrow`` started 404ing, and the
expiry sweeper forgot about escrows whose funds were still locked on-chain.

These tests back the ``EscrowStore`` write-through contract against the real
SQLite agent DB (same machinery the coin requests use) and simulate a restart
by building a second ``PaymentEscrow`` over the same store.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402
from aitbc.db import agent_db  # noqa: E402
from aitbc.models import TaskEscrow  # noqa: E402

from agent_app import state  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402
from agent_app.storage.escrow_store import TaskEscrowStore  # noqa: E402


@pytest.fixture
def escrow_db(monkeypatch, tmp_path):
    """A shared agent DB pointed at a fresh file (same trick as conftest's coin_request_env)."""
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agent.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    agent_db.init_db()

    yield tmp_path / "agent.db"

    agent_db._engine = None
    agent_db._SessionLocal = None


def persisted_row(escrow_id: str) -> TaskEscrow | None:
    """Read the raw row back out of the test DB, detached from its session."""
    with agent_db.get_db_session() as session:
        row = session.get(TaskEscrow, escrow_id)
        if row is not None:
            session.expunge(row)
        return row


class TestEscrowPersistence:
    """create/lock/release/refund all write through to the task_escrows table."""

    def test_locked_escrow_survives_restart(self, escrow_db):
        escrow = PaymentEscrow(store=TaskEscrowStore())
        entry = escrow.create_escrow(
            task_id="task-1", chain_id="ait-mainnet", requester="buyer", agent="provider", amount=100, fee=2
        )
        escrow.lock(entry.escrow_id, submitter=lambda *a: "lock-tx-1")
        entry.contract_id = "contract-1"  # set post-lock, like the submit router does
        escrow.persist_entry(entry)

        restarted = PaymentEscrow(store=TaskEscrowStore())
        loaded = restarted.get_escrow(entry.escrow_id)
        assert loaded is not None
        assert loaded.task_id == "task-1"
        assert loaded.status == EscrowStatus.LOCKED
        assert loaded.tx_hash_lock == "lock-tx-1"
        assert loaded.contract_id == "contract-1"
        assert loaded.requester == "buyer"
        assert loaded.agent == "provider"
        assert loaded.amount == 100
        assert loaded.fee == 2
        assert loaded.expires_at == pytest.approx(entry.expires_at)
        # the task-id lookup the /tasks/{id}/escrow endpoint relies on
        assert restarted.get_escrow_for_task("task-1").escrow_id == entry.escrow_id

    def test_terminal_states_survive_restart(self, escrow_db):
        escrow = PaymentEscrow(store=TaskEscrowStore())
        released = escrow.create_escrow(task_id="t-rel", chain_id="c", requester="b", agent="p", amount=10)
        escrow.lock(released.escrow_id, submitter=lambda *a: "lock-rel")
        escrow.release(released.escrow_id, submitter=lambda *a: "tx-rel")

        refunded = escrow.create_escrow(task_id="t-ref", chain_id="c", requester="b", agent="p", amount=10)
        escrow.lock(refunded.escrow_id, submitter=lambda *a: "lock-ref")
        escrow.refund(refunded.escrow_id, submitter=lambda *a: "tx-ref")

        restarted = PaymentEscrow(store=TaskEscrowStore())
        rel = restarted.get_escrow(released.escrow_id)
        ref = restarted.get_escrow(refunded.escrow_id)
        assert rel.status == EscrowStatus.RELEASED
        assert rel.tx_hash_release == "tx-rel"
        assert rel.released_at is not None
        assert ref.status == EscrowStatus.REFUNDED
        assert ref.tx_hash_refund == "tx-ref"

    def test_bookkeeping_only_escrow_persists(self, escrow_db):
        """Escrows locked without a chain submitter still round-trip."""
        escrow = PaymentEscrow(store=TaskEscrowStore())
        entry = escrow.create_escrow(task_id="t-off", chain_id="c", requester="b", agent="p", amount=7)
        escrow.lock(entry.escrow_id)  # no submitter -> tx_hash_lock stays None

        restarted = PaymentEscrow(store=TaskEscrowStore())
        loaded = restarted.get_escrow(entry.escrow_id)
        assert loaded.status == EscrowStatus.LOCKED
        assert loaded.tx_hash_lock is None

    def test_metadata_roundtrip(self, escrow_db):
        escrow = PaymentEscrow(store=TaskEscrowStore())
        entry = escrow.create_escrow(task_id="t-meta", chain_id="c", requester="b", agent="p", amount=5)
        entry.metadata["quote_id"] = "q-9"
        escrow.persist_entry(entry)

        restarted = PaymentEscrow(store=TaskEscrowStore())
        assert restarted.get_escrow(entry.escrow_id).metadata["quote_id"] == "q-9"

    def test_failed_refund_keeps_row_locked_for_retry(self, escrow_db):
        """A refund whose chain submission fails must stay LOCKED, persisted.

        That is what lets the sweeper retry on the next pass instead of
        stranding the locked funds.
        """
        escrow = PaymentEscrow(store=TaskEscrowStore())
        entry = escrow.create_escrow(task_id="t-stuck", chain_id="c", requester="b", agent="p", amount=10, timeout=0.01)
        escrow.lock(entry.escrow_id, submitter=lambda *a: "lock-tx")
        time.sleep(0.02)

        def boom(*a):
            raise RuntimeError("rpc down")

        assert escrow.expire_stale(refund_submitter_for=lambda e: boom) == []
        assert persisted_row(entry.escrow_id).status == "LOCKED"

        # After a "restart" the row still reads LOCKED and the sweeper retries it.
        restarted = PaymentEscrow(store=TaskEscrowStore())
        loaded = restarted.get_escrow(entry.escrow_id)
        assert loaded.status == EscrowStatus.LOCKED
        assert restarted.expire_stale(refund_submitter_for=lambda e: boom) == []
        assert loaded.status == EscrowStatus.LOCKED

        expired = restarted.expire_stale(refund_submitter_for=lambda e: lambda *a: "refund-tx")
        assert [e.escrow_id for e in expired] == [entry.escrow_id]
        assert loaded.status == EscrowStatus.REFUNDED
        assert loaded.tx_hash_refund == "refund-tx"
        assert persisted_row(entry.escrow_id).status == "REFUNDED"

    def test_sweeper_sees_locked_rows_after_restart(self, escrow_db):
        """An escrow locked before the restart is expired/refunded after it."""
        escrow = PaymentEscrow(store=TaskEscrowStore())
        entry = escrow.create_escrow(task_id="t-sweep", chain_id="c", requester="b", agent="p", amount=10, timeout=0.01)
        escrow.lock(entry.escrow_id, submitter=lambda *a: "lock-tx")
        time.sleep(0.02)

        restarted = PaymentEscrow(store=TaskEscrowStore())
        expired = restarted.expire_stale(refund_submitter_for=lambda e: lambda *a: "swept-tx")
        assert [e.escrow_id for e in expired] == [entry.escrow_id]
        assert restarted.get_escrow(entry.escrow_id).status == EscrowStatus.REFUNDED

    def test_lock_of_reloaded_pending_entry(self, escrow_db):
        """A PENDING entry persisted before a crash can still lock after reload."""
        escrow = PaymentEscrow(store=TaskEscrowStore())
        entry = escrow.create_escrow(task_id="t-pend", chain_id="c", requester="b", agent="p", amount=10)

        restarted = PaymentEscrow(store=TaskEscrowStore())
        loaded = restarted.get_escrow(entry.escrow_id)
        assert loaded.status == EscrowStatus.PENDING
        restarted.lock(loaded.escrow_id, submitter=lambda *a: "late-lock")
        assert persisted_row(entry.escrow_id).status == "LOCKED"


class TestEscrowEndpointsAfterRestart:
    """The reported regression: /tasks/{id}/escrow 404s after a restart."""

    def _client(self) -> TestClient:
        app = FastAPI()
        app.include_router(tasks_router.router)
        return TestClient(app)

    def test_task_escrow_endpoint_survives_restart(self, escrow_db, monkeypatch):
        client = self._client()

        escrow = PaymentEscrow(store=TaskEscrowStore())
        entry = escrow.create_escrow(task_id="task-42", chain_id="c", requester="buyer", agent="prov", amount=50)
        escrow.lock(entry.escrow_id, submitter=lambda *a: "lock-tx-42")
        entry.contract_id = "contract-42"
        escrow.persist_entry(entry)
        monkeypatch.setattr(state, "payment_escrow", escrow)

        before = client.get("/tasks/task-42/escrow")
        assert before.status_code == 200

        # Simulate the restart: a fresh manager rehydrated from the same store.
        monkeypatch.setattr(state, "payment_escrow", PaymentEscrow(store=TaskEscrowStore()))
        after = client.get("/tasks/task-42/escrow")
        assert after.status_code == 200
        body = after.json()["escrow"]
        assert body["escrow_id"] == entry.escrow_id
        assert body["escrow_status"] == "locked"
        assert body["tx_hash_lock"] == "lock-tx-42"
        assert body["contract_id"] == "contract-42"

    def test_escrow_id_endpoint_survives_restart(self, escrow_db, monkeypatch):
        client = self._client()

        escrow = PaymentEscrow(store=TaskEscrowStore())
        entry = escrow.create_escrow(task_id="task-77", chain_id="c", requester="b", agent="p", amount=25)
        escrow.lock(entry.escrow_id, submitter=lambda *a: "lock-tx-77")
        monkeypatch.setattr(state, "payment_escrow", escrow)
        assert client.get(f"/tasks/escrow/{entry.escrow_id}").status_code == 200

        monkeypatch.setattr(state, "payment_escrow", PaymentEscrow(store=TaskEscrowStore()))
        resp = client.get(f"/tasks/escrow/{entry.escrow_id}")
        assert resp.status_code == 200
        assert resp.json()["escrow"]["escrow_status"] == "locked"
