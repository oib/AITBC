"""
Factory for creating shared AgentIntegrationService with app-specific adapters.
This enables gradual migration from duplicated code to shared implementation.
"""

from sqlmodel import Session

from aitbc_agent_core import AgentIntegrationService
from ..adapters.agent_core_adapters import (
    AgentSecurityManagerAdapter,
    AgentAuditorAdapter,
    AgentOrchestratorAdapter,
    ZKProofServiceAdapter,
    SessionProviderAdapter,
)
from .agent_coordination.security import AgentSecurityManager, AgentAuditor
from .agent_coordination.agent_service import AIAgentOrchestrator, CoordinatorClient
from ..storage.db import get_session


def create_agent_integration_service(session: Session) -> AgentIntegrationService:
    """
    Factory to create shared AgentIntegrationService with app-specific adapters.

    Returns:
        Configured AgentIntegrationService instance
    """
    security_manager = AgentSecurityManager(session=session)
    auditor = AgentAuditor(session=session)
    coordinator_client = CoordinatorClient()
    orchestrator = AIAgentOrchestrator(session=session, coordinator_client=coordinator_client)

    return AgentIntegrationService(
        session_provider=SessionProviderAdapter(get_session),
        security_manager=AgentSecurityManagerAdapter(security_manager),
        auditor=AgentAuditorAdapter(auditor),
        orchestrator=AgentOrchestratorAdapter(orchestrator),
        zk_proof_service=ZKProofServiceAdapter(session),
    )


# Singleton instance for app-wide use
_shared_service: AgentIntegrationService | None = None


def get_shared_agent_integration_service() -> AgentIntegrationService:
    """
    Get or create the shared AgentIntegrationService singleton.
    
    Returns:
        Shared AgentIntegrationService instance
    """
    global _shared_service
    if _shared_service is None:
        from sqlmodel import Session as SQLModelSession
        from ..storage.db import get_engine
        with SQLModelSession(get_engine()) as _sess:
            _shared_service = create_agent_integration_service(_sess)
    return _shared_service
