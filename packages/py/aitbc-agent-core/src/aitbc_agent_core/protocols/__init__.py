"""
Protocol definitions for agent service dependency injection.
"""

from .domain import (
    AgentStatus,
    VerificationLevel,
    StepType,
    IAgentExecution,
    IAgentStepExecution,
)
from .security import ISecurityManager, IAuditor
from .orchestrator import IAgentOrchestrator
from .zk_proof import IZKProofService
from .database import ISessionProvider

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
