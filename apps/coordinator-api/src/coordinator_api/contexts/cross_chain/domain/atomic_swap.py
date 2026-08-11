"""
Atomic Swap Domain Models

Domain models for managing trustless cross-chain atomic swaps between agents.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from coordinator_api.validators import validate_agent_id, validate_ethereum_address


class SwapStatus(StrEnum):
    CREATED = "created"  # Order created but not initiated on-chain
    INITIATED = "initiated"  # Hashlock created and funds locked on source chain
    PARTICIPATING = "participating"  # Hashlock matched and funds locked on target chain
    COMPLETED = "completed"  # Secret revealed and funds claimed
    REFUNDED = "refunded"  # Timelock expired, funds returned
    FAILED = "failed"  # General error state


class AtomicSwapOrder(SQLModel, table=True):
    """Represents a cross-chain atomic swap order between two parties"""

    __tablename__ = "atomic_swap_order"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)

    # Initiator details (Party A)
    initiator_agent_id: str = Field(index=True, max_length=128)
    initiator_address: str = Field(max_length=42)
    source_chain_id: int = Field(index=True)
    source_token: str = Field(max_length=42)  # "native" or ERC20 address
    source_amount: Decimal = Field(gt=0, max_digits=20, decimal_places=8)

    # Participant details (Party B)
    participant_agent_id: str = Field(index=True, max_length=128)
    participant_address: str = Field(max_length=42)
    target_chain_id: int = Field(index=True)
    target_token: str = Field(max_length=42)  # "native" or ERC20 address
    target_amount: Decimal = Field(gt=0, max_digits=20, decimal_places=8)

    @field_validator("initiator_agent_id", "participant_agent_id")
    @classmethod
    def validate_agent_id_field(cls, v: str) -> str:
        return validate_agent_id(v)

    @field_validator("initiator_address", "participant_address", "source_token", "target_token")
    @classmethod
    def validate_address_field(cls, v: str) -> str:
        if v == "native":
            return v
        return validate_ethereum_address(v)

    # Cryptographic elements
    hashlock: str = Field(index=True)  # sha256 hash of the secret
    secret: str | None = Field(default=None)  # The secret (revealed upon completion)

    # Timelocks (Unix timestamps)
    source_timelock: int = Field()  # Party A's timelock (longer)
    target_timelock: int = Field()  # Party B's timelock (shorter)

    # Transaction tracking
    source_initiate_tx: str | None = Field(default=None)
    target_participate_tx: str | None = Field(default=None)
    target_complete_tx: str | None = Field(default=None)
    source_complete_tx: str | None = Field(default=None)
    refund_tx: str | None = Field(default=None)

    status: SwapStatus = Field(default=SwapStatus.CREATED, index=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["AtomicSwapOrder", "SwapStatus"]
