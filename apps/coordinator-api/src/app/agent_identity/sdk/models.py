"""
SDK Models
Data models for the Agent Identity SDK
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class IdentityStatus(StrEnum):
    """Agent identity status enumeration"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class VerificationType(StrEnum):
    """Identity verification type enumeration"""

    BASIC = "basic"
    ADVANCED = "advanced"
    ZERO_KNOWLEDGE = "zero-knowledge"
    MULTI_SIGNATURE = "multi-signature"


class ChainType(StrEnum):
    """Blockchain chain type enumeration"""

    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    BSC = "bsc"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    AVALANCHE = "avalanche"
    SOLANA = "solana"
    CUSTOM = "custom"


@dataclass
class AgentIdentity:
    """Agent identity model"""

    id: str
    agent_id: str
    owner_address: str
    display_name: str
    description: str
    avatar_url: str
    status: IdentityStatus
    verification_level: VerificationType
    is_verified: bool
    verified_at: datetime | None
    supported_chains: list[str]
    primary_chain: int
    reputation_score: float
    total_transactions: int
    successful_transactions: int
    success_rate: float
    created_at: datetime
    updated_at: datetime
    last_activity: datetime | None
    metadata: dict[str, Any]
    tags: list[str]


@dataclass
class CrossChainMapping:
    """Cross-chain mapping model"""

    id: str
    agent_id: str
    chain_id: int
    chain_type: ChainType
    chain_address: str
    is_verified: bool
    verified_at: datetime | None
    wallet_address: str | None
    wallet_type: str
    chain_metadata: dict[str, Any]
    last_transaction: datetime | None
    transaction_count: int
    created_at: datetime
    updated_at: datetime


@dataclass
class AgentWallet:
    """Agent wallet model"""

    id: str
    agent_id: str
    chain_id: int
    chain_address: str
    wallet_type: str
    contract_address: str | None
    balance: float
    spending_limit: float
    total_spent: float
    is_active: bool
    permissions: list[str]
    requires_multisig: bool
    multisig_threshold: int
    multisig_signers: list[str]
    last_transaction: datetime | None
    transaction_count: int
    created_at: datetime
    updated_at: datetime


@dataclass
class Transaction:
    """Transaction model"""

    hash: str
    from_address: str
    to_address: str
    amount: str
    gas_used: str
    gas_price: str
    status: str
    block_number: int
    timestamp: datetime


@dataclass
class Verification:
    """Verification model"""

    id: str
    agent_id: str
    chain_id: int
    verification_type: VerificationType
    verifier_address: str
    proof_hash: str
    proof_data: dict[str, Any]
    verification_result: str
    created_at: datetime
    expires_at: datetime | None


@dataclass
class ChainConfig:
    """Chain configuration model"""

    chain_id: int
    chain_type: ChainType
    name: str
    rpc_url: str
    block_explorer_url: str | None
    native_currency: str
    decimals: int


@dataclass
class CreateIdentityRequest:
    """Request model for creating identity"""

    owner_address: str
    chains: list[int]
    display_name: str = ""
    description: str = ""
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None


@dataclass
class UpdateIdentityRequest:
    """Request model for updating identity"""

    display_name: str | None = None
    description: str | None = None
    avatar_url: str | None = None
    status: IdentityStatus | None = None
    verification_level: VerificationType | None = None
    supported_chains: list[int] | None = None
    primary_chain: int | None = None
    metadata: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    tags: list[str] | None = None


@dataclass
class CreateMappingRequest:
    """Request model for creating cross-chain mapping"""

    chain_id: int
    chain_address: str
    wallet_address: str | None = None
    wallet_type: str = "agent-wallet"
    chain_metadata: dict[str, Any] | None = None


@dataclass
class VerifyIdentityRequest:
    """Request model for identity verification"""

    chain_id: int
    verifier_address: str
    proof_hash: str
    proof_data: dict[str, Any]
    verification_type: VerificationType = VerificationType.BASIC
    expires_at: datetime | None = None


@dataclass
class TransactionRequest:
    """Request model for transaction execution"""

    to_address: str
    amount: float
    data: dict[str, Any] | None = None
    gas_limit: int | None = None
    gas_price: str | None = None


@dataclass
class SearchRequest:
    """Request model for searching identities"""

    query: str = ""
    chains: list[int] | None = None
    status: IdentityStatus | None = None
    verification_level: VerificationType | None = None
    min_reputation: float | None = None
    limit: int = 50
    offset: int = 0


@dataclass
class MigrationRequest:
    """Request model for identity migration"""

    from_chain: int
    to_chain: int
    new_address: str
    verifier_address: str | None = None


@dataclass
class WalletStatistics:
    """Wallet statistics model"""

    total_wallets: int
    active_wallets: int
    total_balance: float
    total_spent: float
    total_transactions: int
    average_balance_per_wallet: float
    chain_breakdown: dict[str, dict[str, Any]]
    supported_chains: list[str]


@dataclass
class IdentityStatistics:
    """Identity statistics model"""

    total_identities: int
    total_mappings: int
    verified_mappings: int
    verification_rate: float
    total_verifications: int
    supported_chains: int
    chain_breakdown: dict[str, dict[str, Any]]


@dataclass
class RegistryHealth:
    """Registry health model"""

    status: str
    registry_statistics: IdentityStatistics
    supported_chains: list[ChainConfig]
    cleaned_verifications: int
    issues: list[str]
    timestamp: datetime


# Response models
@dataclass
class CreateIdentityResponse:
    """Response model for identity creation"""

    identity_id: str
    agent_id: str
    owner_address: str
    display_name: str
    supported_chains: list[int]
    primary_chain: int
    registration_result: dict[str, Any]
    wallet_results: list[dict[str, Any]]
    created_at: str


@dataclass
class UpdateIdentityResponse:
    """Response model for identity update"""

    agent_id: str
    identity_id: str
    updated_fields: list[str]
    updated_at: str


@dataclass
class VerifyIdentityResponse:
    """Response model for identity verification"""

    verification_id: str
    agent_id: str
    chain_id: int
    verification_type: VerificationType
    verified: bool
    timestamp: str


@dataclass
class TransactionResponse:
    """Response model for transaction execution"""

    transaction_hash: str
    from_address: str
    to_address: str
    amount: str
    gas_used: str
    gas_price: str
    status: str
    block_number: int
    timestamp: str


@dataclass
class SearchResponse:
    """Response model for identity search"""

    results: list[dict[str, Any]]
    total_count: int
    query: str
    filters: dict[str, Any]
    pagination: dict[str, Any]


@dataclass
class SyncReputationResponse:
    """Response model for reputation synchronization"""

    agent_id: str
    aggregated_reputation: float
    chain_reputations: dict[int, float]
    verified_chains: list[int]
    sync_timestamp: str


@dataclass
class MigrationResponse:
    """Response model for identity migration"""

    agent_id: str
    from_chain: int
    to_chain: int
    source_address: str
    target_address: str
    migration_successful: bool
    action: str | None
    verification_copied: bool | None
    wallet_created: bool | None
    wallet_id: str | None
    wallet_address: str | None
    error: str | None = None
