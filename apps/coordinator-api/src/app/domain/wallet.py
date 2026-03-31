"""
Multi-Chain Wallet Integration Domain Models

Domain models for managing agent wallets across multiple blockchain networks.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class WalletType(StrEnum):
    EOA = "eoa"  # Externally Owned Account
    SMART_CONTRACT = "smart_contract"  # Smart Contract Wallet (e.g. Safe)
    MULTI_SIG = "multi_sig"  # Multi-Signature Wallet
    MPC = "mpc"  # Multi-Party Computation Wallet


class NetworkType(StrEnum):
    EVM = "evm"
    SOLANA = "solana"
    APTOS = "aptos"
    SUI = "sui"


class AgentWallet(SQLModel, table=True):
    """Represents a wallet owned by an AI agent"""

    __tablename__ = "agent_wallet"

    id: int | None = Field(default=None, primary_key=True)
    agent_id: str = Field(index=True)
    address: str = Field(index=True)
    public_key: str = Field()
    wallet_type: WalletType = Field(default=WalletType.EOA, index=True)
    is_active: bool = Field(default=True)
    encrypted_private_key: str | None = Field(default=None)  # Only if managed internally
    kms_key_id: str | None = Field(default=None)  # Reference to external KMS
    meta_data: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # DISABLED:     balances: List["TokenBalance"] = Relationship(back_populates="wallet")
    # DISABLED:     transactions: List["WalletTransaction"] = Relationship(back_populates="wallet")


class NetworkConfig(SQLModel, table=True):
    """Configuration for supported blockchain networks"""

    __tablename__ = "wallet_network_config"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: int = Field(index=True, unique=True)
    name: str = Field(index=True)
    network_type: NetworkType = Field(default=NetworkType.EVM)
    rpc_url: str = Field()
    ws_url: str | None = Field(default=None)
    explorer_url: str = Field()
    native_currency_symbol: str = Field()
    native_currency_decimals: int = Field(default=18)
    is_testnet: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True)


class TokenBalance(SQLModel, table=True):
    """Tracks token balances for agent wallets across networks"""

    __tablename__ = "token_balance"

    id: int | None = Field(default=None, primary_key=True)
    wallet_id: int = Field(foreign_key="agent_wallet.id", index=True)
    chain_id: int = Field(foreign_key="wallet_network_config.chain_id", index=True)
    token_address: str = Field(index=True)  # "native" for native currency
    token_symbol: str = Field()
    balance: float = Field(default=0.0)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # DISABLED:     wallet: AgentWallet = Relationship(back_populates="balances")


class TransactionStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    DROPPED = "dropped"


class WalletTransaction(SQLModel, table=True):
    """Record of transactions executed by agent wallets"""

    __tablename__ = "wallet_transaction"

    id: int | None = Field(default=None, primary_key=True)
    wallet_id: int = Field(foreign_key="agent_wallet.id", index=True)
    chain_id: int = Field(foreign_key="wallet_network_config.chain_id", index=True)
    tx_hash: str | None = Field(default=None, index=True)
    to_address: str = Field(index=True)
    value: float = Field(default=0.0)
    data: str | None = Field(default=None)
    gas_limit: int | None = Field(default=None)
    gas_price: float | None = Field(default=None)
    nonce: int | None = Field(default=None)
    status: TransactionStatus = Field(default=TransactionStatus.PENDING, index=True)
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # DISABLED:     wallet: AgentWallet = Relationship(back_populates="transactions")
