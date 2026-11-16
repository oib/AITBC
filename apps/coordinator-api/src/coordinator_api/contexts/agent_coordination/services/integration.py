"""
Agent Integration and Deployment Framework for Verifiable AI Agent Orchestration
Integrates agent orchestration with existing ML ZK proof system and provides deployment tools

MIGRATION IN PROGRESS: This file is being migrated to use shared AgentIntegrationService
from aitbc-agent-core package. See agent_integration_factory.py for the factory pattern.
After migration is complete, duplicated code will be removed.

Session/threadpool audit (#1908)
--------------------------------
All four managers hold one sync ``Session`` and dispatch DB work through
``run_in_threadpool``; the composed helpers (``AgentAuditor``,
``AgentSecurityManager``, ``AgentTrustManager``, ``AgentSandboxManager``,
``AIAgentOrchestrator``/``AgentStateManager``) share that same Session.

Production wiring is sequential today: ``agent_integration_router`` builds a
fresh manager set per request on the per-request ``get_session()`` Session
and every ``await`` is sequential — no ``gather``/``create_task`` — so no
two workers ever touch the Session concurrently. The hazard is latent: any
caller that shares one manager/Session across coroutines reproduces the
#1904 ``sqlite3.InterfaceError``.

Defense in depth: every session-touching public method runs under a
per-Session ``asyncio.Lock`` (``_serialized_session``) stored in
``session.info`` — one lock per Session, shared by every manager composed
on it. ``ZKProofService`` holds a Session reference it never uses.
``AgentProductionManager.deploy_to_production`` deliberately does not hold
the lock across its body — it only orchestrates already-locked sub-manager
calls and holding it would self-deadlock on the non-reentrant
``asyncio.Lock`` — so its two direct ``auditor.log_event`` calls take the
lock individually. Private helpers (``_create_deployment_instance``,
``_check_instance_health``, ``_remove_deployment_instance``) run inside
their callers' lock and are not decorated. ``AgentStateManager``'s own
#1904 lock is a different object, so mixing orchestrator calls with these
managers on one Session is still unsynchronized — no current call path
does that. Router endpoints also touch the Session directly
(``session.get``/``session.execute`` via ``run_in_threadpool``) outside
the lock, sequential per request under the same per-request reasoning.
"""

import asyncio
import functools
import os
import re
import subprocess
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import uuid4

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import JSON, Column, Field, Session, SQLModel, select

from aitbc.aitbc_logging import get_logger

from coordinator_api.contexts.agent_coordination.domain.agent import (
    AgentExecution,
    AgentStep,
    AgentStepExecution,
    VerificationLevel,
)
from .orchestrator_service import AIAgentOrchestrator
from .security import AgentAuditor, AgentSecurityManager, AuditEventType, SecurityLevel
from starlette.concurrency import run_in_threadpool

logger = get_logger(__name__)

# Expected failure surface for the best-effort handlers below: sqlmodel
# session/DBAPI errors, systemd subprocess/file ops (OSError,
# SubprocessError), lazy httpx health/metrics calls, mock-ZK RuntimeError,
# and data-shape errors. RuntimeError preserves catch of abort-style
# raises; BaseExceptions still propagate.
_OPS_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    SQLAlchemyError,
    httpx.HTTPError,
    ImportError,
    subprocess.SubprocessError,
)


# CE-003: instance_id is composed from user-supplied deployment_name and
# target_environment, then interpolated into a systemd unit file path,
# unit contents, and SyslogIdentifier. Anything outside this charset can
# inject directives (newline) or traverse the unit-file path (slash).
_SAFE_UNIT_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


def _validate_unit_component(value: str, field: str) -> str:
    """Reject values unsafe for interpolation into systemd units/paths."""
    if not isinstance(value, str) or not _SAFE_UNIT_COMPONENT_RE.match(value):
        raise ValueError(f"invalid {field}: must be 1-63 chars of [A-Za-z0-9._-], starting alphanumeric")
    return value


# #1932 F6: deployment fan-out spawns one systemd unit per instance, and both
# min_instances (deploy) and target_instances (scale, a query param) are
# caller-influenced. Clamp to the config's own max_instances AND a hard
# ceiling so a crafted config cannot request an unbounded fan-out.
_MAX_DEPLOYMENT_INSTANCES = 50


def _instance_ceiling(config: "AgentDeploymentConfig") -> int:
    """Effective per-deployment instance cap: config max_instances, hard-bound."""
    return max(0, min(int(config.max_instances), _MAX_DEPLOYMENT_INSTANCES))


_SESSION_LOCK_KEY = "_aitbc_agent_coordination_session_lock"


def _session_lock(session: Session | None) -> asyncio.Lock:
    """Return the asyncio.Lock shared by every manager bound to ``session``.

    The managers in this module are composed onto ONE Session —
    ``AgentProductionManager`` fans out to ``AgentDeploymentManager``,
    ``AgentMonitoringManager`` and ``AgentIntegrationManager``, each
    constructing its own ``AgentAuditor`` — so a per-instance lock (the
    #1904 ``AgentStateManager`` pattern) would not serialize across them.
    ``session.info`` hands every manager built on the same Session the
    same lock object.

    For ``session is None`` (test-only helper pins), each call returns a
    fresh lock — callers store it on the manager instance in ``__init__``.
    """
    if session is None:
        return asyncio.Lock()
    lock = session.info.get(_SESSION_LOCK_KEY)
    if not isinstance(lock, asyncio.Lock):
        lock = asyncio.Lock()
        session.info[_SESSION_LOCK_KEY] = lock
    return lock


def _serialized_session[F: Callable[..., Awaitable[Any]]](method: F) -> F:
    """Run an async manager method under the per-Session asyncio lock.

    Same serialization treatment as #1904's ``AgentStateManager._lock``,
    keyed on the Session (see ``_session_lock``) so managers composed onto
    one Session serialize with each other. Private helpers invoked from a
    decorated public method run inside the held lock and must not be
    decorated themselves — ``asyncio.Lock`` is not reentrant.
    """

    @functools.wraps(method)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        async with args[0]._lock:
            return await method(*args, **kwargs)

    return cast(F, wrapper)


def zk_integration_mock_enabled() -> bool:
    """Whether the mock ZK proof service may answer (dev/testing only)."""
    return os.getenv("AGENT_INTEGRATION_ZK_MOCK", "0") == "1"


class ZKProofService:
    """Mock ZK proof service for testing.

    Disabled by default: set ``AGENT_INTEGRATION_ZK_MOCK=1`` to enable. The
    mock mints made-up proof ids and always reports ``verified: true`` —
    fine for tests, unacceptable as an answer to a real caller (the service
    is reachable via the mounted agent-integration router).
    """

    def __init__(self, session: Any) -> None:
        self.session = session

    @staticmethod
    def _require_mock_enabled() -> None:
        if not zk_integration_mock_enabled():
            raise RuntimeError(
                "mock ZK proof service is disabled — set AGENT_INTEGRATION_ZK_MOCK=1 for development/testing only"
            )

    async def generate_zk_proof(self, circuit_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Mock ZK proof generation"""
        self._require_mock_enabled()
        return {
            "proof_id": f"proof_{uuid4().hex[:8]}",
            "circuit_name": circuit_name,
            "inputs": inputs,
            "proof_size": 1024,
            "generation_time": 0.1,
        }

    async def verify_proof(self, proof_id: str) -> dict[str, Any]:
        """Mock ZK proof verification"""
        self._require_mock_enabled()
        return {"verified": True, "verification_time": 0.05, "details": {"mock": True}}


class DeploymentStatus(StrEnum):
    """Deployment status enumeration"""

    PENDING = "pending"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    RETRYING = "retrying"
    TERMINATED = "terminated"


class AgentDeploymentConfig(SQLModel, table=True):
    """Configuration for agent deployment"""

    __tablename__ = "agent_deployment_configs"
    id: str = Field(default_factory=lambda: f"deploy_{uuid4().hex[:8]}", primary_key=True)
    workflow_id: str = Field(index=True)
    deployment_name: str = Field(max_length=100)
    description: str = Field(default="")
    version: str = Field(default="1.0.0")
    target_environments: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    deployment_regions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    min_cpu_cores: float = Field(default=1.0)
    min_memory_mb: int = Field(default=1024)
    min_storage_gb: int = Field(default=10)
    requires_gpu: bool = Field(default=False)
    gpu_memory_mb: int | None = Field(default=None)
    min_instances: int = Field(default=1)
    max_instances: int = Field(default=5)
    auto_scaling: bool = Field(default=True)
    scaling_policy: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    health_check_endpoint: str = Field(default="/health")
    health_check_interval: int = Field(default=30)
    health_check_timeout: int = Field(default=10)
    max_failures: int = Field(default=3)
    rollout_strategy: str = Field(default="rolling")
    rollback_enabled: bool = Field(default=True)
    deployment_timeout: int = Field(default=1800)
    enable_metrics: bool = Field(default=True)
    enable_logging: bool = Field(default=True)
    enable_tracing: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    alerting_rules: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    agent_version: str = Field(default="")
    previous_version: str = Field(default="")
    status: DeploymentStatus = Field(default=DeploymentStatus.PENDING)
    deployment_time: datetime | None = Field(default=None)
    last_health_check: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentDeploymentInstance(SQLModel, table=True):
    """Individual deployment instance tracking"""

    __tablename__ = "agent_deployment_instances"
    id: str = Field(default_factory=lambda: f"instance_{uuid4().hex[:10]}", primary_key=True)
    deployment_id: str = Field(index=True)
    instance_id: str = Field(index=True)
    environment: str = Field(index=True)
    region: str = Field(index=True)
    status: DeploymentStatus = Field(default=DeploymentStatus.PENDING)
    health_status: str = Field(default="unknown")
    endpoint_url: str | None = Field(default=None)
    internal_ip: str | None = Field(default=None)
    external_ip: str | None = Field(default=None)
    port: int | None = Field(default=None)
    cpu_usage: float | None = Field(default=None)
    memory_usage: int | None = Field(default=None)
    disk_usage: int | None = Field(default=None)
    gpu_usage: float | None = Field(default=None)
    request_count: int = Field(default=0)
    error_count: int = Field(default=0)
    average_response_time: float | None = Field(default=None)
    uptime_percentage: float | None = Field(default=None)
    last_health_check: datetime | None = Field(default=None)
    consecutive_failures: int = Field(default=0)
    health_check_history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentIntegrationManager:
    """Manages integration between agent orchestration and existing systems"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._lock = _session_lock(session)
        self.zk_service = ZKProofService(session)
        self.orchestrator = AIAgentOrchestrator(session, None)  # type: ignore[arg-type]
        self.security_manager = AgentSecurityManager(session)
        self.auditor = AgentAuditor(session)

    @_serialized_session
    async def integrate_with_zk_system(
        self, execution_id: str, verification_level: VerificationLevel = VerificationLevel.BASIC
    ) -> dict[str, Any]:
        """Integrate agent execution with ZK proof system"""
        try:
            execution = (
                await run_in_threadpool(self.session.scalars, select(AgentExecution).where(AgentExecution.id == execution_id))
            ).first()
            if not execution:
                raise ValueError(f"Execution not found: {execution_id}")
            step_executions = (
                await run_in_threadpool(
                    self.session.scalars, select(AgentStepExecution).where(AgentStepExecution.execution_id == execution_id)
                )
            ).all()
            # requires_proof lives on AgentStep, not AgentStepExecution — resolve
            # it from the workflow's step definitions.
            workflow_steps = (
                await run_in_threadpool(
                    self.session.scalars, select(AgentStep).where(AgentStep.workflow_id == execution.workflow_id)
                )
            ).all()
            step_requires_proof = {step.id: step.requires_proof for step in workflow_steps}
            integration_result: dict[str, Any] = {
                "execution_id": execution_id,
                "integration_status": "in_progress",
                "zk_proofs_generated": [],
                "verification_results": [],
                "integration_errors": [],
            }
            for step_execution in step_executions:
                if step_requires_proof.get(step_execution.step_id, False):
                    try:
                        proof_result = await self._generate_step_zk_proof(step_execution, verification_level)
                        integration_result["zk_proofs_generated"].append(
                            {
                                "step_id": step_execution.step_id,
                                "proof_id": proof_result["proof_id"],
                                "verification_level": verification_level,
                                "proof_size": proof_result["proof_size"],
                            }
                        )
                        verification_result = await self._verify_zk_proof(proof_result["proof_id"])
                        integration_result["verification_results"].append(
                            {
                                "step_id": step_execution.step_id,
                                "verification_status": verification_result["verified"],
                                "verification_time": verification_result["verification_time"],
                            }
                        )
                    except _OPS_ERRORS as e:
                        integration_result["integration_errors"].append(
                            {"step_id": step_execution.step_id, "error": str(e), "error_type": "zk_proof_generation"}
                        )
            try:
                workflow_proof = await self._generate_workflow_zk_proof(execution, list(step_executions), verification_level)
                integration_result["workflow_proof"] = {
                    "proof_id": workflow_proof["proof_id"],
                    "verification_level": verification_level,
                    "proof_size": workflow_proof["proof_size"],
                }
                workflow_verification = await self._verify_zk_proof(workflow_proof["proof_id"])
                integration_result["workflow_verification"] = {
                    "verified": workflow_verification["verified"],
                    "verification_time": workflow_verification["verification_time"],
                }
            except _OPS_ERRORS as e:
                integration_result["integration_errors"].append({"error": str(e), "error_type": "workflow_proof_generation"})
            if integration_result["integration_errors"]:
                integration_result["integration_status"] = "partial_success"
            else:
                integration_result["integration_status"] = "success"
            await self.auditor.log_event(
                AuditEventType.VERIFICATION_COMPLETED,
                execution_id=execution_id,
                security_level=SecurityLevel.INTERNAL,
                event_data={"integration_result": integration_result, "verification_level": verification_level},
            )
            return integration_result
        except Exception as e:
            logger.error("ZK integration failed: %s", e)
            await self.auditor.log_event(
                AuditEventType.VERIFICATION_FAILED,
                execution_id=execution_id,
                security_level=SecurityLevel.INTERNAL,
                event_data={"error": str(e)},
            )
            raise

    async def _generate_step_zk_proof(
        self, step_execution: AgentStepExecution, verification_level: VerificationLevel
    ) -> dict[str, Any]:
        """Generate ZK proof for individual step execution"""
        proof_inputs = {
            "step_id": step_execution.step_id,
            "execution_id": step_execution.execution_id,
            "step_type": "inference",
            "input_data": step_execution.input_data,
            "output_data": step_execution.output_data,
            "execution_time": step_execution.execution_time,
            "timestamp": step_execution.completed_at.isoformat() if step_execution.completed_at else None,
        }
        if verification_level == VerificationLevel.ZERO_KNOWLEDGE:
            proof_result = await self.zk_service.generate_zk_proof(circuit_name="agent_step_verification", inputs=proof_inputs)
        elif verification_level == VerificationLevel.FULL:
            proof_result = await self.zk_service.generate_zk_proof(
                circuit_name="agent_step_full_verification", inputs=proof_inputs
            )
        else:
            proof_result = await self.zk_service.generate_zk_proof(
                circuit_name="agent_step_basic_verification", inputs=proof_inputs
            )
        return proof_result

    async def _generate_workflow_zk_proof(
        self, execution: AgentExecution, step_executions: list[AgentStepExecution], verification_level: VerificationLevel
    ) -> dict[str, Any]:
        """Generate ZK proof for entire workflow execution"""
        step_proofs = []
        for step_execution in step_executions:
            if step_execution.step_proof:
                step_proofs.append(step_execution.step_proof)
        proof_inputs = {
            "execution_id": execution.id,
            "workflow_id": execution.workflow_id,
            "step_proofs": step_proofs,
            "final_result": execution.final_result,
            "total_execution_time": execution.total_execution_time,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        }
        circuit_name = f"agent_workflow_{verification_level.value}_verification"
        proof_result = await self.zk_service.generate_zk_proof(circuit_name=circuit_name, inputs=proof_inputs)
        return proof_result

    async def _verify_zk_proof(self, proof_id: str) -> dict[str, Any]:
        """Verify ZK proof"""
        verification_result = await self.zk_service.verify_proof(proof_id)
        return {
            "verified": verification_result["verified"],
            "verification_time": verification_result["verification_time"],
            "verification_details": verification_result.get("details", {}),
        }


# The deployment / monitoring / production managers live in
# integration_managers.py (#1860 phase 6 split). Re-exported here so the
# import surface — services.integration.AgentDeploymentManager and friends,
# plus the test/monkeypatch seams — is unchanged. This import must stay at
# the bottom: integration_managers imports the models and helpers defined
# above, so a top-level import would be circular.
from .integration_managers import (
    AgentDeploymentManager as AgentDeploymentManager,
    AgentMonitoringManager as AgentMonitoringManager,
    AgentProductionManager as AgentProductionManager,
)
