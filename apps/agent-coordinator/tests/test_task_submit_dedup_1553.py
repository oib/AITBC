"""#1553: POST /tasks/submit must not mint a second escrow on retry.

``task_id`` is the caller-visible natural key. Before the fix every submit
with a ``payment`` block called ``create_escrow`` unconditionally, so a retry
after a lost response locked the buyer's funds on-chain twice. The submit path
now reuses the still-active (PENDING/LOCKED) escrow for the same task_id.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402

from agent_app import state  # noqa: E402
from agent_app.models import TaskPayment, TaskSubmission  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402


def _submission(task_id: str) -> TaskSubmission:
    return TaskSubmission(
        task_data={"task_id": task_id, "task_type": "test"},
        payment=TaskPayment(amount=100, requester="buyer", agent="provider"),
    )


@pytest.fixture
def escrow_env(monkeypatch):
    monkeypatch.setattr(state, "payment_escrow", PaymentEscrow())
    monkeypatch.setattr(tasks_router.settings, "task_payment_escrow_enabled", True)
    yield state.payment_escrow
    monkeypatch.setattr(state, "payment_escrow", None)


class TestTaskSubmitEscrowDedup:
    def test_retry_reuses_active_escrow(self, escrow_env):
        req = _submission("task-dedup-1")
        escrow_id_1, _, status_1 = tasks_router._create_task_escrow(req, "task-dedup-1", "ait-mainnet")
        escrow_id_2, _, status_2 = tasks_router._create_task_escrow(req, "task-dedup-1", "ait-mainnet")

        assert escrow_id_1 == escrow_id_2
        assert status_1 == status_2 == EscrowStatus.PENDING.value
        # Exactly one escrow exists for the task — no duplicate lock possible.
        entries = [e for e in escrow_env._escrows.values() if e.task_id == "task-dedup-1"]
        assert len(entries) == 1

    def test_terminal_escrow_allows_fresh_submission(self, escrow_env):
        req = _submission("task-dedup-2")
        escrow_id_1, _, _ = tasks_router._create_task_escrow(req, "task-dedup-2", "ait-mainnet")
        entry = escrow_env.get_escrow(escrow_id_1)
        assert entry is not None
        # Force terminal: PENDING -> LOCKED -> REFUNDED via direct status set
        # (refund needs LOCKED; lock bookkeeping-only keeps it off-chain).
        escrow_env.lock(entry.escrow_id)
        escrow_env.refund(entry.escrow_id)

        escrow_id_2, _, _ = tasks_router._create_task_escrow(req, "task-dedup-2", "ait-mainnet")
        assert escrow_id_2 != escrow_id_1

    def test_locked_escrow_replay_skips_second_lock(self, escrow_env):
        req = _submission("task-dedup-3")
        escrow_id, _, _ = tasks_router._create_task_escrow(req, "task-dedup-3", "ait-mainnet")
        entry = escrow_env.get_escrow(escrow_id)
        assert entry is not None
        escrow_env.lock(entry.escrow_id, submitter=lambda *a: "lock-tx-1")
        entry.contract_id = "contract-1"
        escrow_env.persist_entry(entry)

        # _lock_escrow_on_chain must return the stored contract id WITHOUT
        # calling PaymentEscrow.lock again (which would raise on non-PENDING).
        contract_id = tasks_router._lock_escrow_on_chain(entry, req.payment, "task-dedup-3")
        assert contract_id == "contract-1"
        assert entry.status == EscrowStatus.LOCKED

    def test_different_requester_same_task_id_is_not_a_replay(self, escrow_env):
        """#1553 merge-interaction: task_id is caller-chosen, so the dedup must
        be scoped to identical payment terms — a second buyer reusing the id
        must not inherit (or hijack) the first buyer's escrow."""
        req_a = _submission("task-dedup-4")
        escrow_id_a, _, _ = tasks_router._create_task_escrow(req_a, "task-dedup-4", "ait-mainnet")

        req_b = TaskSubmission(
            task_data={"task_id": "task-dedup-4", "task_type": "test"},
            payment=TaskPayment(amount=100, requester="other-buyer", agent="provider"),
        )
        with pytest.raises(ValueError, match="different payment terms"):
            tasks_router._create_task_escrow(req_b, "task-dedup-4", "ait-mainnet")

        # No second escrow was minted for the colliding id.
        entries = [e for e in escrow_env._escrows.values() if e.task_id == "task-dedup-4"]
        assert len(entries) == 1
        assert entries[0].escrow_id == escrow_id_a
        assert entries[0].requester == "buyer"

    def test_different_amount_same_task_id_is_not_a_replay(self, escrow_env):
        req_a = _submission("task-dedup-5")
        tasks_router._create_task_escrow(req_a, "task-dedup-5", "ait-mainnet")

        req_b = TaskSubmission(
            task_data={"task_id": "task-dedup-5", "task_type": "test"},
            payment=TaskPayment(amount=999, requester="buyer", agent="provider"),
        )
        with pytest.raises(ValueError, match="different payment terms"):
            tasks_router._create_task_escrow(req_b, "task-dedup-5", "ait-mainnet")
