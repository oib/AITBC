"""#3027 pins: the orphan sweeper's distributed-check must survive eviction.

``LoadBalancer._evict_terminal_assignments`` drops the oldest TERMINAL
assignments once ``task_assignments`` exceeds ``_max_assignments`` and
``TaskAssignmentStore.delete`` removes the durable row — so "no
``get_assignment(task_id)``" stopped meaning "never distributed". A task
whose escrow is stuck PENDING-with-live-lock (#2998) whose assignment
completed and was later evicted would be REFUNDED even though work was
distributed: provider unpaid, requester refunded.

The fix tombstones the escrow entry itself: ``PaymentEscrow.mark_distributed``
stamps ``metadata["was_distributed_at"]`` on every row for the task when the
distributor creates the assignment, and the sweeper re-stamps on first
observation. The tombstone lives in the escrow store, so it survives both
the bounded assignment map and restarts.
"""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

import httpx  # noqa: E402
import inspect  # noqa: E402

import agent_app.lifespan as lifespan_mod  # noqa: E402
from agent_app.routing.agent_discovery import AgentInfo, AgentStatus, AgentType  # noqa: E402
from agent_app.routing.load_balancer import LoadBalancer, TaskDistributor, TaskPriority  # noqa: E402
from agent_app.services.chain_escrow import ChainEscrowClient  # noqa: E402
from agent_app.services.orphan_escrow_sweeper import (  # noqa: E402
    OrphanedTaskEscrowSweeper,
)
from agent_app.storage.escrow_store import TaskEscrowStore  # noqa: E402

from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402
from aitbc.crypto.payment_escrow import META_WAS_DISTRIBUTED_AT  # noqa: E402
from aitbc.db import agent_db  # noqa: E402

CHAIN_ID = "ait-test-chain"
TASK_ID = "atask_20261126101608_c9252014"
SETTLEMENT_KEY = "test-settlement-key"


def _pending_entry(escrow: PaymentEscrow, task_id: str = TASK_ID, age: float = 10_000.0):
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=1,
    )
    entry.created_at = time.time() - age
    return entry


def _live_record(task_id: str = TASK_ID) -> dict:
    return {
        "job_id": task_id,
        "contract_id": "contract-1",
        "state": "funded",
        "status": "locked",
        "buyer": "0xBuyer",
        "provider": "0xAgent",
        "amount": "0.05",
        "released_amount": "0",
        "lock_tx_hash": "0x" + "cd" * 32,
        "created_at": "2026-11-26T10:16:08+00:00",
    }


class _ChainHandler:
    """MockTransport handler recording calls; escrow GET/refund are scripted."""

    def __init__(self, records: dict[str, dict | None], refund_status: int = 200):
        self.records = records
        self.refund_status = refund_status
        self.gets: list[str] = []
        self.refunds: list[tuple[str, dict, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.startswith("/rpc/escrow/"):
            job_id = path.rsplit("/", 1)[-1]
            self.gets.append(job_id)
            record = self.records.get(job_id)
            if record is None:
                return httpx.Response(404, json={"detail": "not found"}, request=request)
            return httpx.Response(200, json=record, request=request)
        if request.method == "POST" and path.endswith("/refund"):
            job_id = path.split("/")[-2]
            self.refunds.append((job_id, {}, dict(request.headers)))
            if self.refund_status != 200:
                return httpx.Response(self.refund_status, json={"detail": "boom"}, request=request)
            return httpx.Response(200, json={"success": True, "refund_tx_hash": "0x" + "ef" * 32}, request=request)
        return httpx.Response(404, json={"detail": "unrouted"}, request=request)


def _client(handler: _ChainHandler) -> ChainEscrowClient:
    return ChainEscrowClient(
        "http://rpc.test",
        api_key="api-key",
        settlement_api_key=SETTLEMENT_KEY,
        transport=httpx.MockTransport(handler),
    )


def _sweeper(escrow: PaymentEscrow, client: ChainEscrowClient, lb=None, **kwargs) -> OrphanedTaskEscrowSweeper:
    return OrphanedTaskEscrowSweeper(
        payment_escrow=escrow,
        escrow_rpc=client,
        load_balancer=lb,
        grace_seconds=kwargs.pop("grace_seconds", 900.0),
        batch_size=kwargs.pop("batch_size", 25),
        **kwargs,
    )


def _evicted_lb() -> MagicMock:
    """A balancer whose assignment map no longer holds the task (#3027)."""
    return MagicMock(get_assignment=MagicMock(return_value=None))


class TestEvictedAssignmentTombstone:
    """The defect: assignment evicted → get_assignment None → was REFUNDED."""

    def test_evicted_assignment_with_tombstone_adopts_not_refunds(self):
        """The headline fix: the durable tombstone on the escrow entry is
        the distributed-signal that survives assignment eviction."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        entry.metadata[META_WAS_DISTRIBUTED_AT] = time.time() - 100.0
        handler = _ChainHandler({TASK_ID: _live_record()})
        sweeper = _sweeper(escrow, _client(handler), lb=_evicted_lb())

        counts = sweeper.run_once()

        assert counts["adopted"] == 1
        assert handler.refunds == []
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.LOCKED
        assert refreshed.tx_hash_lock == "0x" + "cd" * 32

    def test_assignment_present_adopts_and_stamps_tombstone(self):
        """A live assignment still adopts — and now also tombstones the row
        so a later eviction cannot un-say it."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        lb = MagicMock()
        lb.get_assignment = MagicMock(return_value=MagicMock(status="completed"))
        sweeper = _sweeper(escrow, _client(handler), lb=lb)

        counts = sweeper.run_once()

        assert counts["adopted"] == 1
        assert handler.refunds == []
        assert META_WAS_DISTRIBUTED_AT in entry.metadata

    def test_evicted_assignment_without_tombstone_still_refunds(self):
        """Documented pre-fix fallback: a row written before the tombstone
        existed cannot be distinguished retroactively — no tombstone and no
        assignment still reads as 'submit died before distribution'."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        sweeper = _sweeper(escrow, _client(handler), lb=_evicted_lb())

        counts = sweeper.run_once()

        assert counts["refunded"] == 1
        assert len(handler.refunds) == 1
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.REFUNDED

    def test_tombstone_adopts_even_without_balancer(self):
        """The tombstone is escrow-local truth — no balancer needed."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        entry.metadata[META_WAS_DISTRIBUTED_AT] = time.time()
        handler = _ChainHandler({TASK_ID: _live_record()})
        sweeper = _sweeper(escrow, _client(handler), lb=None)

        counts = sweeper.run_once()

        assert counts["adopted"] == 1
        assert handler.refunds == []

    def test_balancer_read_failure_still_treated_as_distributed(self):
        """Unchanged safe direction: an unreadable balancer must not refund."""
        escrow = PaymentEscrow()
        _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        lb = MagicMock()
        lb.get_assignment = MagicMock(side_effect=RuntimeError("balancer down"))
        sweeper = _sweeper(escrow, _client(handler), lb=lb)

        counts = sweeper.run_once()

        assert counts["adopted"] == 1
        assert handler.refunds == []


class _StampFailsEscrow(PaymentEscrow):
    """Escrow whose persist_entry fails exactly when the tombstone is set."""

    def persist_entry(self, entry, *, strict: bool = False) -> None:
        if META_WAS_DISTRIBUTED_AT in entry.metadata:
            raise RuntimeError("store gone")
        super().persist_entry(entry, strict=strict)


class TestStampFailureTolerance:
    def test_stamp_write_failure_does_not_break_adopt(self):
        """Best-effort stamp: a persist failure is swallowed, the in-memory
        mutation still holds, and the sweep adopts rather than refunding."""
        escrow = _StampFailsEscrow()
        entry = _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        lb = MagicMock()
        lb.get_assignment = MagicMock(return_value=MagicMock(status="completed"))
        sweeper = _sweeper(escrow, _client(handler), lb=lb)

        counts = sweeper.run_once()

        assert counts["adopted"] == 1
        assert handler.refunds == []
        # The in-memory tombstone survived even though the persist failed.
        assert META_WAS_DISTRIBUTED_AT in entry.metadata


class TestMarkDistributed:
    """``PaymentEscrow.mark_distributed`` — the distribution-time stamp."""

    def test_stamps_every_entry_for_task_only(self):
        escrow = PaymentEscrow()
        e1 = _pending_entry(escrow, task_id="task-a")
        e2 = _pending_entry(escrow, task_id="task-a", age=5_000.0)
        other = _pending_entry(escrow, task_id="task-b")

        stamped = escrow.mark_distributed("task-a")

        assert stamped == 2
        assert META_WAS_DISTRIBUTED_AT in e1.metadata
        assert META_WAS_DISTRIBUTED_AT in e2.metadata
        assert META_WAS_DISTRIBUTED_AT not in other.metadata
        # Idempotent: a second call stamps nothing new.
        assert escrow.mark_distributed("task-a") == 0

    def test_unknown_task_stamps_nothing(self):
        escrow = PaymentEscrow()
        _pending_entry(escrow)
        assert escrow.mark_distributed("no-such-task") == 0

    def test_stamp_persists_to_store(self):
        """The tombstone must reach the durable row — that IS the fix."""
        saves: list[dict] = []

        class _RecordingStore:
            def save(self, entry) -> None:
                saves.append(dict(entry.metadata))

            def load_all(self) -> list:
                return []

            def load(self, escrow_id: str):
                return None

            def load_by_task(self, task_id: str):
                return None

        escrow = PaymentEscrow(store=_RecordingStore())
        entry = _pending_entry(escrow)
        escrow.mark_distributed(TASK_ID)

        assert any(META_WAS_DISTRIBUTED_AT in m for m in saves)
        assert META_WAS_DISTRIBUTED_AT in entry.metadata


@pytest.fixture
def escrow_db(monkeypatch, tmp_path):
    """Fresh agent DB file (same trick as test_escrow_persistence)."""
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agent.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    agent_db.init_db()

    yield tmp_path / "agent.db"

    agent_db._engine = None
    agent_db._SessionLocal = None


class TestTombstoneSurvivesRestart:
    def test_tombstone_reloads_and_still_adopts(self, escrow_db):
        """End-to-end durability: stamp → 'restart' (new PaymentEscrow over
        the same store) → evicted assignment → still adopted, not refunded."""
        store = TaskEscrowStore()
        escrow = PaymentEscrow(store=store)
        entry = _pending_entry(escrow)
        escrow.mark_distributed(TASK_ID)

        # Simulate restart: a fresh manager rehydrates from the same store.
        escrow2 = PaymentEscrow(store=TaskEscrowStore())
        reloaded = escrow2.get_escrow_for_task(TASK_ID)
        assert reloaded is not None
        assert META_WAS_DISTRIBUTED_AT in reloaded.metadata

        handler = _ChainHandler({TASK_ID: _live_record()})
        sweeper = _sweeper(escrow2, _client(handler), lb=_evicted_lb())

        counts = sweeper.run_once()

        assert counts["adopted"] == 1
        assert handler.refunds == []
        assert escrow2.get_escrow(entry.escrow_id).status == EscrowStatus.LOCKED


def _agent_info(agent_id: str = "agent-1") -> AgentInfo:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return AgentInfo(
        agent_id=agent_id,
        agent_type=AgentType.WORKER,
        status=AgentStatus.ACTIVE,
        capabilities=[],
        services=[],
        endpoints={"http": "http://agent-1:9000"},
        metadata={},
        last_heartbeat=now,
        registration_time=now,
    )


def _balancer_with_agent(agent_id: str = "agent-1") -> LoadBalancer:
    registry = AsyncMock()
    registry.discover_agents = AsyncMock(return_value=[_agent_info(agent_id)])
    registry.get_agent_by_id = lambda aid: _agent_info(aid) if aid == agent_id else None
    return LoadBalancer(registry=registry)


class TestDistributionTimeStamp:
    """The earliest durable moment: stamp when the assignment is created,
    before any later eviction can erase the only distributed-evidence."""

    async def test_distribute_task_tombstones_escrow_rows(self):
        lb = _balancer_with_agent()
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow, task_id="t-dist-1")
        td = TaskDistributor(lb, payment_escrow=escrow)
        td._send_task_to_agent = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await td.submit_task({"task_id": "t-dist-1", "task_type": "x"}, TaskPriority.NORMAL)
        task_info = await td.priority_queues[TaskPriority.NORMAL].get()
        await td._distribute_task(task_info)

        assert META_WAS_DISTRIBUTED_AT in entry.metadata
        # And the balancer-side assignment exists as before.
        assert lb.get_assignment("t-dist-1") is not None

    async def test_distribute_task_without_escrow_is_noop(self):
        lb = _balancer_with_agent()
        td = TaskDistributor(lb)  # payment_escrow defaults to None
        td._send_task_to_agent = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await td.submit_task({"task_id": "t-dist-2", "task_type": "x"}, TaskPriority.NORMAL)
        task_info = await td.priority_queues[TaskPriority.NORMAL].get()
        await td._distribute_task(task_info)  # must not raise

        assert td.distribution_stats["tasks_distributed"] == 1

    async def test_stamp_failure_never_breaks_distribution(self):
        lb = _balancer_with_agent()
        bad_escrow = MagicMock()
        bad_escrow.mark_distributed = MagicMock(side_effect=RuntimeError("store gone"))
        td = TaskDistributor(lb, payment_escrow=bad_escrow)
        td._send_task_to_agent = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await td.submit_task({"task_id": "t-dist-3", "task_type": "x"}, TaskPriority.NORMAL)
        task_info = await td.priority_queues[TaskPriority.NORMAL].get()
        await td._distribute_task(task_info)

        assert td.distribution_stats["tasks_distributed"] == 1
        bad_escrow.mark_distributed.assert_called_once_with("t-dist-3")

    async def test_no_assignment_means_no_stamp(self):
        """assign_task returning None (no eligible agent) must NOT tombstone
        — the escrow was never distributed and stays refundable."""
        lb = _balancer_with_agent()
        lb.assign_task = AsyncMock(return_value=None)
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow, task_id="t-dist-4")
        td = TaskDistributor(lb, payment_escrow=escrow)

        await td.submit_task({"task_id": "t-dist-4", "task_type": "x"}, TaskPriority.NORMAL)
        task_info = await td.priority_queues[TaskPriority.NORMAL].get()
        await td._distribute_task(task_info)

        assert META_WAS_DISTRIBUTED_AT not in entry.metadata


class TestLifespanWiring:
    """#3027 wiring pin: the lifespan must hand the escrow manager to the
    distributor — without it the distribution-time stamp never lands and
    the fix only covers rows the sweeper happened to probe before eviction."""

    def test_lifespan_wires_distributor_payment_escrow(self):
        src = inspect.getsource(lifespan_mod.lifespan)
        assert "task_distributor.payment_escrow" in src
