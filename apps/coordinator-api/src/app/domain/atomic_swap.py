"""
Atomic Swap Domain Models

Domain models for managing trustless cross-chain atomic swaps between agents.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlmodel import Field, SQLModel


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
    initiator_agent_id: str = Field(index=True)
    initiator_address: str = Field()
    source_chain_id: int = Field(index=True)
    source_token: str = Field()  # "native" or ERC20 address
    source_amount: float = Field()

    # Participant details (Party B)
    participant_agent_id: str = Field(index=True)
    participant_address: str = Field()
    target_chain_id: int = Field(index=True)
    target_token: str = Field()  # "native" or ERC20 address
    target_amount: float = Field()

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

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
