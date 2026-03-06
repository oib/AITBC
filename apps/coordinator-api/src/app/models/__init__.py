"""
Models package for the AITBC Coordinator API
"""

# Import basic types from types.py to avoid circular imports
from ..types import (
    JobState,
    Constraints,
)

# Import schemas from schemas.py
from ..schemas import (
    JobCreate,
    JobView,
    JobResult,
    AssignedJob,
    MinerHeartbeat,
    MinerRegister,
    MarketplaceBidRequest,
    MarketplaceOfferView,
    MarketplaceStatsView,
    BlockSummary,
    BlockListResponse,
    TransactionSummary,
    TransactionListResponse,
    AddressSummary,
    AddressListResponse,
    ReceiptSummary,
    ReceiptListResponse,
    ExchangePaymentRequest,
    ExchangePaymentResponse,
    ConfidentialTransaction,
    ConfidentialTransactionCreate,
    ConfidentialTransactionView,
    ConfidentialAccessRequest,
    ConfidentialAccessResponse,
    KeyPair,
    KeyRotationLog,
    AuditAuthorization,
    KeyRegistrationRequest,
    KeyRegistrationResponse,
    ConfidentialAccessLog,
    AccessLogQuery,
    AccessLogResponse,
    Receipt,
    JobFailSubmit,
    JobResultSubmit,
    PollRequest,
)

# Import domain models
from ..domain import (
    Job,
    Miner,
    JobReceipt,
    MarketplaceOffer,
    MarketplaceBid,
    User,
    Wallet,
    JobPayment,
    PaymentEscrow,
)

# Service-specific models
from .services import (
    ServiceType,
    ServiceRequest,
    ServiceResponse,
    WhisperRequest,
    StableDiffusionRequest,
    LLMRequest,
    FFmpegRequest,
    BlenderRequest,
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
    "MarketplaceBid",
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
