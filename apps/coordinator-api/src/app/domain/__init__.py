"""Domain models for the coordinator API."""

# agent.py and agent_performance.py have been migrated to
# contexts/agent_coordination/domain/. Re-exported here so that
# SQLModel.metadata table registration still happens when app.domain
# is imported (e.g. during init_db), and any legacy name imports keep working.
from ..contexts.agent_coordination.domain.agent import (
    AgentExecution,
    AgentMarketplace,
    AgentStatus,
    AgentStep,
    AgentStepExecution,
    AIAgentWorkflow,
    VerificationLevel,
)
from .job import Job
from .job_receipt import JobReceipt
from .miner import Miner
from .user import Transaction, User, UserSession, Wallet

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
