"""
Models package for the AITBC Coordinator API
"""

# Import basic types from types.py to avoid circular imports
from aitbc_shared import MarketplaceOffer, JobPayment, PaymentEscrow
from ..custom_types import (
    Constraints,
    JobState,
)

# Import domain models
from ..contexts.infrastructure.domain import (
    Job,
    JobReceipt,
    Miner,
    User,
    Wallet,
)

# Import schemas from schemas.py
from ..schemas import (
    AccessLogQuery,
    AccessLogResponse,
    AddressListResponse,
    AddressSummary,
    AssignedJob,
    AuditAuthorization,
    BlockListResponse,
    BlockSummary,
    ConfidentialAccessLog,
    ConfidentialAccessRequest,
    ConfidentialAccessResponse,
    ConfidentialTransaction,
    ConfidentialTransactionCreate,
    ConfidentialTransactionView,
    ExchangePaymentRequest,
    ExchangePaymentResponse,
    JobCreate,
    JobFailSubmit,
    JobResult,
    JobResultSubmit,
    JobView,
    KeyPair,
    KeyRegistrationRequest,
    KeyRegistrationResponse,
    KeyRotationLog,
    MarketplaceOfferView,
    MarketplaceStatsView,
    MinerHeartbeat,
    MinerRegister,
    PollRequest,
    Receipt,
    ReceiptListResponse,
    ReceiptSummary,
    TransactionListResponse,
    TransactionSummary,
)

# Service-specific models
from .services import (
    BlenderRequest,
    FFmpegRequest,
    LLMRequest,
    ServiceRequest,
    ServiceResponse,
    ServiceType,
    StableDiffusionRequest,
    WhisperRequest,
)

# from .confidential import ConfidentialReceipt, ConfidentialAttestation
# from .multitenant import Tenant, TenantConfig, TenantUser
# from .registry import (
#     ServiceRegistry,
#     ServiceRegistration,
#     ServiceHealthCheck,
#     ServiceMetrics,
# )
# from .registry_data import DataService, DataServiceConfig
# from .registry_devtools import DevToolService, DevToolConfig
# from .registry_gaming import GamingService, GamingConfig
# from .registry_media import MediaService, MediaConfig
# from .registry_scientific import ScientificService, ScientificConfig

__all__ = [
    "JobState",
    "JobCreate",
    "JobView",
    "JobResult",
    "Constraints",
    "Job",
    "Miner",
    "JobReceipt",
    "MarketplaceOffer",
    "ServiceType",
    "ServiceRequest",
    "ServiceResponse",
    "WhisperRequest",
    "StableDiffusionRequest",
    "LLMRequest",
    "FFmpegRequest",
    "BlenderRequest",
    "JobPayment",
    "PaymentEscrow",
]
