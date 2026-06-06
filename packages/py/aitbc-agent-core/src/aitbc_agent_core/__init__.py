"""
AITBC Agent Core - Shared agent service logic with protocol-based dependency injection.

This package provides shared business logic for agent integration and orchestration
using protocol-based dependency injection to avoid coupling to app-specific implementations.
"""

__version__ = "0.1.0"

from .integration import AgentIntegrationService
from .protocols import (
    AgentStatus,
    IAgentExecution,
    IAgentOrchestrator,
    IAgentStepExecution,
    IAuditor,
    ISecurityManager,
    ISessionProvider,
    IZKProofService,
    StepType,
    VerificationLevel,
)

__all__ = [
    # Version
    "__version__",
    # Protocols
    "AgentStatus",
    "VerificationLevel",
    "StepType",
    "IAgentExecution",
    "IAgentStepExecution",
    "ISecurityManager",
    "IAuditor",
    "IAgentOrchestrator",
    "IZKProofService",
    "ISessionProvider",
    # Core service
    "AgentIntegrationService",
]
