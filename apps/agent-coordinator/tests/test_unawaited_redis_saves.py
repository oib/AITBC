"""#749-class regression: redis-backed save paths must actually await
``redis.set`` — an unawaited call drops the coroutine, so the row is never
persisted while the code reports success. Found in the missing-await sweep:
orchestrator workflow definition/execution saves and the agent-registry
save all discarded the coroutine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from agent_app.routing.agent_discovery import AgentInfo, AgentRegistry, AgentStatus, AgentType
from agent_app.workflow.orchestrator import WorkflowDefinition, WorkflowExecution, WorkflowOrchestrator


class FakeAsyncRedis:
    def __init__(self):
        self.data: dict[str, str] = {}
        self.set_calls = 0

    async def set(self, key, value, ex=None):
        self.set_calls += 1
        self.data[key] = value
        return True


@pytest.mark.asyncio
async def test_save_workflow_definition_persists():
    redis = FakeAsyncRedis()
    orch = WorkflowOrchestrator()
    orch.redis_client = redis
    wf = WorkflowDefinition(workflow_id="wf-1", name="t")
    await orch._save_workflow_definition(wf)
    assert "workflow:wf-1" in redis.data  # absent pre-fix: the coroutine was dropped


@pytest.mark.asyncio
async def test_save_workflow_execution_persists():
    redis = FakeAsyncRedis()
    orch = WorkflowOrchestrator()
    orch.redis_client = redis
    ex = WorkflowExecution(execution_id="e1", workflow_id="wf-1")
    await orch._save_workflow_execution(ex)
    assert "execution:wf-1:e1" in redis.data


@pytest.mark.asyncio
async def test_save_agent_to_redis_persists():
    redis = FakeAsyncRedis()
    svc = SimpleNamespace(redis_client=redis)
    info = AgentInfo(
        agent_id="a1",
        agent_type=AgentType.INFERENCE,
        status=AgentStatus.ACTIVE,
        capabilities=[],
        services=[],
        endpoints={},
        metadata={},
        last_heartbeat=datetime.now(UTC),
        registration_time=datetime.now(UTC),
    )
    await AgentRegistry._save_agent_to_redis(svc, info)
    assert "agent:a1" in redis.data
