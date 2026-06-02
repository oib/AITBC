from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from ..storage.schema import MARKETPLACE_BID_TABLE


class MarketplaceOffer(SQLModel, table=True):
    __tablename__ = "marketplaceoffer"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    provider: str = Field(index=True)
    capacity: int = Field(default=0, nullable=False)
    price: float = Field(default=0.0, nullable=False)
    sla: str = Field(default="")
    status: str = Field(default="open", max_length=20)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, index=True)
    attributes: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # GPU-specific fields
    gpu_model: str | None = Field(default=None, index=True)
    gpu_memory_gb: int | None = Field(default=None)
    gpu_count: int | None = Field(default=1)
    cuda_version: str | None = Field(default=None)
    price_per_hour: float | None = Field(default=None)
    region: str | None = Field(default=None, index=True)


class MarketplaceBid(SQLModel, table=True):
    __tablename__ = MARKETPLACE_BID_TABLE
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    provider: str = Field(index=True)
    capacity: int = Field(default=0, nullable=False)
    price: float = Field(default=0.0, nullable=False)
    notes: str | None = Field(default=None)
    status: str = Field(default="pending", nullable=False)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, index=True)
    
    # Auction-specific fields
    auction_type: str = Field(default="standard", index=True)  # standard, dutch, sealed, reverse
    sealed_bid_encrypted: str | None = Field(default=None)  # For sealed bids
    reveal_timestamp: datetime | None = Field(default=None)  # For sealed bid reveal
    dutch_price: float | None = Field(default=None)  # Current Dutch auction price
    auction_id: str | None = Field(default=None, index=True)  # Reference to auction


class AuctionConfig(SQLModel, table=True):
    """Auction configuration and metadata."""

    __tablename__ = "auction_config"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    auction_id: str = Field(index=True, unique=True)
    auction_type: str = Field(index=True)  # dutch, sealed, reverse
    resource_id: str = Field(index=True)
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = Field(default=None)
    reserve_price: float = Field(default=0.0)
    start_price: float | None = Field(default=None)  # For Dutch auctions
    decrement_rate: float | None = Field(default=None)  # For Dutch auctions
    decrement_interval: int | None = Field(default=None)  # For Dutch auctions (seconds)
    status: str = Field(default="active", index=True)  # active, completed, cancelled
    winner_id: str | None = Field(default=None)
    winning_price: float | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
