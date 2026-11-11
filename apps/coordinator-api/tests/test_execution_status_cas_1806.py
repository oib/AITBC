"""#1806: agent execution status updates are compare-and-swap."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlmodel import Session

from coordinator_api.contexts.agent_coordination.domain.agent import AgentStatus, AIAgentWorkflow
from coordinator_api.contexts.agent_coordination.services.orchestrator_service import AgentStateManager


def _workflow(session: Session) -> AIAgentWorkflow:
    wf = AIAgentWorkflow(owner_id="client1", name="wf", steps={"s0": {}})
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stale_running_writer_does_not_regress_completed(db_session: Session) -> None:
    sm = AgentStateManager(db_session)
    wf = _workflow(db_session)
    execution = await sm.create_execution(wf.id, "client1")
    await sm.update_execution_status(execution.id, AgentStatus.RUNNING, started_at=datetime.now(UTC), total_steps=1)
    await sm.update_execution_status(execution.id, AgentStatus.COMPLETED, completed_at=datetime.now(UTC))

    regress = await sm.update_execution_status(
        execution.id,
        AgentStatus.RUNNING,
        current_step=99,
        step_states={"stale": True},
    )
    assert regress.status == AgentStatus.COMPLETED
    assert regress.current_step != 99
    row = await sm.get_execution(execution.id)
    assert row is not None and row.status == AgentStatus.COMPLETED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_after_terminal_is_noop(db_session: Session) -> None:
    sm = AgentStateManager(db_session)
    wf = _workflow(db_session)
    execution = await sm.create_execution(wf.id, "client1")
    await sm.update_execution_status(execution.id, AgentStatus.FAILED, completed_at=datetime.now(UTC))

    cancelled = await sm.update_execution_status(execution.id, AgentStatus.CANCELLED, completed_at=datetime.now(UTC))
    assert cancelled.status == AgentStatus.FAILED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_complete_and_running_progress_terminal_wins(db_engine) -> None:
    with Session(db_engine) as session:
        wf = _workflow(session)
        sm = AgentStateManager(session)
        execution = await sm.create_execution(wf.id, "client1")
        exec_id = execution.id

    async def complete() -> None:
        with Session(db_engine) as session:
            sm = AgentStateManager(session)
            await sm.update_execution_status(exec_id, AgentStatus.RUNNING, started_at=datetime.now(UTC), total_steps=1)
            await asyncio.sleep(0)
            await sm.update_execution_status(exec_id, AgentStatus.COMPLETED, completed_at=datetime.now(UTC))

    async def progress() -> None:
        await asyncio.sleep(0)
        with Session(db_engine) as session:
            sm = AgentStateManager(session)
            await sm.update_execution_status(
                exec_id,
                AgentStatus.RUNNING,
                current_step=1,
                step_states={"progress": True},
            )

    await asyncio.gather(complete(), progress())
    with Session(db_engine) as session:
        sm = AgentStateManager(session)
        row = await sm.get_execution(exec_id)
        assert row is not None and row.status == AgentStatus.COMPLETED
