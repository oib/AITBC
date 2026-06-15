"""
Multi-Chain Transaction Domain Models

Domain models for multi-chain transaction management.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class TransactionPriority(StrEnum):
    """Transaction priority levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class TransactionType(StrEnum):
    """Transaction types"""

    TRANSFER = "transfer"
    SWAP = "swap"
    BRIDGE = "bridge"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    CONTRACT_CALL = "contract_call"
    APPROVAL = "approval"


class TransactionStatus(StrEnum):
    """Enhanced transaction status"""

    QUEUED = "queued"
    PENDING = "pending"
    PROCESSING = "processing"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RETRYING = "retrying"


class RoutingStrategy(StrEnum):
    """Transaction routing strategies"""

    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    BALANCED = "balanced"
    RELIABLE = "reliable"
    PRIORITY = "priority"


class MultiChainTransaction(SQLModel, table=True):
    """Multi-chain transaction record"""

    __tablename__ = "multi_chain_transaction"

    id: str = Field(default=None, primary_key=True)  # Transaction ID
    user_id: str = Field(index=True)
    chain_id: int = Field(index=True)
    transaction_type: TransactionType = Field(index=True)
    from_address: str = Field(index=True)
    to_address: str = Field(index=True)
    amount: float = Field(default=0.0)
    token_address: str | None = Field(default=None, index=True)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    priority: TransactionPriority = Field(default=TransactionPriority.MEDIUM, index=True)
    routing_strategy: RoutingStrategy = Field(default=RoutingStrategy.BALANCED)
    gas_limit: int | None = Field(default=None)
    gas_price: int | None = Field(default=None)
    max_fee_per_gas: int | None = Field(default=None)
    status: TransactionStatus = Field(default=TransactionStatus.QUEUED, index=True)
    deadline: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=30), index=True)
    meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    retry_count: int = Field(default=0)
    submit_attempts: int = Field(default=0)
    gas_used: int | None = Field(default=None)
    gas_price_paid: int | None = Field(default=None)
    transaction_hash: str | None = Field(default=None, index=True)
    block_number: int | None = Field(default=None)
    confirmations: int = Field(default=0)
    error_message: str | None = Field(default=None)
    processing_time: float | None = Field(default=None)  # Processing time in seconds
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cancelled_at: datetime | None = Field(default=None)
    cancellation_reason: str | None = Field(default=None)
