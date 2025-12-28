"""
User domain models for AITBC
"""

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON
from datetime import datetime
from typing import Optional, List
from enum import Enum


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(SQLModel, table=True):
    """User model"""
    id: str = Field(primary_key=True)
    email: str = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True)
    status: UserStatus = Field(default=UserStatus.ACTIVE)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    
    # Relationships
    wallets: List["Wallet"] = Relationship(back_populates="user")
    transactions: List["Transaction"] = Relationship(back_populates="user")


class Wallet(SQLModel, table=True):
    """Wallet model for storing user balances"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    address: str = Field(unique=True, index=True)
    balance: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: User = Relationship(back_populates="wallets")
    transactions: List["Transaction"] = Relationship(back_populates="wallet")


class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    PURCHASE = "purchase"
    REWARD = "reward"
    REFUND = "refund"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Transaction(SQLModel, table=True):
    """Transaction model"""
    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    wallet_id: Optional[int] = Field(foreign_key="wallet.id")
    type: TransactionType
    status: TransactionStatus = Field(default=TransactionStatus.PENDING)
    amount: float
    fee: float = Field(default=0.0)
    description: Optional[str] = None
    tx_metadata: Optional[str] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_at: Optional[datetime] = None
    
    # Relationships
    user: User = Relationship(back_populates="transactions")
    wallet: Optional[Wallet] = Relationship(back_populates="transactions")


class UserSession(SQLModel, table=True):
    """User session model"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    token: str = Field(unique=True, index=True)
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: datetime = Field(default_factory=datetime.utcnow)
