"""monitor_sandbox must refuse rather than serve fabricated zero metrics.

The endpoint used to return all-zero resource_usage/security_events/counters
shaped like real monitoring data. Until real container/process/network/fs
integration exists it raises NotImplementedError; the router maps that to 501.
"""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from coordinator_api.contexts.agent_coordination.services.security import (
    AgentSandboxConfig,
    AgentSandboxManager,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[AgentSandboxConfig.__table__])
    with Session(engine) as session:
        yield session


async def test_monitor_sandbox_refuses_with_not_implemented(session):
    session.add(AgentSandboxConfig(id="sandbox_exec-1"))
    session.commit()
    mgr = AgentSandboxManager(session)
    with pytest.raises(NotImplementedError, match="not implemented"):
        await mgr.monitor_sandbox("exec-1")


async def test_monitor_sandbox_unknown_execution_id(session):
    mgr = AgentSandboxManager(session)
    with pytest.raises(ValueError, match="Sandbox not found"):
        await mgr.monitor_sandbox("nonexistent")


async def test_create_sandbox_result_is_response_serializable(session):
    """create_sandbox returns an AgentSandboxConfig ORM object; the route must be
    able to serialize it via model_dump(mode='json') — it previously returned the
    ORM object to a `dict` response annotation and FastAPI response validation
    turned that into a 500 AFTER the row committed."""
    mgr = AgentSandboxManager(session)
    sandbox = await mgr.create_sandbox_environment(execution_id="exec-ser")
    dumped = sandbox.model_dump(mode="json")
    assert dumped["id"] == "sandbox_exec-ser"
    assert isinstance(dumped["created_at"], str)
    assert isinstance(dumped["security_level"], str)


async def test_create_sandbox_second_call_conflicts_on_pk(session):
    """Sandbox ids are deterministic (sandbox_{execution_id}) so the router's
    IntegrityError → return-existing path is what makes re-create idempotent."""
    import sqlalchemy.exc

    mgr = AgentSandboxManager(session)
    await mgr.create_sandbox_environment(execution_id="exec-dupe")
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await mgr.create_sandbox_environment(execution_id="exec-dupe")
