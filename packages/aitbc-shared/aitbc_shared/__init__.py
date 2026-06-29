"""
AITBC Shared Package
Shared ORM models, utilities, and configuration for AITBC applications
"""

from .core.config import DatabaseConfig, ServiceSettings
from .models import JobPayment, MarketplaceBid, MarketplaceOffer, PaymentEscrow, ReputationDTO
from .orm import get_engine, get_session, init_db

__all__ = [
    # Config
    "DatabaseConfig",
    "ServiceSettings",
    # Models
    "MarketplaceOffer",
    "MarketplaceBid",
    "JobPayment",
    "PaymentEscrow",
    "ReputationDTO",
    # ORM utilities
    "get_engine",
    "get_session",
    "init_db",
]
