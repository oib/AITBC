"""
Agent Identity Domain Models for Cross-Chain Agent Identity Management
Implements SQLModel definitions for unified agent identity across multiple blockchains
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel


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


class AgentIdentity(SQLModel, table=True):
    """Unified agent identity across blockchains"""

    __tablename__ = "agent_identities"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"identity_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True, unique=True)  # Links to AIAgentWorkflow.id
    owner_address: str = Field(index=True)

    # Identity metadata
    display_name: str = Field(max_length=100, default="")
    description: str = Field(default="")
    avatar_url: str = Field(default="")

    # Status and verification
    status: IdentityStatus = Field(default=IdentityStatus.ACTIVE)
    verification_level: VerificationType = Field(default=VerificationType.BASIC)
    is_verified: bool = Field(default=False)
    verified_at: datetime | None = Field(default=None)

    # Cross-chain capabilities
    supported_chains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    primary_chain: int = Field(default=1)  # Default to Ethereum mainnet

    # Reputation and trust
    reputation_score: float = Field(default=0.0)
    total_transactions: int = Field(default=0)
    successful_transactions: int = Field(default=0)
    last_activity: datetime | None = Field(default=None)

    # Metadata and settings
    identity_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    settings_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))

    # Indexes for performance
    __table_args__ = {
#        # Index(        Index("idx_agent_identity_owner", "owner_address"),)
#        # Index(        Index("idx_agent_identity_status", "status"),)
#        # Index(        Index("idx_agent_identity_verified", "is_verified"),)
#        # Index(        Index("idx_agent_identity_reputation", "reputation_score"),)
    }


class CrossChainMapping(SQLModel, table=True):
    """Mapping of agent identity across different blockchains"""

    __tablename__ = "cross_chain_mappings"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"mapping_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True)
    chain_id: int = Field(index=True)
    chain_type: ChainType = Field(default=ChainType.ETHEREUM)
    chain_address: str = Field(index=True)

    # Verification and status
    is_verified: bool = Field(default=False)
    verified_at: datetime | None = Field(default=None)
    verification_proof: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    # Wallet information
    wallet_address: str | None = Field(default=None)
    wallet_type: str = Field(default="agent-wallet")  # agent-wallet, external-wallet, etc.

    # Chain-specific metadata
    chain_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    nonce: int | None = Field(default=None)

    # Activity tracking
    last_transaction: datetime | None = Field(default=None)
    transaction_count: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))

    # Unique constraint
    __table_args__ = {
#        # Index(        Index("idx_cross_chain_agent_chain", "agent_id", "chain_id"),)
#        # Index(        Index("idx_cross_chain_address", "chain_address"),)
#        # Index(        Index("idx_cross_chain_verified", "is_verified"),)
    }


class IdentityVerification(SQLModel, table=True):
    """Verification records for cross-chain identities"""

    __tablename__ = "identity_verifications"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"verify_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True)
    chain_id: int = Field(index=True)

    # Verification details
    verification_type: VerificationType
    verifier_address: str = Field(index=True)  # Who performed the verification
    proof_hash: str = Field(index=True)
    proof_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Status and results
    is_valid: bool = Field(default=True)
    verification_result: str = Field(default="pending")  # pending, approved, rejected
    rejection_reason: str | None = Field(default=None)

    # Expiration and renewal
    expires_at: datetime | None = Field(default=None)
    renewed_at: datetime | None = Field(default=None)

    # Metadata
    verification_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))

    # Indexes
    __table_args__ = {
#        # Index(        Index("idx_identity_verify_agent_chain", "agent_id", "chain_id"),)
#        # Index(        Index("idx_identity_verify_verifier", "verifier_address"),)
#        # Index(        Index("idx_identity_verify_hash", "proof_hash"),)
#        # Index(        Index("idx_identity_verify_result", "verification_result"),)
    }


class AgentWallet(SQLModel, table=True):
    """Agent wallet information for cross-chain operations"""

    __tablename__ = "agent_wallets"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"wallet_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True)
    chain_id: int = Field(index=True)
    chain_address: str = Field(index=True)

    # Wallet details
    wallet_type: str = Field(default="agent-wallet")
    contract_address: str | None = Field(default=None)

    # Financial information
    balance: float = Field(default=0.0)
    spending_limit: float = Field(default=0.0)
    total_spent: float = Field(default=0.0)

    # Status and permissions
    is_active: bool = Field(default=True)
    permissions: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Security
    requires_multisig: bool = Field(default=False)
    multisig_threshold: int = Field(default=1)
    multisig_signers: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Activity tracking
    last_transaction: datetime | None = Field(default=None)
    transaction_count: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))

    # Indexes
    __table_args__ = {
#        # Index(        Index("idx_agent_wallet_agent_chain", "agent_id", "chain_id"),)
#        # Index(        Index("idx_agent_wallet_address", "chain_address"),)
#        # Index(        Index("idx_agent_wallet_active", "is_active"),)
    }


# Request/Response Models for API
class AgentIdentityCreate(SQLModel):
    """Request model for creating agent identities"""

    agent_id: str
    owner_address: str
    display_name: str = Field(max_length=100, default="")
    description: str = Field(default="")
    avatar_url: str = Field(default="")
    supported_chains: list[int] = Field(default_factory=list)
    primary_chain: int = Field(default=1)
    meta_data: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class AgentIdentityUpdate(SQLModel):
    """Request model for updating agent identities"""

    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None)
    avatar_url: str | None = Field(default=None)
    status: IdentityStatus | None = Field(default=None)
    verification_level: VerificationType | None = Field(default=None)
    supported_chains: list[int] | None = Field(default=None)
    primary_chain: int | None = Field(default=None)
    meta_data: dict[str, Any] | None = Field(default=None)
    settings: dict[str, Any] | None = Field(default=None)
    tags: list[str] | None = Field(default=None)


class CrossChainMappingCreate(SQLModel):
    """Request model for creating cross-chain mappings"""

    agent_id: str
    chain_id: int
    chain_type: ChainType = Field(default=ChainType.ETHEREUM)
    chain_address: str
    wallet_address: str | None = Field(default=None)
    wallet_type: str = Field(default="agent-wallet")
    chain_meta_data: dict[str, Any] = Field(default_factory=dict)


class CrossChainMappingUpdate(SQLModel):
    """Request model for updating cross-chain mappings"""

    chain_address: str | None = Field(default=None)
    wallet_address: str | None = Field(default=None)
    wallet_type: str | None = Field(default=None)
    chain_meta_data: dict[str, Any] | None = Field(default=None)
    is_verified: bool | None = Field(default=None)


class IdentityVerificationCreate(SQLModel):
    """Request model for creating identity verifications"""

    agent_id: str
    chain_id: int
    verification_type: VerificationType
    verifier_address: str
    proof_hash: str
    proof_data: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = Field(default=None)
    verification_meta_data: dict[str, Any] = Field(default_factory=dict)


class AgentWalletCreate(SQLModel):
    """Request model for creating agent wallets"""

    agent_id: str
    chain_id: int
    chain_address: str
    wallet_type: str = Field(default="agent-wallet")
    contract_address: str | None = Field(default=None)
    spending_limit: float = Field(default=0.0)
    permissions: list[str] = Field(default_factory=list)
    requires_multisig: bool = Field(default=False)
    multisig_threshold: int = Field(default=1)
    multisig_signers: list[str] = Field(default_factory=list)


class AgentWalletUpdate(SQLModel):
    """Request model for updating agent wallets"""

    contract_address: str | None = Field(default=None)
    spending_limit: float | None = Field(default=None)
    permissions: list[str] | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    requires_multisig: bool | None = Field(default=None)
    multisig_threshold: int | None = Field(default=None)
    multisig_signers: list[str] | None = Field(default=None)


# Response Models
class AgentIdentityResponse(SQLModel):
    """Response model for agent identity"""

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
    last_activity: datetime | None
    meta_data: dict[str, Any]
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class CrossChainMappingResponse(SQLModel):
    """Response model for cross-chain mapping"""

    id: str
    agent_id: str
    chain_id: int
    chain_type: ChainType
    chain_address: str
    is_verified: bool
    verified_at: datetime | None
    wallet_address: str | None
    wallet_type: str
    chain_meta_data: dict[str, Any]
    last_transaction: datetime | None
    transaction_count: int
    created_at: datetime
    updated_at: datetime


class AgentWalletResponse(SQLModel):
    """Response model for agent wallet"""

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
