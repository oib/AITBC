"""
Shared agent integration logic using protocol-based dependency injection.
This module contains pure business logic with no app-specific dependencies.
"""

from datetime import UTC, datetime
from typing import Any

from .protocols.database import ISessionProvider
from .protocols.orchestrator import IAgentOrchestrator
from .protocols.security import IAuditor, ISecurityManager
from .protocols.zk_proof import IZKProofService


class AgentIntegrationService:
    """
    Shared agent integration service with injected dependencies.
    All app-specific logic is abstracted through protocols.
    """

    def __init__(
        self,
        session_provider: ISessionProvider,
        security_manager: ISecurityManager,
        auditor: IAuditor,
        orchestrator: IAgentOrchestrator,
        zk_proof_service: IZKProofService | None = None,
    ):
        """
        Initialize the agent integration service with injected dependencies.

        Args:
            session_provider: Provider for database sessions
            security_manager: Manager for security validation
            auditor: Service for audit logging
            orchestrator: Service for workflow orchestration
            zk_proof_service: Optional service for ZK proof generation
        """
        self._session_provider = session_provider
        self._security_manager = security_manager
        self._auditor = auditor
        self._orchestrator = orchestrator
        self._zk_proof_service = zk_proof_service

    async def deploy_agent(
        self,
        workflow_id: str,
        deployment_config: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Deploy an agent with the given configuration.
        Pure business logic using only protocol interfaces.

        Args:
            workflow_id: ID of the workflow to deploy
            deployment_config: Configuration for deployment
            context: Additional context for the operation

        Returns:
            Deployment result with deployment_id and status
        """
        # Validate operation using security manager
        if not await self._security_manager.validate_operation(
            "deploy_agent", {"workflow_id": workflow_id, **(context or {})}
        ):
            raise PermissionError("Operation not authorized")

        # Execute deployment using orchestrator
        result = await self._orchestrator.execute_workflow(workflow_id, deployment_config)

        # Audit the deployment
        await self._auditor.audit_event(
            "agent_deployed",
            {
                "workflow_id": workflow_id,
                "deployment_id": result.get("deployment_id"),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        return result

    async def generate_verification_proof(
        self,
        execution_id: str,
        circuit_name: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate ZK proof for agent execution verification.

        Args:
            execution_id: ID of the execution to verify
            circuit_name: Name of the ZK circuit
            inputs: Circuit inputs

        Returns:
            Proof metadata including proof_id and verification status
        """
        if not self._zk_proof_service:
            raise RuntimeError("ZK proof service not configured")

        proof = await self._zk_proof_service.generate_zk_proof(circuit_name, inputs)

        await self._auditor.audit_event(
            "proof_generated",
            {
                "execution_id": execution_id,
                "proof_id": proof["proof_id"],
                "circuit_name": circuit_name,
            },
        )

        return proof

    async def verify_execution_proof(
        self,
        proof_id: str,
    ) -> dict[str, Any]:
        """
        Verify a ZK proof for agent execution.

        Args:
            proof_id: ID of the proof to verify

        Returns:
            Verification result with status and details
        """
        if not self._zk_proof_service:
            raise RuntimeError("ZK proof service not configured")

        verification = await self._zk_proof_service.verify_proof(proof_id)

        await self._auditor.audit_event(
            "proof_verified",
            {
                "proof_id": proof_id,
                "verified": verification.get("verified", False),
            },
        )

        return verification

    async def get_execution_status(
        self,
        execution_id: str,
    ) -> dict[str, Any]:
        """
        Get the status of an agent execution.

        Args:
            execution_id: ID of the execution to query

        Returns:
            Current execution status and metadata
        """
        return await self._orchestrator.get_status(execution_id)
