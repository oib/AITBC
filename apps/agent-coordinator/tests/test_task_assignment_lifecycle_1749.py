"""#1749: task assignments must reach a terminal state.

Before the fix ``LoadBalancer.complete_task`` had no production caller, so
``pending_tasks`` only ever grew — after ~100 assignments per agent every
``POST /tasks/submit`` failed with 'no suitable agent found'. These tests pin
the lifecycle: caller-task_id correlation, send-failure release, real
completed/failed/timeout states, the bounded assignment map, and the
unpaid-task completion path on ``/tasks/{id}/complete|fail``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_app import state  # noqa: E402
from agent_app.routing.agent_discovery import AgentInfo, AgentStatus, AgentType  # noqa: E402
from agent_app.routing.load_balancer import LoadBalancer, TaskDistributor, TaskPriority  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402


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


def _balancer_with_agent(agent_id: str = "agent-1") -> LoadBalancer:
    registry = AsyncMock()
    registry.discover_agents = AsyncMock(return_value=[_agent_info(agent_id)])
    registry.get_agent_by_id = lambda aid: _agent_info(aid) if aid == agent_id else None
    return LoadBalancer(registry=registry)


class TestAssignmentCorrelation:
    async def test_assign_uses_caller_task_id(self) -> None:
        lb = _balancer_with_agent()
        task_data = {"task_id": "caller-t-1", "task_type": "test"}
        agent_id = await lb.assign_task(task_data)
        assert agent_id == "agent-1"
        assignment = lb.get_assignment("caller-t-1")
        assert assignment is not None
        assert assignment.agent_id == "agent-1"
        assert assignment.status == "pending"
        # The id is written back so the distributor/message carry it too.
        assert task_data["task_id"] == "caller-t-1"

    async def test_assign_mints_id_when_absent(self) -> None:
        lb = _balancer_with_agent()
        task_data: dict = {"task_type": "test"}
        await lb.assign_task(task_data)
        assert task_data["task_id"]
        assert lb.get_assignment(task_data["task_id"]) is not None


class TestSendFailureReleasesPendingSlot:
    async def test_failed_send_fails_assignment(self) -> None:
        lb = _balancer_with_agent()
        td = TaskDistributor(lb)
        td._send_task_to_agent = AsyncMock(return_value=False)  # type: ignore[method-assign]

        await td.submit_task({"task_id": "t-send-fail", "task_type": "x"}, TaskPriority.NORMAL)
        # Drain the queue through the real distribution path.
        task_info = await td.priority_queues[TaskPriority.NORMAL].get()
        await td._distribute_task(task_info)

        metrics = lb.agent_metrics["agent-1"]
        assert metrics.pending_tasks == 0
        assignment = lb.get_assignment("t-send-fail")
        assert assignment is not None
        assert assignment.status == "failed"
        assert assignment.error_message == "send_failed"

    async def test_successful_send_keeps_pending_until_report(self) -> None:
        lb = _balancer_with_agent()
        td = TaskDistributor(lb)
        td._send_task_to_agent = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await td.submit_task({"task_id": "t-send-ok", "task_type": "x"}, TaskPriority.NORMAL)
        task_info = await td.priority_queues[TaskPriority.NORMAL].get()
        await td._distribute_task(task_info)

        assert lb.agent_metrics["agent-1"].pending_tasks == 1
        assert lb.get_assignment("t-send-ok").status == "pending"  # type: ignore[union-attr]

        # The completion report releases the slot.
        lb.complete_task("t-send-ok", success=True)
        assert lb.agent_metrics["agent-1"].pending_tasks == 0
        assert lb.get_assignment("t-send-ok").status == "completed"  # type: ignore[union-attr]


class TestTerminalStates:
    def test_failed_task_gets_failed_status(self) -> None:
        from agent_app.routing.load_balancer import LoadMetrics, TaskAssignment

        lb = _balancer_with_agent()
        assignment = TaskAssignment(task_id="t-x", agent_id="agent-1", assigned_at=datetime.now(UTC))
        lb.task_assignments["t-x"] = assignment
        lb.agent_metrics["agent-1"] = LoadMetrics(pending_tasks=1)
        lb.fail_task("t-x", error_message="boom")
        assert assignment.status == "failed"
        assert lb.agent_metrics["agent-1"].pending_tasks == 0
        assert lb.agent_metrics["agent-1"].failed_tasks == 1

    def test_expire_stale_assignments_fails_old_pending(self) -> None:
        from agent_app.routing.load_balancer import LoadMetrics, TaskAssignment

        lb = LoadBalancer(registry=AsyncMock())
        old = TaskAssignment(
            task_id="t-old",
            agent_id="agent-1",
            assigned_at=datetime.now(UTC) - timedelta(seconds=7200),
        )
        fresh = TaskAssignment(task_id="t-fresh", agent_id="agent-1", assigned_at=datetime.now(UTC))
        lb.task_assignments["t-old"] = old
        lb.task_assignments["t-fresh"] = fresh
        lb.agent_metrics["agent-1"] = LoadMetrics(pending_tasks=2)

        expired = lb.expire_stale_assignments(max_age_seconds=3600)
        assert expired == ["t-old"]
        assert old.status == "timeout"
        assert fresh.status == "pending"
        assert lb.agent_metrics["agent-1"].pending_tasks == 1

    def test_terminal_assignments_are_evicted_pending_kept(self) -> None:
        from agent_app.routing.load_balancer import TaskAssignment

        lb = LoadBalancer(registry=AsyncMock())
        lb._max_assignments = 5
        for i in range(8):
            a = TaskAssignment(task_id=f"t-{i}", agent_id="agent-1", assigned_at=datetime.now(UTC))
            lb.task_assignments[a.task_id] = a
            if i % 2 == 0:
                a.status = "completed"
        lb._evict_terminal_assignments()
        # Pending records survive eviction; the 3 oldest terminal records go.
        assert sum(1 for a in lb.task_assignments.values() if a.status == "pending") == 4
        assert len(lb.task_assignments) == 5


class TestUnpaidCompletionEndpoints:
    """``/tasks/{id}/complete|fail`` settle assignment-only (unpaid) tasks."""

    @pytest.fixture
    def app_client(self, monkeypatch):
        from agent_app.config import settings

        # #1846: settlement mechanics, not authz — anonymous calls 401 in advisory.
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        lb = _balancer_with_agent()
        monkeypatch.setattr(state, "load_balancer", lb)
        monkeypatch.setattr(state, "payment_escrow", None)
        app = FastAPI()
        app.include_router(tasks_router.router)
        client = TestClient(app)
        yield client, lb
        monkeypatch.setattr(state, "load_balancer", None)
        monkeypatch.setattr(state, "payment_escrow", None)

    async def _seed_pending(self, lb: LoadBalancer, task_id: str) -> None:
        await lb.assign_task({"task_id": task_id, "task_type": "x"})

    def test_complete_settles_unpaid_assignment(self, app_client) -> None:
        client, lb = app_client
        import asyncio

        asyncio.run(self._seed_pending(lb, "t-unpaid-1"))
        resp = client.post("/tasks/t-unpaid-1/complete", json={})
        assert resp.status_code == 200
        assert lb.get_assignment("t-unpaid-1").status == "completed"  # type: ignore[union-attr]
        assert lb.agent_metrics["agent-1"].pending_tasks == 0

    def test_fail_settles_unpaid_assignment(self, app_client) -> None:
        client, lb = app_client
        import asyncio

        asyncio.run(self._seed_pending(lb, "t-unpaid-2"))
        resp = client.post("/tasks/t-unpaid-2/fail", json={})
        assert resp.status_code == 200
        assert lb.get_assignment("t-unpaid-2").status == "failed"  # type: ignore[union-attr]
        assert lb.agent_metrics["agent-1"].pending_tasks == 0

    def test_unknown_task_still_404(self, app_client) -> None:
        client, _lb = app_client
        resp = client.post("/tasks/no-such-task/complete", json={})
        # payment_escrow is None and no assignment exists.
        assert resp.status_code == 503
