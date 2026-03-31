"""
Cross-Chain Bridge Domain Models

Domain models for cross-chain asset transfers, bridge requests, and validator management.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


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
    contract_request_id: str = Field(index=True)  # Contract request ID
    sender_address: str = Field(index=True)
    recipient_address: str = Field(index=True)
    source_token: str = Field(index=True)  # Source token address
    target_token: str = Field(index=True)  # Target token address
    source_chain_id: int = Field(index=True)
    target_chain_id: int = Field(index=True)
    amount: float = Field(default=0.0)
    bridge_fee: float = Field(default=0.0)
    total_amount: float = Field(default=0.0)  # Amount including fee
    exchange_rate: float = Field(default=1.0)  # Exchange rate between tokens
    status: BridgeRequestStatus = Field(default=BridgeRequestStatus.PENDING, index=True)
    zk_proof: str | None = Field(default=None)  # Zero-knowledge proof
    merkle_proof: str | None = Field(default=None)  # Merkle proof for completion
    lock_tx_hash: str | None = Field(default=None, index=True)  # Lock transaction hash
    unlock_tx_hash: str | None = Field(default=None, index=True)  # Unlock transaction hash
    confirmations: int = Field(default=0)  # Number of confirmations received
    required_confirmations: int = Field(default=3)  # Required confirmations
    dispute_reason: str | None = Field(default=None)
    resolution_action: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    resolved_at: datetime | None = Field(default=None)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))

    # Relationships
    # transactions: List["BridgeTransaction"] = Relationship(back_populates="bridge_request")
    # disputes: List["BridgeDispute"] = Relationship(back_populates="bridge_request")


class SupportedToken(SQLModel, table=True):
    """Supported tokens for cross-chain bridging"""

    __tablename__ = "supported_token"

    id: int | None = Field(default=None, primary_key=True)
    token_address: str = Field(index=True)
    token_symbol: str = Field(index=True)
    token_name: str = Field(default="")
    decimals: int = Field(default=18)
    bridge_limit: float = Field(default=1000000.0)  # Maximum bridge amount
    fee_percentage: float = Field(default=0.5)  # Bridge fee percentage
    min_amount: float = Field(default=0.01)  # Minimum bridge amount
    max_amount: float = Field(default=1000000.0)  # Maximum bridge amount
    requires_whitelist: bool = Field(default=False)
    is_active: bool = Field(default=True, index=True)
    is_wrapped: bool = Field(default=False)  # Whether it's a wrapped token
    original_token: str | None = Field(default=None)  # Original token address for wrapped tokens
    supported_chains: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    bridge_contracts: dict[int, str] = Field(default_factory=dict, sa_column=Column(JSON))  # Chain ID -> Contract address
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChainConfig(SQLModel, table=True):
    """Configuration for supported blockchain networks"""

    __tablename__ = "chain_config"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: int = Field(index=True)
    chain_name: str = Field(index=True)
    chain_type: ChainType = Field(index=True)
    rpc_url: str = Field(default="")
    block_explorer_url: str = Field(default="")
    bridge_contract_address: str = Field(default="")
    native_token: str = Field(default="")
    native_token_symbol: str = Field(default="")
    block_time: int = Field(default=12)  # Average block time in seconds
    min_confirmations: int = Field(default=3)  # Minimum confirmations for finality
    avg_block_time: int = Field(default=12)  # Average block time
    finality_time: int = Field(default=300)  # Time to finality in seconds
    gas_token: str = Field(default="")
    max_gas_price: float = Field(default=0.0)  # Maximum gas price
    is_active: bool = Field(default=True, index=True)
    is_testnet: bool = Field(default=False)
    requires_validator: bool = Field(default=True)  # Whether validator confirmation is required
    validator_threshold: float = Field(default=0.67)  # Validator threshold percentage
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Validator(SQLModel, table=True):
    """Bridge validator for cross-chain confirmations"""

    __tablename__ = "validator"

    id: int | None = Field(default=None, primary_key=True)
    validator_address: str = Field(index=True)
    validator_name: str = Field(default="")
    weight: int = Field(default=1)  # Validator weight
    commission_rate: float = Field(default=0.0)  # Commission rate
    total_validations: int = Field(default=0)  # Total number of validations
    successful_validations: int = Field(default=0)  # Successful validations
    failed_validations: int = Field(default=0)  # Failed validations
    slashed_amount: float = Field(default=0.0)  # Total amount slashed
    earned_fees: float = Field(default=0.0)  # Total fees earned
    reputation_score: float = Field(default=100.0)  # Reputation score (0-100)
    uptime_percentage: float = Field(default=100.0)  # Uptime percentage
    last_validation: datetime | None = Field(default=None)
    last_seen: datetime | None = Field(default=None)
    status: ValidatorStatus = Field(default=ValidatorStatus.ACTIVE, index=True)
    is_active: bool = Field(default=True, index=True)
    supported_chains: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    val_meta_data: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # transactions: List["BridgeTransaction"] = Relationship(back_populates="validator")


class BridgeTransaction(SQLModel, table=True):
    """Transactions related to bridge requests"""

    __tablename__ = "bridge_transaction"

    id: int | None = Field(default=None, primary_key=True)
    bridge_request_id: int = Field(foreign_key="bridge_request.id", index=True)
    validator_address: str | None = Field(default=None, index=True)
    transaction_type: TransactionType = Field(index=True)
    transaction_hash: str | None = Field(default=None, index=True)
    block_number: int | None = Field(default=None)
    block_hash: str | None = Field(default=None)
    gas_used: int | None = Field(default=None)
    gas_price: float | None = Field(default=None)
    transaction_cost: float | None = Field(default=None)
    signature: str | None = Field(default=None)  # Validator signature
    merkle_proof: list[str] | None = Field(default_factory=list, sa_column=Column(JSON))
    confirmations: int = Field(default=0)  # Number of confirmations
    is_successful: bool = Field(default=False)
    error_message: str | None = Field(default=None)
    retry_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    confirmed_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)

    # Relationships
    # bridge_request: BridgeRequest = Relationship(back_populates="transactions")
    # validator: Optional[Validator] = Relationship(back_populates="transactions")


class BridgeDispute(SQLModel, table=True):
    """Dispute records for failed bridge transfers"""

    __tablename__ = "bridge_dispute"

    id: int | None = Field(default=None, primary_key=True)
    bridge_request_id: int = Field(foreign_key="bridge_request.id", index=True)
    dispute_type: str = Field(index=True)  # TIMEOUT, INSUFFICIENT_FUNDS, VALIDATOR_MISBEHAVIOR, etc.
    dispute_reason: str = Field(default="")
    dispute_status: str = Field(default="open")  # open, investigating, resolved, rejected
    reporter_address: str = Field(index=True)
    evidence: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    resolution_action: str | None = Field(default=None)
    resolution_details: str | None = Field(default=None)
    refund_amount: float | None = Field(default=None)
    compensation_amount: float | None = Field(default=None)
    penalty_amount: float | None = Field(default=None)
    investigator_address: str | None = Field(default=None)
    investigation_notes: str | None = Field(default=None)
    is_resolved: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = Field(default=None)

    # Relationships
    # bridge_request: BridgeRequest = Relationship(back_populates="disputes")


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
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BridgeStatistics(SQLModel, table=True):
    """Statistics for bridge operations"""

    __tablename__ = "bridge_statistics"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: int = Field(index=True)
    token_address: str = Field(index=True)
    date: datetime = Field(index=True)
    total_volume: float = Field(default=0.0)  # Total volume for the day
    total_transactions: int = Field(default=0)  # Total number of transactions
    successful_transactions: int = Field(default=0)  # Successful transactions
    failed_transactions: int = Field(default=0)  # Failed transactions
    total_fees: float = Field(default=0.0)  # Total fees collected
    average_transaction_time: float = Field(default=0.0)  # Average time in minutes
    average_transaction_size: float = Field(default=0.0)  # Average transaction size
    unique_users: int = Field(default=0)  # Unique users for the day
    peak_hour_volume: float = Field(default=0.0)  # Peak hour volume
    peak_hour_transactions: int = Field(default=0)  # Peak hour transactions
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BridgeAlert(SQLModel, table=True):
    """Alerts for bridge operations and issues"""

    __tablename__ = "bridge_alert"

    id: int | None = Field(default=None, primary_key=True)
    alert_type: str = Field(index=True)  # HIGH_FAILURE_RATE, LOW_LIQUIDITY, VALIDATOR_OFFLINE, etc.
    severity: str = Field(index=True)  # LOW, MEDIUM, HIGH, CRITICAL
    chain_id: int | None = Field(default=None, index=True)
    token_address: str | None = Field(default=None, index=True)
    validator_address: str | None = Field(default=None, index=True)
    bridge_request_id: int | None = Field(default=None, index=True)
    title: str = Field(default="")
    message: str = Field(default="")
    val_meta_data: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    threshold_value: float = Field(default=0.0)  # Threshold that triggered alert
    current_value: float = Field(default=0.0)  # Current value
    is_acknowledged: bool = Field(default=False, index=True)
    acknowledged_by: str | None = Field(default=None)
    acknowledged_at: datetime | None = Field(default=None)
    is_resolved: bool = Field(default=False, index=True)
    resolved_at: datetime | None = Field(default=None)
    resolution_notes: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))


class BridgeConfiguration(SQLModel, table=True):
    """Configuration settings for bridge operations"""

    __tablename__ = "bridge_configuration"

    id: int | None = Field(default=None, primary_key=True)
    config_key: str = Field(index=True)
    config_value: str = Field(default="")
    config_type: str = Field(default="string")  # string, number, boolean, json
    description: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


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
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BridgeSnapshot(SQLModel, table=True):
    """Daily snapshot of bridge operations"""

    __tablename__ = "bridge_snapshot"

    id: int | None = Field(default=None, primary_key=True)
    snapshot_date: datetime = Field(index=True)
    total_volume_24h: float = Field(default=0.0)
    total_transactions_24h: int = Field(default=0)
    successful_transactions_24h: int = Field(default=0)
    failed_transactions_24h: int = Field(default=0)
    total_fees_24h: float = Field(default=0.0)
    average_transaction_time: float = Field(default=0.0)
    unique_users_24h: int = Field(default=0)
    active_validators: int = Field(default=0)
    total_liquidity: float = Field(default=0.0)
    bridge_utilization: float = Field(default=0.0)
    top_tokens: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    top_chains: dict[str, int] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ValidatorReward(SQLModel, table=True):
    """Rewards earned by validators"""

    __tablename__ = "validator_reward"

    id: int | None = Field(default=None, primary_key=True)
    validator_address: str = Field(index=True)
    bridge_request_id: int = Field(foreign_key="bridge_request.id", index=True)
    reward_amount: float = Field(default=0.0)
    reward_token: str = Field(index=True)
    reward_type: str = Field(index=True)  # VALIDATION_FEE, PERFORMANCE_BONUS, etc.
    reward_period: str = Field(index=True)  # Daily, weekly, monthly
    is_claimed: bool = Field(default=False, index=True)
    claimed_at: datetime | None = Field(default=None)
    claim_transaction_hash: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
