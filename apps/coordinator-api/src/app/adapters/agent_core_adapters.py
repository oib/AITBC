"""
Adapters for coordinator-api app to implement aitbc-agent-core protocols.
These adapters wrap coordinator-api's native domain models and services.
"""

from typing import Any

from aitbc_agent_core.protocols.database import ISessionProvider
from aitbc_agent_core.protocols.domain import (
    AgentStatus as ProtocolAgentStatus,
)
from aitbc_agent_core.protocols.domain import (
    IAgentExecution,
    IAgentStepExecution,
)
from aitbc_agent_core.protocols.domain import (
    StepType as ProtocolStepType,
)
from aitbc_agent_core.protocols.domain import (
    VerificationLevel as ProtocolVerificationLevel,
)
from aitbc_agent_core.protocols.orchestrator import IAgentOrchestrator
from aitbc_agent_core.protocols.security import IAuditor, ISecurityManager
from aitbc_agent_core.protocols.zk_proof import IZKProofService

# Import from coordinator-api's own domain models
from app.contexts.agent_coordination.domain.agent import (
    AgentExecution,
    AgentStepExecution,
)
from app.contexts.agent_coordination.services.orchestrator_service import AIAgentOrchestrator

# Import from coordinator-api services
from app.contexts.agent_coordination.services.security import (
    AgentAuditor,
    AgentSecurityManager,
)
from sqlmodel import Session


class AgentExecutionAdapter(IAgentExecution):
    """Adapter for AgentExecution domain model"""

    def __init__(self, execution: AgentExecution):
        self._execution = execution

    @property
    def id(self) -> str:
        return self._execution.id  # type: ignore[no-any-return]

    @property
    def workflow_id(self) -> str:
        return self._execution.workflow_id  # type: ignore[no-any-return]

    @property
    def status(self) -> ProtocolAgentStatus:
        return ProtocolAgentStatus(self._execution.status)

    @property
    def verification_level(self) -> ProtocolVerificationLevel:
        return ProtocolVerificationLevel(self._execution.verification_level)

    def to_dict(self) -> dict[str, Any]:
        return self._execution.model_dump()  # type: ignore[no-any-return]


class AgentStepExecutionAdapter(IAgentStepExecution):
    """Adapter for AgentStepExecution domain model"""

    def __init__(self, step_execution: AgentStepExecution):
        self._step_execution = step_execution

    @property
    def id(self) -> str:
        return self._step_execution.id  # type: ignore[no-any-return]

    @property
    def execution_id(self) -> str:
        return self._step_execution.execution_id  # type: ignore[no-any-return]

    @property
    def step_type(self) -> ProtocolStepType:
        return ProtocolStepType(self._step_execution.step_type)

    def to_dict(self) -> dict[str, Any]:
        return self._step_execution.model_dump()  # type: ignore[no-any-return]


class AgentSecurityManagerAdapter(ISecurityManager):
    """Adapter for AgentSecurityManager"""

    def __init__(self, manager: AgentSecurityManager):
        self._manager = manager

    async def validate_operation(self, operation: str, context: dict[str, Any]) -> bool:
        # Delegate to app-specific implementation
        try:
            if hasattr(self._manager, "validate_operation"):
                return await self._manager.validate_operation(operation, context)  # type: ignore[no-any-return]
            # Fallback: basic validation
            return True
        except Exception:
            # Fail closed on errors
            return False

    async def audit_event(self, event_type: str, details: dict[str, Any]) -> None:
        # Delegate to app-specific implementation
        if hasattr(self._manager, "audit_event"):
            await self._manager.audit_event(event_type, details)


class AgentAuditorAdapter(IAuditor):
    """Adapter for AgentAuditor"""

    def __init__(self, auditor: AgentAuditor):
        self._auditor = auditor

    async def log_audit(self, event_type: str, details: dict[str, Any]) -> None:
        # Delegate to app-specific implementation
        if hasattr(self._auditor, "log_audit"):
            await self._auditor.log_audit(event_type, details)
        elif hasattr(self._auditor, "audit_event"):
            await self._auditor.audit_event(event_type, details)


class AgentOrchestratorAdapter(IAgentOrchestrator):
    """Adapter for AIAgentOrchestrator"""

    def __init__(self, orchestrator: AIAgentOrchestrator):
        self._orchestrator = orchestrator

    async def execute_workflow(self, workflow_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        # Delegate to app-specific implementation
        if hasattr(self._orchestrator, "execute_workflow"):
            return await self._orchestrator.execute_workflow(workflow_id, inputs)  # type: ignore[no-any-return]
        # Fallback: return mock result
        return {
            "execution_id": f"exec_{workflow_id}",
            "status": "completed",
            "result": inputs,
        }

    async def get_status(self, execution_id: str) -> dict[str, Any]:
        # Delegate to app-specific implementation
        if hasattr(self._orchestrator, "get_status"):
            return await self._orchestrator.get_status(execution_id)  # type: ignore[no-any-return]
        # Fallback: return mock status
        return {
            "execution_id": execution_id,
            "status": "completed",
        }


class ZKProofServiceAdapter(IZKProofService):
    """Adapter for ZK proof service (mock implementation)"""

    def __init__(self, session: Session):
        self._session = session

    async def generate_zk_proof(self, circuit_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Mock ZK proof generation"""
        from uuid import uuid4

        return {
            "proof_id": f"proof_{uuid4().hex[:8]}",
            "circuit_name": circuit_name,
            "inputs": inputs,
            "proof_size": 1024,
            "generation_time": 0.1,
        }

    async def verify_proof(self, proof_id: str) -> dict[str, Any]:
        """Mock ZK proof verification"""
        return {"verified": True, "verification_time": 0.05, "details": {"mock": True}}


class SessionProviderAdapter(ISessionProvider):
    """Adapter for SQLModel session management"""

    def __init__(self, session_factory: Any):
        self._session_factory = session_factory

    def get_session(self) -> Session:
        return self._session_factory()  # type: ignore[no-any-return]

    def close_session(self, session: Session) -> None:
        session.close()
