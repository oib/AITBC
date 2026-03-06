"""
SDK Models
Data models for the Agent Identity SDK
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, Any
from datetime import datetime
from enum import Enum


class IdentityStatus(str, Enum):
    """Agent identity status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class VerificationType(str, Enum):
    """Identity verification type enumeration"""
    BASIC = "basic"
    ADVANCED = "advanced"
    ZERO_KNOWLEDGE = "zero-knowledge"
    MULTI_SIGNATURE = "multi-signature"


class ChainType(str, Enum):
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
    verified_at: Optional[datetime]
    supported_chains: List[str]
    primary_chain: int
    reputation_score: float
    total_transactions: int
    successful_transactions: int
    success_rate: float
    created_at: datetime
    updated_at: datetime
    last_activity: Optional[datetime]
    metadata: Dict[str, Any]
    tags: List[str]


@dataclass
class CrossChainMapping:
    """Cross-chain mapping model"""
    id: str
    agent_id: str
    chain_id: int
    chain_type: ChainType
    chain_address: str
    is_verified: bool
    verified_at: Optional[datetime]
    wallet_address: Optional[str]
    wallet_type: str
    chain_metadata: Dict[str, Any]
    last_transaction: Optional[datetime]
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
    contract_address: Optional[str]
    balance: float
    spending_limit: float
    total_spent: float
    is_active: bool
    permissions: List[str]
    requires_multisig: bool
    multisig_threshold: int
    multisig_signers: List[str]
    last_transaction: Optional[datetime]
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
    proof_data: Dict[str, Any]
    verification_result: str
    created_at: datetime
    expires_at: Optional[datetime]


@dataclass
class ChainConfig:
    """Chain configuration model"""
    chain_id: int
    chain_type: ChainType
    name: str
    rpc_url: str
    block_explorer_url: Optional[str]
    native_currency: str
    decimals: int


@dataclass
class CreateIdentityRequest:
    """Request model for creating identity"""
    owner_address: str
    chains: List[int]
    display_name: str = ""
    description: str = ""
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


@dataclass
class UpdateIdentityRequest:
    """Request model for updating identity"""
    display_name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    status: Optional[IdentityStatus] = None
    verification_level: Optional[VerificationType] = None
    supported_chains: Optional[List[int]] = None
    primary_chain: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


@dataclass
class CreateMappingRequest:
    """Request model for creating cross-chain mapping"""
    chain_id: int
    chain_address: str
    wallet_address: Optional[str] = None
    wallet_type: str = "agent-wallet"
    chain_metadata: Optional[Dict[str, Any]] = None


@dataclass
class VerifyIdentityRequest:
    """Request model for identity verification"""
    chain_id: int
    verifier_address: str
    proof_hash: str
    proof_data: Dict[str, Any]
    verification_type: VerificationType = VerificationType.BASIC
    expires_at: Optional[datetime] = None


@dataclass
class TransactionRequest:
    """Request model for transaction execution"""
    to_address: str
    amount: float
    data: Optional[Dict[str, Any]] = None
    gas_limit: Optional[int] = None
    gas_price: Optional[str] = None


@dataclass
class SearchRequest:
    """Request model for searching identities"""
    query: str = ""
    chains: Optional[List[int]] = None
    status: Optional[IdentityStatus] = None
    verification_level: Optional[VerificationType] = None
    min_reputation: Optional[float] = None
    limit: int = 50
    offset: int = 0


@dataclass
class MigrationRequest:
    """Request model for identity migration"""
    from_chain: int
    to_chain: int
    new_address: str
    verifier_address: Optional[str] = None


@dataclass
class WalletStatistics:
    """Wallet statistics model"""
    total_wallets: int
    active_wallets: int
    total_balance: float
    total_spent: float
    total_transactions: int
    average_balance_per_wallet: float
    chain_breakdown: Dict[str, Dict[str, Any]]
    supported_chains: List[str]


@dataclass
class IdentityStatistics:
    """Identity statistics model"""
    total_identities: int
    total_mappings: int
    verified_mappings: int
    verification_rate: float
    total_verifications: int
    supported_chains: int
    chain_breakdown: Dict[str, Dict[str, Any]]


@dataclass
class RegistryHealth:
    """Registry health model"""
    status: str
    registry_statistics: IdentityStatistics
    supported_chains: List[ChainConfig]
    cleaned_verifications: int
    issues: List[str]
    timestamp: datetime


# Response models
@dataclass
class CreateIdentityResponse:
    """Response model for identity creation"""
    identity_id: str
    agent_id: str
    owner_address: str
    display_name: str
    supported_chains: List[int]
    primary_chain: int
    registration_result: Dict[str, Any]
    wallet_results: List[Dict[str, Any]]
    created_at: str


@dataclass
class UpdateIdentityResponse:
    """Response model for identity update"""
    agent_id: str
    identity_id: str
    updated_fields: List[str]
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
    results: List[Dict[str, Any]]
    total_count: int
    query: str
    filters: Dict[str, Any]
    pagination: Dict[str, Any]


@dataclass
class SyncReputationResponse:
    """Response model for reputation synchronization"""
    agent_id: str
    aggregated_reputation: float
    chain_reputations: Dict[int, float]
    verified_chains: List[int]
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
    action: Optional[str]
    verification_copied: Optional[bool]
    wallet_created: Optional[bool]
    wallet_id: Optional[str]
    wallet_address: Optional[str]
    error: Optional[str] = None
