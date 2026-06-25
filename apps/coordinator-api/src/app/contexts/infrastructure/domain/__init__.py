"""Infrastructure domain models.

Core platform models (Job, JobReceipt, Miner, User, Wallet, Transaction,
UserSession) migrated from flat app/domain/ in v0.5.14.
"""

from app.contexts.infrastructure.domain.job import Job
from app.contexts.infrastructure.domain.job_receipt import JobReceipt
from app.contexts.infrastructure.domain.miner import Miner
from app.contexts.infrastructure.domain.user import Transaction, User, UserSession, Wallet

__all__ = [
    "Job",
    "JobReceipt",
    "Miner",
    "Transaction",
    "User",
    "UserSession",
    "Wallet",
]
