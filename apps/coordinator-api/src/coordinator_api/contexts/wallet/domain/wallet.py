"""
Multi-Chain Wallet Integration Domain Models

Domain models for managing agent wallets across multiple blockchain networks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import field_validator
from sqlalchemy import JSON, Column, Numeric
from sqlmodel import Field, SQLModel

from coordinator_api.validators import validate_ethereum_address, validate_url


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
    agent_id: str = Field(index=True, max_length=128)
    address: str = Field(index=True, max_length=42)
    public_key: str = Field()
    wallet_type: WalletType = Field(default=WalletType.EOA, index=True)
    is_active: bool = Field(default=True)
    encrypted_private_key: str | None = Field(default=None)  # Only if managed internally
    kms_key_id: str | None = Field(default=None)  # Reference to external KMS
    meta_data: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("address")
    @classmethod
    def validate_address_field(cls, v: str) -> str:
        return validate_ethereum_address(v)

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

    @field_validator("rpc_url", "ws_url", "explorer_url")
    @classmethod
    def validate_url_field(cls, v: str | None) -> str | None:
        return validate_url(v)


class TokenBalance(SQLModel, table=True):
    """Tracks token balances for agent wallets across networks"""

    __tablename__ = "token_balance"

    id: int | None = Field(default=None, primary_key=True)
    wallet_id: int = Field(foreign_key="agent_wallet.id", index=True)
    chain_id: int = Field(foreign_key="wallet_network_config.chain_id", index=True)
    token_address: str = Field(index=True, max_length=42)  # "native" for native currency
    token_symbol: str = Field()
    balance: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(20, 8)))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("token_address")
    @classmethod
    def validate_token_address(cls, v: str) -> str:
        if v.lower() == "native":
            return v
        return validate_ethereum_address(v)

    # Relationships
    # DISABLED:     wallet: AgentWallet = Relationship(back_populates="balances")


class TransactionStatus(StrEnum):
    PENDING = "pending"
    SIGNED = "signed"
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
    to_address: str = Field(index=True, max_length=42)
    value: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(20, 8)))
    data: str | None = Field(default=None)
    gas_limit: int | None = Field(default=None)
    gas_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(20, 8)))
    nonce: int | None = Field(default=None)
    status: TransactionStatus = Field(default=TransactionStatus.PENDING, index=True)
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("to_address")
    @classmethod
    def validate_to_address(cls, v: str) -> str:
        return validate_ethereum_address(v)

    # Relationships
    # DISABLED:     wallet: AgentWallet = Relationship(back_populates="transactions")


__all__ = [
    "AgentWallet",
    "NetworkConfig",
    "NetworkType",
    "TokenBalance",
    "TransactionStatus",
    "WalletTransaction",
    "WalletType",
]
