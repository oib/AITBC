"""Database schema for coin requests."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import declarative_base

Base: Any = declarative_base()


class CoinRequestStatus(StrEnum):
    """Status of a coin request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CoinRequest(Base):
    """Coin request model for database storage."""

    __tablename__ = "coin_requests"

    id = Column(String, primary_key=True)
    sender = Column(String, nullable=False, index=True)
    recipient = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    wallet_address = Column(String, nullable=False)
    status = Column(SQLEnum(CoinRequestStatus), default=CoinRequestStatus.PENDING, nullable=False, index=True)
    approval_mode = Column(String, nullable=False)
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    signed_transaction = Column(Text, nullable=True)
    transaction_hash = Column(String, nullable=True, index=True)
    audit_log = Column(Text, nullable=True)
