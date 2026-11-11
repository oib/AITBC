"""
Cross-Chain Bridge Domain Models

Domain models for cross-chain asset transfers, bridge requests, and validator management.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import field_validator
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from coordinator_api.validators import validate_ethereum_address, validate_positive_decimal, validate_url


class BridgeRequestStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RESOLVED = "resolved"


class ChainType(StrEnum):
    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    BSC = "bsc"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    AVALANCHE = "avalanche"
    FANTOM = "fantom"
    HARMONY = "harmony"


class TransactionType(StrEnum):
    INITIATION = "initiation"
    CONFIRMATION = "confirmation"
    COMPLETION = "completion"
    REFUND = "refund"
    DISPUTE = "dispute"


class ValidatorStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    SLASHED = "slashed"


class BridgeRequest(SQLModel, table=True):
    """Cross-chain bridge transfer request"""

    __tablename__ = "bridge_request"

    id: int | None = Field(default=None, primary_key=True)
    contract_request_id: str = Field(index=True)
    sender_address: str = Field(index=True, max_length=42)
    recipient_address: str = Field(index=True, max_length=42)
    source_token: str = Field(index=True, max_length=42)  # Source token address
    target_token: str = Field(index=True, max_length=42)  # Target token address
    source_chain_id: int = Field(index=True)
    target_chain_id: int = Field(index=True)
    amount: Decimal = Field(default=Decimal("0.0"), gt=0)
    bridge_fee: Decimal = Field(default=Decimal("0.0"), ge=0)
    total_amount: Decimal = Field(default=Decimal("0.0"))  # Amount including fee
    exchange_rate: Decimal = Field(default=Decimal("1.0"))  # Exchange rate between tokens
    status: BridgeRequestStatus = Field(default=BridgeRequestStatus.PENDING, index=True)
    zk_proof: str | None = Field(default=None)  # Zero-knowledge proof
    merkle_proof: str | None = Field(default=None)  # Merkle proof for completion
    lock_tx_hash: str | None = Field(default=None, index=True)  # Lock transaction hash (source)
    unlock_tx_hash: str | None = Field(default=None, index=True)  # Unlock transaction hash (target)
    confirmations: int = Field(default=0)  # Number of confirmations received
    required_confirmations: int = Field(default=3)  # Required confirmations
    dispute_reason: str | None = Field(default=None)
    resolution_action: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confirmed_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    resolved_at: datetime | None = Field(default=None)
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(hours=24))

    # Runtime fields used by BridgeClientAdapter
    protocol: str | None = Field(default=None, max_length=20)  # BridgeProtocol used for this request
    secret_hash: str | None = Field(default=None, index=True)  # HTLC hashlock
    cancellation_reason: str | None = Field(default=None)
    error_message: str | None = Field(default=None)

    @field_validator("sender_address", "recipient_address", "source_token", "target_token")
    @classmethod
    def validate_address_field(cls, v: str) -> str:
        return validate_ethereum_address(v)

    @field_validator("amount")
    @classmethod
    def validate_amount_field(cls, v: Decimal) -> Decimal:
        return validate_positive_decimal(v)

    # Relationships
    # transactions: List["BridgeTransaction"] = Relationship(back_populates="bridge_request")
    # disputes: List["BridgeDispute"] = Relationship(back_populates="bridge_request")


class ChainConfig(SQLModel, table=True):
    """Configuration for supported blockchain networks"""

    __tablename__ = "chain_config"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: int = Field(index=True)
    chain_name: str = Field(index=True)
    chain_type: ChainType = Field(index=True)
    rpc_url: str = Field(default="")
    block_explorer_url: str = Field(default="")
    bridge_contract_address: str = Field(default="", max_length=42)
    native_token: str = Field(default="")
    native_token_symbol: str = Field(default="")
    block_time: int = Field(default=12)  # Average block time in seconds
    min_confirmations: int = Field(default=3)  # Minimum confirmations for finality
    avg_block_time: int = Field(default=12)  # Average block time
    finality_time: int = Field(default=300)  # Time to finality in seconds
    gas_token: str = Field(default="")
    max_gas_price: Decimal = Field(default=Decimal("0.0"))  # Maximum gas price
    is_active: bool = Field(default=True, index=True)
    is_testnet: bool = Field(default=False)
    requires_validator: bool = Field(default=True)  # Whether validator confirmation is required
    validator_threshold: Decimal = Field(default=Decimal("0.67"))  # Validator threshold percentage
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("rpc_url", "block_explorer_url")
    @classmethod
    def validate_url_field(cls, v: str) -> str:
        if not v:
            return v
        return validate_url(v) or v

    @field_validator("bridge_contract_address")
    @classmethod
    def validate_contract_address(cls, v: str) -> str:
        if not v:
            return v
        return validate_ethereum_address(v)


class Validator(SQLModel, table=True):
    """Bridge validator for cross-chain confirmations"""

    __tablename__ = "validator"

    id: int | None = Field(default=None, primary_key=True)
    validator_address: str = Field(index=True, max_length=42)
    validator_name: str = Field(default="")
    weight: int = Field(default=1)  # Validator weight
    commission_rate: Decimal = Field(default=Decimal("0.0"))  # Commission rate
    total_validations: int = Field(default=0)  # Total number of validations
    successful_validations: int = Field(default=0)  # Successful validations
    failed_validations: int = Field(default=0)  # Failed validations
    slashed_amount: Decimal = Field(default=Decimal("0.0"))  # Total amount slashed
    earned_fees: Decimal = Field(default=Decimal("0.0"))  # Total fees earned
    reputation_score: Decimal = Field(default=Decimal("100.0"))  # Reputation score (0-100)
    uptime_percentage: Decimal = Field(default=Decimal("100.0"))  # Uptime percentage
    last_validation: datetime | None = Field(default=None)
    last_seen: datetime | None = Field(default=None)
    status: ValidatorStatus = Field(default=ValidatorStatus.ACTIVE, index=True)
    is_active: bool = Field(default=True, index=True)
    supported_chains: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    val_meta_data: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("validator_address")
    @classmethod
    def validate_validator_address(cls, v: str) -> str:
        return validate_ethereum_address(v)

    # Relationships
    # transactions: List["BridgeTransaction"] = Relationship(back_populates="validator")


class MerkleProof(SQLModel, table=True):
    """Merkle proofs for bridge transaction verification"""

    __tablename__ = "merkle_proof"

    id: int | None = Field(default=None, primary_key=True)
    bridge_request_id: int = Field(foreign_key="bridge_request.id", index=True)
    proof_hash: str = Field(index=True)  # Merkle proof hash
    merkle_root: str = Field(index=True)  # Merkle root
    proof_data: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # Proof data
    leaf_index: int = Field(default=0)  # Leaf index in tree
    tree_depth: int = Field(default=0)  # Tree depth
    is_valid: bool = Field(default=False)
    verified_at: datetime | None = Field(default=None)
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(hours=24))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LiquidityPool(SQLModel, table=True):
    """Liquidity pools for bridge operations"""

    __tablename__ = "bridge_liquidity_pool"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: int = Field(index=True)
    token_address: str = Field(index=True)
    pool_address: str = Field(index=True)
    total_liquidity: float = Field(default=0.0)  # Total liquidity in pool
    available_liquidity: float = Field(default=0.0)  # Available liquidity
    utilized_liquidity: float = Field(default=0.0)  # Utilized liquidity
    utilization_rate: float = Field(default=0.0)  # Utilization rate
    interest_rate: float = Field(default=0.0)  # Interest rate
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "BridgeRequest",
    "BridgeRequestStatus",
    "ChainConfig",
    "ChainType",
    "LiquidityPool",
    "MerkleProof",
    "TransactionType",
    "Validator",
    "ValidatorStatus",
]
