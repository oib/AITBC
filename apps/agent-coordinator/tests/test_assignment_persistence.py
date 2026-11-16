"""Durable persistence for load-balancer task assignments (#2163).

``LoadBalancer.task_assignments`` used to live purely in memory: a
coordinator restart dropped the task -> agent mapping, leaving escrowed
tasks untrackable — ``/tasks/{id}/complete`` could no longer find the
assignment and ``pending_tasks`` accounting reset to zero.

These tests back the ``TaskAssignmentStore`` write-through contract against
the real SQLite agent DB (same machinery the coin requests and task escrows
use) and simulate a restart by building a second ``LoadBalancer`` over the
same store.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from aitbc.db import agent_db  # noqa: E402
from aitbc.models import TaskAssignmentRow  # noqa: E402

from agent_app.routing.agent_discovery import AgentInfo, AgentStatus, AgentType  # noqa: E402
from agent_app.routing.load_balancer import LoadBalancer, LoadMetrics, TaskAssignment  # noqa: E402
from agent_app.storage.assignment_store import TaskAssignmentStore  # noqa: E402


@pytest.fixture
def assignment_db(monkeypatch, tmp_path):
    """A shared agent DB pointed at a fresh file (same trick as test_escrow_persistence)."""
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agent.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    agent_db.init_db()

    yield tmp_path / "agent.db"

    agent_db._engine = None
    agent_db._SessionLocal = None


def _agent_info(agent_id: str = "agent-1") -> AgentInfo:
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


def _registry(agent_id: str = "agent-1") -> AsyncMock:
    registry = AsyncMock()
    registry.discover_agents = AsyncMock(return_value=[_agent_info(agent_id)])
    registry.get_agent_by_id = lambda aid: _agent_info(aid) if aid == agent_id else None
    return registry


def _balancer(store: TaskAssignmentStore | None = None, agent_id: str = "agent-1") -> LoadBalancer:
    return LoadBalancer(registry=_registry(agent_id), assignment_store=store)


def persisted_row(task_id: str) -> TaskAssignmentRow | None:
    """Read the raw row back out of the test DB, detached from its session."""
    with agent_db.get_db_session() as session:
        row = session.get(TaskAssignmentRow, task_id)
        if row is not None:
            session.expunge(row)
        return row


class TestAssignmentPersistence:
    """assign/complete/fail/expire/evict all write through to task_assignments."""

    async def test_pending_assignment_survives_restart(self, assignment_db):
        lb = _balancer(TaskAssignmentStore())
        agent_id = await lb.assign_task({"task_id": "t-restart", "task_type": "x"})
        assert agent_id == "agent-1"

        # Simulate the restart: a fresh balancer rehydrated from the same store.
        restarted = _balancer(TaskAssignmentStore())
        assignment = restarted.get_assignment("t-restart")
        assert assignment is not None
        assert assignment.agent_id == "agent-1"
        assert assignment.status == "pending"
        # pending_tasks accounting is rebuilt so capacity checks stay honest.
        assert restarted.agent_metrics["agent-1"].pending_tasks == 1

    async def test_complete_after_restart_settles_and_persists(self, assignment_db):
        lb = _balancer(TaskAssignmentStore())
        await lb.assign_task({"task_id": "t-complete", "task_type": "x"})

        restarted = _balancer(TaskAssignmentStore())
        restarted.complete_task("t-complete", success=True, response_time=0.5)

        assignment = restarted.get_assignment("t-complete")
        assert assignment is not None
        assert assignment.status == "completed"
        assert assignment.success is True
        assert assignment.completed_at is not None
        row = persisted_row("t-complete")
        assert row is not None
        assert row.status == "completed"
        assert row.success is True

        # A second restart sees the terminal state too.
        again = _balancer(TaskAssignmentStore())
        assert again.get_assignment("t-complete").status == "completed"  # type: ignore[union-attr]

    async def test_fail_and_expire_persist_terminal_states(self, assignment_db):
        lb = _balancer(TaskAssignmentStore())
        await lb.assign_task({"task_id": "t-fail", "task_type": "x"})
        lb.fail_task("t-fail", error_message="boom")
        assert persisted_row("t-fail").status == "failed"  # type: ignore[union-attr]

        stale = TaskAssignment(
            task_id="t-stale",
            agent_id="agent-1",
            assigned_at=datetime.now(UTC) - timedelta(seconds=7200),
        )
        lb.task_assignments["t-stale"] = stale
        lb._persist_assignment(stale)
        lb.agent_metrics["agent-1"] = LoadMetrics(pending_tasks=1)

        restarted = _balancer(TaskAssignmentStore())
        expired = restarted.expire_stale_assignments(max_age_seconds=3600)
        assert expired == ["t-stale"]
        assert restarted.get_assignment("t-stale").status == "timeout"  # type: ignore[union-attr]
        assert persisted_row("t-stale").status == "timeout"  # type: ignore[union-attr]

    async def test_evicted_terminal_row_is_deleted(self, assignment_db):
        lb = _balancer(TaskAssignmentStore())
        lb._max_assignments = 2
        for i in range(3):
            await lb.assign_task({"task_id": f"t-evict-{i}", "task_type": "x"})
            lb.complete_task(f"t-evict-{i}", success=True)
        # All three are terminal; the oldest is evicted once over the bound.
        lb._evict_terminal_assignments()
        assert len(lb.task_assignments) <= 2
        evicted = [t for t in ("t-evict-0", "t-evict-1", "t-evict-2") if t not in lb.task_assignments]
        assert len(evicted) == 1
        assert persisted_row(evicted[0]) is None

    async def test_store_failure_does_not_break_assignment(self, assignment_db, monkeypatch):
        """A broken store degrades to the old in-memory behaviour, loudly."""
        store = TaskAssignmentStore()

        def _boom(_assignment: TaskAssignment) -> None:
            raise RuntimeError("db gone")

        monkeypatch.setattr(store, "save", _boom)
        lb = _balancer(store)

        agent_id = await lb.assign_task({"task_id": "t-nodb", "task_type": "x"})
        assert agent_id == "agent-1"
        assert lb.get_assignment("t-nodb") is not None
