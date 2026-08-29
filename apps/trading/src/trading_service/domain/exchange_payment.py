"""Exchange payment persistence for the trading compatibility layer."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Numeric
from sqlmodel import Field

from .base import TradingBase


class ExchangePayment(TradingBase, table=True):
    """Ethereum payment request migrated from the coordinator exchange endpoints."""

    __tablename__ = "exchange_payment"
    __table_args__ = {"extend_existing": True}

    payment_id: str = Field(default_factory=lambda: f"ex_{uuid4().hex[:16]}", primary_key=True, max_length=32)
    user_id: str = Field(default="", max_length=255)
    aitbc_amount: Decimal = Field(default=Decimal("0"), sa_column=Numeric(20, 8))
    eth_amount: Decimal = Field(default=Decimal("0"), sa_column=Numeric(20, 8))
    payment_address: str = Field(default="", max_length=64)
    status: str = Field(default="pending", max_length=20)
    idempotency_key: str | None = Field(default=None, max_length=64, unique=True)
    created_at: int = Field(default_factory=lambda: int(datetime.now(UTC).timestamp()))
    expires_at: int = Field(default=0)
    confirmations: int = Field(default=0)
    tx_hash: str | None = Field(default=None, max_length=128)
    confirmed_at: int | None = Field(default=None)
