"""
Protocol definitions for agent service dependency injection.
"""

from .database import ISessionProvider
from .domain import (
    AgentStatus,
    IAgentExecution,
    IAgentStepExecution,
    StepType,
    VerificationLevel,
)
from .orchestrator import IAgentOrchestrator
from .security import IAuditor, ISecurityManager
from .zk_proof import IZKProofService

__all__ = [
    # Domain protocols
    "AgentStatus",
    "VerificationLevel",
    "StepType",
    "IAgentExecution",
    "IAgentStepExecution",
    # Security protocols
    "ISecurityManager",
    "IAuditor",
    # Orchestration protocols
    "IAgentOrchestrator",
    # ZK proof protocols
    "IZKProofService",
    # Database protocols
    "ISessionProvider",
]
