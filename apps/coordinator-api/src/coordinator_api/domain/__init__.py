"""Domain models for the coordinator API.

Compatibility shim — all model files have been migrated to bounded contexts.
Re-exports are kept here so that SQLModel.metadata table registration still
happens when app.domain is imported (e.g. during init_db), and legacy
name imports keep working.
"""

from ..contexts.agent_coordination.domain.agent import (
    AgentExecution,
    AgentMarketplace,
    AgentStatus,
    AgentStep,
    AgentStepExecution,
    AIAgentWorkflow,
    VerificationLevel,
)
from ..contexts.infrastructure.domain import Job, JobReceipt, Miner, Transaction, User, UserSession, Wallet

__all__ = [
    "Job",
    "Miner",
    "JobReceipt",
    "User",
    "Wallet",
    "Transaction",
    "UserSession",
    "AIAgentWorkflow",
    "AgentStep",
    "AgentExecution",
    "AgentStepExecution",
    "AgentMarketplace",
    "AgentStatus",
    "VerificationLevel",
]
