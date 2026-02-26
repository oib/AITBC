"""
User domain models for AITBC
"""

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON
from datetime import datetime
from typing import Optional, List


class User(SQLModel, table=True):
    """User model"""
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(primary_key=True)
    email: str = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True)
    status: str = Field(default="active", max_length=20)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    
    # Relationships
    wallets: List["Wallet"] = Relationship(back_populates="user")
    transactions: List["Transaction"] = Relationship(back_populates="user")


class Wallet(SQLModel, table=True):
    """Wallet model for storing user balances"""
    __tablename__ = "wallets"
    __table_args__ = {"extend_existing": True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id")
    address: str = Field(unique=True, index=True)
    balance: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: User = Relationship(back_populates="wallets")
    transactions: List["Transaction"] = Relationship(back_populates="wallet")


class Transaction(SQLModel, table=True):
    """Transaction model"""
    __tablename__ = "transactions"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id")
    wallet_id: Optional[int] = Field(foreign_key="wallets.id")
    type: str = Field(max_length=20)
    status: str = Field(default="pending", max_length=20)
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
    __tablename__ = "user_sessions"
    __table_args__ = {"extend_existing": True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id")
    token: str = Field(unique=True, index=True)
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: datetime = Field(default_factory=datetime.utcnow)
