# mypy: ignore-errors
"""
Factory for creating shared AgentIntegrationService with app-specific adapters.
This enables gradual migration from duplicated code to shared implementation.
"""


from aitbc_agent_core import AgentIntegrationService

from ..database import get_session
from .adapters.agent_core_adapters import (
    AgentAuditorAdapter,
    AgentOrchestratorAdapter,
    AgentSecurityManagerAdapter,
    SessionProviderAdapter,
    ZKProofServiceAdapter,
)
from .agent_security import AgentAuditor, AgentSecurityManager
from .agent_service import AIAgentOrchestrator


def create_agent_integration_service() -> AgentIntegrationService:
    """
    Factory to create shared AgentIntegrationService with app-specific adapters.
    
    Returns:
        Configured AgentIntegrationService instance
    """
    # Create app-specific service instances
    security_manager = AgentSecurityManager()
    auditor = AgentAuditor()
    orchestrator = AIAgentOrchestrator()

    # Wrap with protocol adapters
    return AgentIntegrationService(
        session_provider=SessionProviderAdapter(get_session),
        security_manager=AgentSecurityManagerAdapter(security_manager),
        auditor=AgentAuditorAdapter(auditor),
        orchestrator=AgentOrchestratorAdapter(orchestrator),
        zk_proof_service=ZKProofServiceAdapter(get_session()),
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
        _shared_service = create_agent_integration_service()
    return _shared_service
