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
