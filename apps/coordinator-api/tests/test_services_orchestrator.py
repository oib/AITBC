"""Service-layer tests for agent_coordination/services/orchestrator_service.py
(#1289 round 6).

Covers AgentStateManager (execution/step CRUD), AgentVerifier (basic/full/ZK
verification levels) and AIAgentOrchestrator (workflow execution, dependency
ordering, status reporting) against the real in-memory session. Step-type
executors are simulated sleeps by design (documented in the source).

The defect chain these tests originally pinned strict-xfail was fixed
in #1316 (same branch): JSON-safe step_states serialization and
tz-normalized completion timing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.agent_coordination.domain.agent import (
    AgentExecution,
    AgentExecutionRequest,
    AgentStatus,
    AgentStep,
    AgentStepExecution,
    AIAgentWorkflow,
    StepType,
    VerificationLevel,
)
from coordinator_api.contexts.agent_coordination.services.orchestrator_service import (
    AgentStateManager,
    AgentVerifier,
    AIAgentOrchestrator,
)


def _seed_workflow(session: Session, owner: str = "client1", n_steps: int = 2) -> AIAgentWorkflow:
    wf = AIAgentWorkflow(owner_id=owner, name="wf", steps={f"s{i}": {} for i in range(n_steps)})
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf


def _seed_step(
    session: Session,
    workflow_id: str,
    order: int = 0,
    step_type: StepType = StepType.INFERENCE,
    **kwargs: Any,
) -> AgentStep:
    step = AgentStep(
        workflow_id=workflow_id,
        step_order=order,
        name=f"step-{order}",
        step_type=step_type,
        **kwargs,
    )
    session.add(step)
    session.commit()
    session.refresh(step)
    return step


def _seed_step_execution(
    session: Session,
    execution_id: str = "exec-x",
    step_id: str = "step-x",
    **kwargs: Any,
) -> AgentStepExecution:
    se = AgentStepExecution(execution_id=execution_id, step_id=step_id, **kwargs)
    session.add(se)
    session.commit()
    session.refresh(se)
    return se


def _orchestrator(session: Session) -> AIAgentOrchestrator:
    return AIAgentOrchestrator(session, coordinator_client=None)  # type: ignore[arg-type]


class TestStateManager:
    async def test_create_execution_resolves_client(self, db_session: Session) -> None:
        sm = AgentStateManager(db_session)
        execution = await sm.create_execution("wf-1", "client1", VerificationLevel.FULL)
        assert execution.id.startswith("exec_")
        assert execution.client_id == "client1"
        assert execution.client_ref == "client1"
        assert execution.verification_level == VerificationLevel.FULL
        assert execution.status == AgentStatus.PENDING

    async def test_create_execution_unknown_client_raises(self, db_session: Session) -> None:
        sm = AgentStateManager(db_session)
        with pytest.raises(ValueError, match="not found"):
            await sm.create_execution("wf-1", "no-such-client")

    async def test_update_execution_status_roundtrip(self, db_session: Session) -> None:
        sm = AgentStateManager(db_session)
        execution = await sm.create_execution("wf-1", "client1")
        updated = await sm.update_execution_status(
            execution.id, AgentStatus.RUNNING, started_at=datetime.now(UTC), total_steps=3
        )
        assert updated.status == AgentStatus.RUNNING
        assert updated.total_steps == 3
        assert updated.started_at is not None

    async def test_update_missing_execution_raises(self, db_session: Session) -> None:
        sm = AgentStateManager(db_session)
        with pytest.raises(ValueError, match="not found"):
            await sm.update_execution_status("exec_missing", AgentStatus.FAILED)

    async def test_get_execution_and_workflow(self, db_session: Session) -> None:
        sm = AgentStateManager(db_session)
        wf = _seed_workflow(db_session)
        execution = await sm.create_execution(wf.id, "client1")
        assert (await sm.get_execution(execution.id)).id == execution.id
        assert await sm.get_execution("exec_missing") is None
        assert (await sm.get_workflow(wf.id)).id == wf.id
        assert await sm.get_workflow("wf_missing") is None

    async def test_get_workflow_steps_ordered(self, db_session: Session) -> None:
        sm = AgentStateManager(db_session)
        wf = _seed_workflow(db_session)
        _seed_step(db_session, wf.id, order=2)
        _seed_step(db_session, wf.id, order=0)
        _seed_step(db_session, wf.id, order=1)
        steps = await sm.get_workflow_steps(wf.id)
        assert [s.step_order for s in steps] == [0, 1, 2]
        assert await sm.get_workflow_steps("wf_missing") == []

    async def test_step_execution_crud(self, db_session: Session) -> None:
        sm = AgentStateManager(db_session)
        se = await sm.create_step_execution("exec-1", "step-1")
        assert se.status == AgentStatus.PENDING
        updated = await sm.update_step_execution(
            se.id, status=AgentStatus.COMPLETED, output_data={"k": "v"}, execution_time=1.5
        )
        assert updated.status == AgentStatus.COMPLETED
        assert updated.output_data == {"k": "v"}
        with pytest.raises(ValueError, match="not found"):
            await sm.update_step_execution("step_exec_missing", status=AgentStatus.FAILED)


class TestVerifier:
    async def test_basic_verify_completed_clean_step(self, db_session: Session) -> None:
        verifier = AgentVerifier()
        se = _seed_step_execution(
            db_session,
            status=AgentStatus.COMPLETED,
            output_data={"out": 1},
            error_message=None,
        )
        result = await verifier.verify_step_execution(se, VerificationLevel.BASIC)
        assert result["verified"] is True
        assert result["verification_level"] == VerificationLevel.BASIC
        assert result["checks"] == ["completion", "output_presence", "error_free"]

    @pytest.mark.parametrize(
        "overrides",
        [
            {"status": AgentStatus.FAILED, "output_data": {"o": 1}},
            {"status": AgentStatus.COMPLETED, "output_data": None},
            {"status": AgentStatus.COMPLETED, "output_data": {"o": 1}, "error_message": "boom"},
            {"status": AgentStatus.RUNNING, "output_data": {"o": 1}},
        ],
    )
    async def test_basic_verify_rejects_unclean(self, db_session: Session, overrides: dict[str, Any]) -> None:
        verifier = AgentVerifier()
        se = _seed_step_execution(db_session, **overrides)
        result = await verifier.verify_step_execution(se, VerificationLevel.BASIC)
        assert result["verified"] is False

    async def test_full_verify_adds_checks(self, db_session: Session) -> None:
        verifier = AgentVerifier()
        se = _seed_step_execution(
            db_session,
            status=AgentStatus.COMPLETED,
            output_data={"o": 1},
            execution_time=10.0,
            memory_usage=128.0,
        )
        result = await verifier.verify_step_execution(se, VerificationLevel.FULL)
        assert result["verified"] is True
        assert "reasonable_execution_time" in result["checks"]
        assert "reasonable_memory_usage" in result["checks"]

    async def test_full_verify_rejects_slow_step(self, db_session: Session) -> None:
        verifier = AgentVerifier()
        se = _seed_step_execution(
            db_session,
            status=AgentStatus.COMPLETED,
            output_data={"o": 1},
            execution_time=7200.0,
            memory_usage=128.0,
        )
        result = await verifier.verify_step_execution(se, VerificationLevel.FULL)
        assert result["verified"] is False

    async def test_full_verify_zero_execution_time_unverified(self, db_session: Session) -> None:
        """Documents a quirk: execution_time=0.0/None is falsy -> the
        reasonable_execution_time check fails -> verified False even for a
        clean completed step."""
        verifier = AgentVerifier()
        se = _seed_step_execution(
            db_session,
            status=AgentStatus.COMPLETED,
            output_data={"o": 1},
            execution_time=0.0,
        )
        result = await verifier.verify_step_execution(se, VerificationLevel.FULL)
        assert result["verified"] is False

    async def test_full_verify_memory_over_limit_does_not_gate(self, db_session: Session) -> None:
        """Documents asymmetry: memory_usage >= 8192 skips the check without
        un-verifying (unlike execution_time) — memory is advisory only."""
        verifier = AgentVerifier()
        se = _seed_step_execution(
            db_session,
            status=AgentStatus.COMPLETED,
            output_data={"o": 1},
            execution_time=10.0,
            memory_usage=99999.0,
        )
        result = await verifier.verify_step_execution(se, VerificationLevel.FULL)
        assert result["verified"] is True
        assert "reasonable_memory_usage" not in result["checks"]

    async def test_zk_falls_back_to_full(self, db_session: Session) -> None:
        verifier = AgentVerifier()
        se = _seed_step_execution(
            db_session,
            status=AgentStatus.COMPLETED,
            output_data={"o": 1},
            execution_time=5.0,
        )
        result = await verifier.verify_step_execution(se, VerificationLevel.ZERO_KNOWLEDGE)
        assert result["verification_level"] == VerificationLevel.ZERO_KNOWLEDGE
        assert "fallback" in result["note"]
        assert result["verified"] is True

    async def test_verify_exception_returns_error_result(self, db_session: Session) -> None:
        verifier = AgentVerifier()
        result = await verifier.verify_step_execution(None, VerificationLevel.BASIC)  # type: ignore[arg-type]
        assert result["verified"] is False
        assert "error" in result


class TestOrchestrator:
    async def test_execute_workflow_missing_workflow_raises(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        request = AgentExecutionRequest(workflow_id="wf_missing", inputs={})
        with pytest.raises(ValueError, match="not found"):
            await orch.execute_workflow(request, "client1")

    async def test_execute_workflow_returns_response_and_marks_running(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session, n_steps=3)
        monkeypatch.setattr(orch, "_execute_steps_async", lambda *a, **k: _noop())
        request = AgentExecutionRequest(workflow_id=wf.id, inputs={"x": 1})
        response = await orch.execute_workflow(request, "client1")
        assert response.workflow_id == wf.id
        assert response.total_steps == 3
        # ORM update() synchronizes the session, so the pre-update object
        # already reflects RUNNING by the time the response is built.
        assert response.status == AgentStatus.RUNNING
        assert response.estimated_total_cost is not None
        execution = await orch.state_manager.get_execution(response.execution_id)
        assert execution is not None
        assert execution.status == AgentStatus.RUNNING
        assert execution.total_steps == 3

    async def test_get_execution_status_missing_raises(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        with pytest.raises(ValueError, match="not found"):
            await orch.get_execution_status("exec_missing")

    async def test_get_execution_status_shape(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session)
        execution = await orch.state_manager.create_execution(wf.id, "client1")
        status = await orch.get_execution_status(execution.id)
        assert status.execution_id == execution.id
        assert status.workflow_id == wf.id
        assert status.status == AgentStatus.PENDING

    async def test_build_execution_order_linear_and_diamond(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session, n_steps=3)
        steps = [
            _seed_step(db_session, wf.id, order=0),
            _seed_step(db_session, wf.id, order=1),
            _seed_step(db_session, wf.id, order=2),
        ]
        # diamond: s0 -> {s1,s2}? steps have no intrinsic dep field; deps come
        # from workflow.dependencies keyed by step id
        order = orch._build_execution_order(steps, {})
        assert set(order) == {s.id for s in steps}
        # explicit deps: last depends on first two
        deps = {steps[2].id: [steps[0].id, steps[1].id]}
        order = orch._build_execution_order(steps, deps)
        assert order[-1] == steps[2].id
        assert set(order[:2]) == {steps[0].id, steps[1].id}

    async def test_build_execution_order_circular_raises(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session, n_steps=2)
        s1 = _seed_step(db_session, wf.id, order=0)
        s2 = _seed_step(db_session, wf.id, order=1)
        with pytest.raises(ValueError, match="Circular dependency"):
            orch._build_execution_order(steps=[s1, s2], dependencies={s1.id: [s2.id], s2.id: [s1.id]})

    async def test_build_execution_order_missing_dep_raises(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session, n_steps=1)
        s1 = _seed_step(db_session, wf.id, order=0)
        with pytest.raises(ValueError, match="Circular dependency"):
            orch._build_execution_order(steps=[s1], dependencies={s1.id: ["step_nonexistent"]})

    async def test_execute_single_step_inference_completes(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session)
        step = _seed_step(db_session, wf.id, step_type=StepType.INFERENCE)
        execution = await orch.state_manager.create_execution(wf.id, "client1")
        se = await orch._execute_single_step(execution.id, step, {"in": 1})
        row = db_session.get(AgentStepExecution, se.id)
        assert row is not None
        assert row.status == AgentStatus.COMPLETED
        assert row.output_data is not None
        assert row.execution_time is not None and row.execution_time > 0
        assert row.input_data == {"in": 1}

    async def test_execute_single_step_training_and_data_processing(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session)
        for step_type in (StepType.TRAINING, StepType.DATA_PROCESSING, StepType.CUSTOM):
            step = _seed_step(db_session, wf.id, step_type=step_type)
            execution = await orch.state_manager.create_execution(wf.id, "client1")
            se = await orch._execute_single_step(execution.id, step, {})
            row = db_session.get(AgentStepExecution, se.id)
            assert row is not None and row.status == AgentStatus.COMPLETED

    async def test_execute_single_step_failure_marks_failed(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session)
        step = _seed_step(db_session, wf.id)
        execution = await orch.state_manager.create_execution(wf.id, "client1")

        async def _boom(step: AgentStep, inputs: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("executor exploded")

        orch._execute_inference_step = _boom  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="executor exploded"):
            await orch._execute_single_step(execution.id, step, {})
        rows = db_session.scalars(select(AgentStepExecution)).all()
        assert rows and rows[-1].status == AgentStatus.FAILED
        assert "executor exploded" in (rows[-1].error_message or "")

    async def test_step_type_dispatch(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session)
        for step_type, attr in [
            (StepType.INFERENCE, "_execute_inference_step"),
            (StepType.TRAINING, "_execute_training_step"),
            (StepType.DATA_PROCESSING, "_execute_data_processing_step"),
            (StepType.CUSTOM, "_execute_custom_step"),
        ]:
            step = _seed_step(db_session, wf.id, step_type=step_type)
            called = []

            async def _spy(s: AgentStep, i: dict[str, Any], _c: list = called) -> dict[str, Any]:
                _c.append(s.id)
                return {"output": {"ok": True}, "execution_time": 0.01}

            setattr(orch, attr, _spy)
            execution = await orch.state_manager.create_execution(wf.id, "client1")
            await orch._execute_single_step(execution.id, step, {})
            assert step.id in called

    async def test_requires_proof_step_gets_verification(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session)
        step = _seed_step(db_session, wf.id, requires_proof=True, verification_level=VerificationLevel.BASIC)
        execution = await orch.state_manager.create_execution(wf.id, "client1")
        se = await orch._execute_single_step(execution.id, step, {})
        row = db_session.get(AgentStepExecution, se.id)
        assert row is not None
        assert row.step_proof is not None
        assert row.verification_status == "verified"

    async def test_handle_execution_failure_marks_failed(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session)
        execution = await orch.state_manager.create_execution(wf.id, "client1")
        await orch._handle_execution_failure(execution.id, RuntimeError("nope"))
        row = await orch.state_manager.get_execution(execution.id)
        assert row is not None
        assert row.status == AgentStatus.FAILED
        assert row.error_message == "nope"
        assert row.completed_at is not None

    def test_estimate_completion_and_cost(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session, n_steps=4)
        execution = AgentExecution(workflow_id=wf.id, client_id="client1", total_steps=4, started_at=datetime.now(UTC))
        est = orch._estimate_completion(execution)
        assert est is not None
        assert (est - execution.started_at).total_seconds() == pytest.approx(120)
        assert orch._estimate_completion(AgentExecution(workflow_id=wf.id, client_id="c")) is None
        assert orch._estimate_cost(wf) == pytest.approx(0.05)

    async def test_execute_steps_async_completes_workflow(self, db_session: Session) -> None:
        orch = _orchestrator(db_session)
        wf = _seed_workflow(db_session, n_steps=2)
        s1 = _seed_step(db_session, wf.id, order=0)
        s2 = _seed_step(db_session, wf.id, order=1)
        wf.dependencies = {s2.id: [s1.id]}
        db_session.add(wf)
        db_session.commit()
        execution = await orch.state_manager.create_execution(wf.id, "client1")
        await orch.state_manager.update_execution_status(
            execution.id, AgentStatus.RUNNING, started_at=datetime.now(UTC), total_steps=2
        )
        await orch._execute_steps_async(execution.id, {})
        row = await orch.state_manager.get_execution(execution.id)
        assert row is not None
        assert row.status == AgentStatus.COMPLETED
        assert row.completed_steps == 2
        assert row.total_execution_time is not None


async def _noop() -> None:
    return None
