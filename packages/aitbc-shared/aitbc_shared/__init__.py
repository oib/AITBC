"""
AITBC Shared Package
Shared ORM models, utilities, and configuration for AITBC applications
"""

from .core.config import DatabaseConfig, ServiceSettings
from .models import JobPayment, MarketOffer, PaymentEscrow, ReputationDTO
from .orm import get_engine, get_session, init_db

__all__ = [
    # Config
    "DatabaseConfig",
    "ServiceSettings",
    # Models
    "MarketOffer",
    "JobPayment",
    "PaymentEscrow",
    "ReputationDTO",
    # ORM utilities
    "get_engine",
    "get_session",
    "init_db",
]
