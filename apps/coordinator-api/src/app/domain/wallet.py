"""
Multi-Chain Wallet Integration Domain Models

Domain models for managing agent wallets across multiple blockchain networks.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel, Relationship

class WalletType(str, Enum):
    EOA = "eoa"                  # Externally Owned Account
    SMART_CONTRACT = "smart_contract"  # Smart Contract Wallet (e.g. Safe)
    MULTI_SIG = "multi_sig"      # Multi-Signature Wallet
    MPC = "mpc"                  # Multi-Party Computation Wallet

class NetworkType(str, Enum):
    EVM = "evm"
    SOLANA = "solana"
    APTOS = "aptos"
    SUI = "sui"

class AgentWallet(SQLModel, table=True):
    """Represents a wallet owned by an AI agent"""
    __tablename__ = "agent_wallet"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(index=True)
    address: str = Field(index=True)
    public_key: str = Field()
    wallet_type: WalletType = Field(default=WalletType.EOA, index=True)
    is_active: bool = Field(default=True)
    encrypted_private_key: Optional[str] = Field(default=None) # Only if managed internally
    kms_key_id: Optional[str] = Field(default=None) # Reference to external KMS
    metadata: Dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    balances: List["TokenBalance"] = Relationship(back_populates="wallet")
    transactions: List["WalletTransaction"] = Relationship(back_populates="wallet")

class NetworkConfig(SQLModel, table=True):
    """Configuration for supported blockchain networks"""
    __tablename__ = "wallet_network_config"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    chain_id: int = Field(index=True, unique=True)
    name: str = Field(index=True)
    network_type: NetworkType = Field(default=NetworkType.EVM)
    rpc_url: str = Field()
    ws_url: Optional[str] = Field(default=None)
    explorer_url: str = Field()
    native_currency_symbol: str = Field()
    native_currency_decimals: int = Field(default=18)
    is_testnet: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True)

class TokenBalance(SQLModel, table=True):
    """Tracks token balances for agent wallets across networks"""
    __tablename__ = "token_balance"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    wallet_id: int = Field(foreign_key="agent_wallet.id", index=True)
    chain_id: int = Field(foreign_key="wallet_network_config.chain_id", index=True)
    token_address: str = Field(index=True) # "native" for native currency
    token_symbol: str = Field()
    balance: float = Field(default=0.0)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    wallet: AgentWallet = Relationship(back_populates="balances")

class TransactionStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    DROPPED = "dropped"

class WalletTransaction(SQLModel, table=True):
    """Record of transactions executed by agent wallets"""
    __tablename__ = "wallet_transaction"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    wallet_id: int = Field(foreign_key="agent_wallet.id", index=True)
    chain_id: int = Field(foreign_key="wallet_network_config.chain_id", index=True)
    tx_hash: Optional[str] = Field(default=None, index=True)
    to_address: str = Field(index=True)
    value: float = Field(default=0.0)
    data: Optional[str] = Field(default=None)
    gas_limit: Optional[int] = Field(default=None)
    gas_price: Optional[float] = Field(default=None)
    nonce: Optional[int] = Field(default=None)
    status: TransactionStatus = Field(default=TransactionStatus.PENDING, index=True)
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    wallet: AgentWallet = Relationship(back_populates="transactions")
