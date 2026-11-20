"""#2014: the workflow orchestrator must be start()ed before it persists.

S10 found ``agent workflow create-workflow`` returning 200 while
``list-workflows`` stayed empty and ``execute`` 404'd: lifespan never
called ``WorkflowOrchestrator.start()``, so ``self.redis_client`` stayed
None and every ``_save_*`` no-oped. These pins drive the real
start -> create -> list -> execute path against a fake redis module.
"""

from __future__ import annotations

from typing import Any

import pytest

import agent_app.workflow.orchestrator as orch_mod
from agent_app.workflow.orchestrator import WorkflowOrchestrator, get_orchestrator


class _FakeRedis:
    """Minimal async redis stand-in: get/set/scan_iter/ping/aclose."""

    def __init__(self, *, ping_fails: bool = False) -> None:
        self.data: dict[str, str] = {}
        self._ping_fails = ping_fails
        self.closed = False

    async def ping(self) -> bool:
        if self._ping_fails:
            raise ConnectionError("redis down")
        return True

    async def aclose(self) -> None:
        self.closed = True

    async def get(self, key: str):
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.data[key] = value
        return True

    async def scan_iter(self, pattern: str):
        prefix = pattern.rstrip("*")
        for key in list(self.data):
            if key.startswith(prefix):
                yield key


class _FakeRedisModule:
    def __init__(self, client: _FakeRedis) -> None:
        self._client = client

    def from_url(self, url: str):
        return self._client


@pytest.fixture
def fake_redis(monkeypatch):
    client = _FakeRedis()
    module = _FakeRedisModule(client)
    monkeypatch.setattr(orch_mod, "redis_client", module)
    return client


@pytest.fixture(autouse=True)
def _reset_singleton():
    orch_mod._orchestrator = None
    yield
    orch_mod._orchestrator = None


@pytest.mark.asyncio
async def test_started_orchestrator_persists_workflows(fake_redis):
    """The defect: un-started orchestrator saved nothing. After start(),
    create -> list -> execute all see the workflow."""
    orch = WorkflowOrchestrator(redis_url="redis://fake")
    await orch.start()
    assert orch.redis_client is fake_redis

    wf = await orch.create_workflow(
        name="s10-paid-leg",
        steps=[{"agent_id": "a1", "action": "noop", "parameters": {}}],
        created_by="test",
    )
    assert f"workflow:{wf.workflow_id}" in fake_redis.data

    listed = await orch.list_workflows()
    assert [w.workflow_id for w in listed] == [wf.workflow_id]

    execution = await orch.execute_workflow(workflow_id=wf.workflow_id, input_parameters={})
    assert execution.workflow_id == wf.workflow_id


@pytest.mark.asyncio
async def test_unreachable_redis_degrades_to_memory_mode(monkeypatch):
    """start() must not leave a dead client installed — persistence calls
    would 500 per request instead of degrading with a warning."""
    client = _FakeRedis(ping_fails=True)
    monkeypatch.setattr(orch_mod, "redis_client", _FakeRedisModule(client))

    orch = WorkflowOrchestrator(redis_url="redis://dead")
    await orch.start()
    assert orch.redis_client is None
    assert client.closed
    assert await orch.list_workflows() == []


@pytest.mark.asyncio
async def test_get_orchestrator_uses_lifespan_redis_url(monkeypatch):
    """lifespan passes REDIS_URL through get_orchestrator — the singleton
    must be constructed with it, not the localhost default."""
    seen: dict[str, Any] = {}

    class _CaptureModule(_FakeRedisModule):
        def from_url(self, url: str):
            seen["url"] = url
            return super().from_url(url)

    monkeypatch.setattr(orch_mod, "redis_client", _CaptureModule(_FakeRedis()))

    orch = get_orchestrator(redis_url="redis://env-redis:6379/2")
    await orch.start()
    assert seen["url"] == "redis://env-redis:6379/2"
