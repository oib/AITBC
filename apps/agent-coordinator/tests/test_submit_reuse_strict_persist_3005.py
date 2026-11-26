"""#3005 pins: a reused PENDING escrow must prove the durable write before
the chain lock is submitted — same contract as the new-entry path.

``persist_entry`` inserts into the manager's memory *before* the strict
write, so a first submit whose store write fails aborts correctly but
leaves a poisoned in-memory PENDING. The same-task retry then takes the
reuse branch — which performed no strict write — and sealed a funded
on-chain escrow with no durable payment row: the orphan failure #2998
exists to prevent.
"""

import os
from unittest.mock import MagicMock

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_app.config import settings
from agent_app.routers import tasks as tasks_router

from aitbc.crypto import PaymentEscrow

TASK_ID = "atask_3005_reuse"
PAYMENT = {
    "requester": "0xBuyer",
    "agent": "0xAgent",
    "amount": 100,
    "lock_tx": {"type": "ESCROW_LOCK"},
    "lock_signature": "0xsig",
}
BODY = {"task_data": {"task_id": TASK_ID}, "payment": PAYMENT}


class _FlakyStore:
    """Fails the first ``failures`` writes, then accepts everything."""

    def __init__(self, failures: int):
        self.failures = failures
        self.writes = 0

    def save(self, entry) -> None:
        self.writes += 1
        if self.writes <= self.failures:
            raise RuntimeError("db gone")

    def load_all(self) -> list:
        return []

    def load(self, escrow_id: str):
        return None

    def load_by_task(self, task_id: str):
        return None


def _app_with_escrow(escrow: PaymentEscrow, monkeypatch):
    fake_state = MagicMock()
    fake_state.task_distributor = MagicMock()
    fake_state.task_distributor.submit_task = MagicMock()
    fake_state.payment_escrow = escrow
    fake_state.escrow_rpc = MagicMock()
    fake_state.escrow_rpc.create = MagicMock(return_value={"lock_tx_hash": "0x" + "ab" * 32, "contract_id": "c-1"})
    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/v1")
    monkeypatch.setattr(tasks_router, "state", fake_state)
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
    monkeypatch.setattr(settings, "task_payment_escrow_enabled", True)
    return TestClient(app), fake_state


def test_retry_with_store_still_failing_never_submits_chain_lock(monkeypatch):
    """Headline pin: first submit dies on the strict write; the retry must
    hit the same durable-write gate BEFORE any chain submission."""
    escrow = PaymentEscrow(store=_FlakyStore(failures=10))
    client, fake_state = _app_with_escrow(escrow, monkeypatch)

    first = client.post("/v1/tasks/submit", json=BODY)
    assert first.status_code == 502
    fake_state.escrow_rpc.create.assert_not_called()

    # The poisoned in-memory PENDING survives — the retry must not reach
    # the chain while the durable write still fails.
    second = client.post("/v1/tasks/submit", json=BODY)
    assert second.status_code == 502
    fake_state.escrow_rpc.create.assert_not_called()
    entry = escrow.get_escrow_for_task(TASK_ID)
    assert entry is not None  # in-memory row exists — and stays unsubmitted


def test_retry_with_store_recovered_locks_on_chain(monkeypatch):
    """Once the store accepts writes again, the same-task retry proves the
    durable row and proceeds to the chain lock — replay semantics intact."""
    # Two failing writes: create_escrow's non-strict persist (swallowed)
    # plus the strict persist_entry that aborts the first submit. The retry
    # then meets a store that accepts writes again.
    store = _FlakyStore(failures=2)
    escrow = PaymentEscrow(store=store)
    client, fake_state = _app_with_escrow(escrow, monkeypatch)

    first = client.post("/v1/tasks/submit", json=BODY)
    assert first.status_code == 502
    fake_state.escrow_rpc.create.assert_not_called()

    second = client.post("/v1/tasks/submit", json=BODY)
    assert second.status_code != 502, second.text
    fake_state.escrow_rpc.create.assert_called_once()
    entry = escrow.get_escrow_for_task(TASK_ID)
    assert entry is not None
