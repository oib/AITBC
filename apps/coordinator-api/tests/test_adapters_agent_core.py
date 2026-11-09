"""Tests for coordinator_api.adapters.agent_core_adapters (#1289 residual coverage)."""

from __future__ import annotations

from typing import Any

import pytest

from coordinator_api.adapters.agent_core_adapters import (
    AgentAuditorAdapter,
    AgentExecutionAdapter,
    AgentOrchestratorAdapter,
    AgentSecurityManagerAdapter,
    AgentStepExecutionAdapter,
    SessionProviderAdapter,
    ZKProofServiceAdapter,
)
from coordinator_api.contexts.agent_coordination.domain.agent import (
    AgentExecution,
    AgentStatus,
    AgentStepExecution,
    StepType,
    VerificationLevel,
)
from coordinator_api.contexts.agent_coordination.services.orchestrator_service import (
    AIAgentOrchestrator,
)
from coordinator_api.contexts.agent_coordination.services.security import (
    AgentAuditor,
    AgentSecurityManager,
)
from sqlmodel import Session


def _execution(**overrides: Any) -> AgentExecution:
    defaults: dict[str, Any] = {
        "workflow_id": "wf_123",
        "client_id": "client1",
        "status": AgentStatus.RUNNING,
        "verification_level": VerificationLevel.FULL,
    }
    defaults.update(overrides)
    return AgentExecution(**defaults)


def _step_execution(**overrides: Any) -> AgentStepExecution:
    defaults: dict[str, Any] = {
        "execution_id": "exec_1",
        "step_id": "step_1",
        "step_type": StepType.INFERENCE,
    }
    defaults.update(overrides)
    return AgentStepExecution(**defaults)


class TestAgentExecutionAdapter:
    def test_properties_delegate_to_domain_model(self) -> None:
        execution = _execution()
        adapter = AgentExecutionAdapter(execution)

        assert adapter.id == execution.id
        assert adapter.workflow_id == "wf_123"
        assert adapter.status.value == "running"
        assert adapter.verification_level.value == "full"

    def test_status_maps_to_protocol_enum(self) -> None:
        from aitbc_agent_core.protocols.domain import AgentStatus as ProtocolAgentStatus

        adapter = AgentExecutionAdapter(_execution(status=AgentStatus.COMPLETED))
        assert adapter.status is ProtocolAgentStatus.COMPLETED

    def test_to_dict_returns_model_dump(self) -> None:
        execution = _execution()
        adapter = AgentExecutionAdapter(execution)
        dumped = adapter.to_dict()
        assert dumped["id"] == execution.id
        assert dumped["workflow_id"] == "wf_123"
        assert dumped["status"] == "running"


class TestAgentStepExecutionAdapter:
    def test_properties_delegate_to_domain_model(self) -> None:
        step = _step_execution()
        adapter = AgentStepExecutionAdapter(step)

        assert adapter.id == step.id
        assert adapter.execution_id == "exec_1"
        assert adapter.step_type.value == "inference"

    def test_step_type_maps_to_protocol_enum(self) -> None:
        from aitbc_agent_core.protocols.domain import StepType as ProtocolStepType

        adapter = AgentStepExecutionAdapter(_step_execution(step_type=StepType.TRAINING))
        assert adapter.step_type is ProtocolStepType.TRAINING

    def test_to_dict_returns_model_dump(self) -> None:
        step = _step_execution()
        adapter = AgentStepExecutionAdapter(step)
        dumped = adapter.to_dict()
        assert dumped["id"] == step.id
        assert dumped["step_type"] == "inference"


class _RecordingManager:
    """Fake security manager exposing the optional delegate methods."""

    def __init__(self) -> None:
        self.validate_calls: list[tuple[str, dict[str, Any]]] = []
        self.audit_calls: list[tuple[str, dict[str, Any]]] = []
        self.validate_result = True
        self.validate_exc: Exception | None = None

    async def validate_operation(self, operation: str, context: dict[str, Any]) -> bool:
        self.validate_calls.append((operation, context))
        if self.validate_exc is not None:
            raise self.validate_exc
        return self.validate_result

    async def log_audit(self, event_type: str, details: dict[str, Any]) -> None:
        self.audit_calls.append((event_type, details))


class TestAgentSecurityManagerAdapter:
    async def test_validate_operation_delegates_to_manager(self) -> None:
        manager = _RecordingManager()
        manager.validate_result = False
        adapter = AgentSecurityManagerAdapter(manager)  # type: ignore[arg-type]

        result = await adapter.validate_operation("op", {"k": "v"})

        assert result is False
        assert manager.validate_calls == [("op", {"k": "v"})]

    async def test_validate_operation_fails_closed_on_error(self) -> None:
        manager = _RecordingManager()
        manager.validate_exc = RuntimeError("boom")
        adapter = AgentSecurityManagerAdapter(manager)  # type: ignore[arg-type]

        assert await adapter.validate_operation("op", {}) is False

    async def test_validate_operation_fallback_true_without_delegate(self) -> None:
        # A manager without validate_operation falls back to basic (allow) validation.
        adapter = AgentSecurityManagerAdapter(object())  # type: ignore[arg-type]
        assert await adapter.validate_operation("anything", {}) is True

    async def test_audit_event_delegates_to_log_audit(self) -> None:
        manager = _RecordingManager()
        adapter = AgentSecurityManagerAdapter(manager)  # type: ignore[arg-type]

        await adapter.audit_event("evt", {"a": 1})

        assert manager.audit_calls == [("evt", {"a": 1})]

    async def test_audit_event_noop_when_manager_lacks_methods(self) -> None:
        adapter = AgentSecurityManagerAdapter(object())  # type: ignore[arg-type]
        await adapter.audit_event("evt", {})  # must not raise

    async def test_real_manager_validate_operation_falls_back(self, db_session: Session) -> None:
        # AgentSecurityManager has no validate_operation -> basic allow fallback.
        manager = AgentSecurityManager(db_session)
        adapter = AgentSecurityManagerAdapter(manager)
        assert await adapter.validate_operation("workflow.execute", {}) is True

    async def test_real_manager_audit_event_is_noop(self, db_session: Session) -> None:
        # AgentSecurityManager exposes neither log_audit nor audit_event.
        manager = AgentSecurityManager(db_session)
        adapter = AgentSecurityManagerAdapter(manager)
        await adapter.audit_event("evt", {"x": 1})  # must not raise


class _RecordingAuditor:
    def __init__(self) -> None:
        self.log_audit_calls: list[tuple[str, dict[str, Any]]] = []
        self.audit_event_calls: list[tuple[str, dict[str, Any]]] = []

    async def log_audit(self, event_type: str, details: dict[str, Any]) -> None:
        self.log_audit_calls.append((event_type, details))

    async def audit_event(self, event_type: str, details: dict[str, Any]) -> None:
        self.audit_event_calls.append((event_type, details))


class TestAgentAuditorAdapter:
    async def test_log_audit_delegates_to_log_audit(self) -> None:
        auditor = _RecordingAuditor()
        adapter = AgentAuditorAdapter(auditor)  # type: ignore[arg-type]

        await adapter.log_audit("evt", {"k": "v"})

        assert auditor.log_audit_calls == [("evt", {"k": "v"})]
        assert auditor.audit_event_calls == []

    async def test_log_audit_falls_back_to_audit_event(self) -> None:
        class _LegacyAuditor:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, Any]]] = []

            async def audit_event(self, event_type: str, details: dict[str, Any]) -> None:
                self.calls.append((event_type, details))

        auditor = _LegacyAuditor()
        adapter = AgentAuditorAdapter(auditor)  # type: ignore[arg-type]

        await adapter.log_audit("evt", {})

        assert auditor.calls == [("evt", {})]

    async def test_real_auditor_log_audit_is_noop(self, db_session: Session) -> None:
        # AgentAuditor exposes log_event, not log_audit/audit_event -> silent no-op.
        auditor = AgentAuditor(db_session)
        adapter = AgentAuditorAdapter(auditor)
        await adapter.log_audit("evt", {"x": 1})  # must not raise


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, dict[str, Any]]] = []
        self.status_calls: list[str] = []

    async def execute_workflow(self, workflow_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        self.execute_calls.append((workflow_id, inputs))
        return {"execution_id": "exec_fake", "status": "completed", "result": inputs}

    async def get_status(self, execution_id: str) -> dict[str, Any]:
        self.status_calls.append(execution_id)
        return {"execution_id": execution_id, "status": "running"}


class TestAgentOrchestratorAdapter:
    async def test_execute_workflow_delegates(self) -> None:
        orchestrator = _FakeOrchestrator()
        adapter = AgentOrchestratorAdapter(orchestrator)  # type: ignore[arg-type]

        result = await adapter.execute_workflow("wf_1", {"in": 1})

        assert result["execution_id"] == "exec_fake"
        assert orchestrator.execute_calls == [("wf_1", {"in": 1})]

    async def test_get_status_delegates(self) -> None:
        orchestrator = _FakeOrchestrator()
        adapter = AgentOrchestratorAdapter(orchestrator)  # type: ignore[arg-type]

        result = await adapter.get_status("exec_9")

        assert result == {"execution_id": "exec_9", "status": "running"}
        assert orchestrator.status_calls == ["exec_9"]

    async def test_execute_workflow_fallback_without_delegate(self) -> None:
        adapter = AgentOrchestratorAdapter(object())  # type: ignore[arg-type]

        result = await adapter.execute_workflow("wf_x", {"a": 2})

        assert result == {
            "execution_id": "exec_wf_x",
            "status": "completed",
            "result": {"a": 2},
        }

    async def test_get_status_fallback_without_delegate(self) -> None:
        adapter = AgentOrchestratorAdapter(object())  # type: ignore[arg-type]

        result = await adapter.get_status("exec_x")

        assert result == {"execution_id": "exec_x", "status": "completed"}

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "AgentOrchestratorAdapter.execute_workflow delegates to "
            "AIAgentOrchestrator.execute_workflow(request, client_id) with "
            "(workflow_id: str, inputs: dict) — signature mismatch raises "
            "AttributeError; defect minted as #1379 from #1289 residual coverage"
        ),
    )
    async def test_execute_workflow_with_real_orchestrator(self, db_session: Session) -> None:
        orchestrator = AIAgentOrchestrator(db_session, coordinator_client=None)  # type: ignore[arg-type]
        adapter = AgentOrchestratorAdapter(orchestrator)

        result = await adapter.execute_workflow("wf_missing", {"x": 1})

        assert isinstance(result, dict)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "AgentOrchestratorAdapter.get_status does not match the real "
            "AIAgentOrchestrator (which exposes get_execution_status); the "
            "fallback fabricates {'status': 'completed'} for any id instead "
            "of raising for an unknown execution — defect minted as #1379 "
            "from #1289 residual coverage"
        ),
    )
    async def test_get_status_with_real_orchestrator_raises_for_unknown(self, db_session: Session) -> None:
        orchestrator = AIAgentOrchestrator(db_session, coordinator_client=None)  # type: ignore[arg-type]
        adapter = AgentOrchestratorAdapter(orchestrator)

        with pytest.raises(ValueError, match="not found"):
            await adapter.get_status("exec_does_not_exist")


class TestZKProofServiceAdapter:
    async def test_generate_zk_proof_disabled_by_default(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGENT_INTEGRATION_ZK_MOCK", raising=False)
        adapter = ZKProofServiceAdapter(db_session)

        with pytest.raises(RuntimeError, match="AGENT_INTEGRATION_ZK_MOCK"):
            await adapter.generate_zk_proof("circuit", {"in": 1})

    async def test_verify_proof_disabled_by_default(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGENT_INTEGRATION_ZK_MOCK", raising=False)
        adapter = ZKProofServiceAdapter(db_session)

        with pytest.raises(RuntimeError, match="AGENT_INTEGRATION_ZK_MOCK"):
            await adapter.verify_proof("proof_1")

    async def test_generate_zk_proof_enabled_returns_proof(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENT_INTEGRATION_ZK_MOCK", "1")
        adapter = ZKProofServiceAdapter(db_session)

        result = await adapter.generate_zk_proof("my_circuit", {"x": 1})

        assert result["circuit_name"] == "my_circuit"
        assert result["inputs"] == {"x": 1}
        assert result["proof_id"].startswith("proof_")
        assert result["proof_size"] == 1024

    async def test_verify_proof_enabled_returns_verified(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENT_INTEGRATION_ZK_MOCK", "1")
        adapter = ZKProofServiceAdapter(db_session)

        result = await adapter.verify_proof("proof_anything")

        assert result["verified"] is True
        assert result["details"] == {"mock": True}

    async def test_mock_enabled_requires_exactly_one(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENT_INTEGRATION_ZK_MOCK", "true")
        adapter = ZKProofServiceAdapter(db_session)

        with pytest.raises(RuntimeError):
            await adapter.verify_proof("p")


class TestSessionProviderAdapter:
    def test_get_session_returns_factory_product(self, db_engine: Any) -> None:
        factory = lambda: Session(db_engine)  # noqa: E731
        adapter = SessionProviderAdapter(factory)

        session = adapter.get_session()
        try:
            assert isinstance(session, Session)
        finally:
            session.close()

    def test_close_session_closes_session(self) -> None:
        class _FakeSession:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        session = _FakeSession()
        adapter = SessionProviderAdapter(lambda: session)

        adapter.close_session(session)  # type: ignore[arg-type]

        assert session.closed is True
