import re
from datetime import UTC, datetime
from typing import Optional

from pydantic import field_validator
from sqlalchemy import BigInteger, Column, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, Relationship, SQLModel

_HEX_PATTERN = re.compile(r"^(0x)?[0-9a-fA-F]+$")


def _validate_hex(value: str, field_name: str) -> str:
    if not _HEX_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a hex-encoded string")
    return value.lower()


def _validate_optional_hex(value: str | None, field_name: str) -> str | None:
    if value is None:
        return value
    return _validate_hex(value, field_name)


class Block(SQLModel, table=True):
    __tablename__ = "block"
    __table_args__ = (
        UniqueConstraint("chain_id", "height", name="uix_block_chain_height"),
        UniqueConstraint("chain_id", "hash", name="uix_block_chain_hash"),
        {"extend_existing": True}
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    height: int = Field(index=True)
    hash: str = Field(index=True)
    parent_hash: str
    proposer: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    tx_count: int = 0
    state_root: str | None = None
    block_metadata: str | None = Field(default=None)

    # Relationships - use sa_relationship_kwargs for lazy loading
    transactions: list["Transaction"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "primaryjoin": "and_(aitbc_chain.base_models.Transaction.block_height==Block.height, aitbc_chain.base_models.Transaction.chain_id==Block.chain_id)",
            "foreign_keys": "[aitbc_chain.base_models.Transaction.block_height, aitbc_chain.base_models.Transaction.chain_id]"
        }
    )
    receipts: list["Receipt"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "primaryjoin": "and_(Receipt.block_height==Block.height, Receipt.chain_id==Block.chain_id)",
            "foreign_keys": "[Receipt.block_height, Receipt.chain_id]"
        }
    )

    @field_validator("hash", mode="before")
    @classmethod
    def _hash_is_hex(cls, value: str) -> str:
        return _validate_hex(value, "Block.hash")

    @field_validator("parent_hash", mode="before")
    @classmethod
    def _parent_hash_is_hex(cls, value: str) -> str:
        return _validate_hex(value, "Block.parent_hash")

    @field_validator("state_root", mode="before")
    @classmethod
    def _state_root_is_hex(cls, value: str | None) -> str | None:
        return _validate_optional_hex(value, "Block.state_root")


class Transaction(SQLModel, table=True):
    __tablename__ = "transaction"
    __table_args__ = (UniqueConstraint("chain_id", "tx_hash", name="uix_transaction_chain_hash"), {"extend_existing": True})

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    tx_hash: str = Field(index=True)
    block_height: int | None = Field(
        default=None,
        index=True,
    )
    sender: str
    recipient: str
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

    # New fields added to schema
    nonce: int = Field(default=0)
    value: int = Field(default=0)
    fee: int = Field(default=0)
    type: str = Field(default="TRANSFER", index=True)
    status: str = Field(default="pending")
    timestamp: str | None = Field(default=None)
    tx_metadata: str | None = Field(default=None)

    # Relationship
    block: Optional["Block"] = Relationship(
        back_populates="transactions",
        sa_relationship_kwargs={
            "primaryjoin": "and_(aitbc_chain.base_models.Transaction.block_height==Block.height, aitbc_chain.base_models.Transaction.chain_id==Block.chain_id)",
            "foreign_keys": "[aitbc_chain.base_models.Transaction.block_height, aitbc_chain.base_models.Transaction.chain_id]"
        }
    )

    @field_validator("tx_hash", mode="before")
    @classmethod
    def _tx_hash_is_hex(cls, value: str) -> str:
        return _validate_hex(value, "Transaction.tx_hash")


class Receipt(SQLModel, table=True):
    __tablename__ = "receipt"
    __table_args__ = (UniqueConstraint("chain_id", "receipt_id", name="uix_receipt_chain_id"), {"extend_existing": True})

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    job_id: str = Field(index=True)
    receipt_id: str = Field(index=True)
    block_height: int | None = Field(
        default=None,
        index=True,
    )
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    miner_signature: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    coordinator_attestations: list = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    minted_amount: int | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    status: str = Field(default="pending", index=True)  # pending, claimed, invalid
    claimed_at: datetime | None = None
    claimed_by: str | None = None

    # Relationship
    block: Optional["Block"] = Relationship(
        back_populates="receipts",
        sa_relationship_kwargs={
            "primaryjoin": "and_(Receipt.block_height==Block.height, Receipt.chain_id==Block.chain_id)",
            "foreign_keys": "[Receipt.block_height, Receipt.chain_id]"
        }
    )

    @field_validator("receipt_id", mode="before")
    @classmethod
    def _receipt_id_is_hex(cls, value: str) -> str:
        return _validate_hex(value, "Receipt.receipt_id")


class Account(SQLModel, table=True):
    __tablename__ = "account"
    __table_args__ = {"extend_existing": True}

    chain_id: str = Field(primary_key=True)
    address: str = Field(primary_key=True)
    balance: int = Field(default=0, sa_type=BigInteger)
    nonce: int = Field(default=0, sa_type=BigInteger)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class Escrow(SQLModel, table=True):
    __tablename__ = "escrow"
    __table_args__ = {"extend_existing": True}
    job_id: str = Field(primary_key=True)
    buyer: str = Field(foreign_key="account.address")
    provider: str = Field(foreign_key="account.address")
    amount: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    released_at: datetime | None = None


class CrossChainTransfer(SQLModel, table=True):
    """Cross-chain bridge transfer record"""
    __tablename__ = "cross_chain_transfer"
    __table_args__ = {"extend_existing": True}

    transfer_id: str = Field(primary_key=True)
    source_chain: str = Field(index=True)
    target_chain: str = Field(index=True)
    sender: str = Field(index=True)
    recipient: str = Field(index=True)
    amount: int
    asset: str = Field(default="native")
    status: str = Field(default="pending")  # pending, locked, confirmed, completed, failed, refunded
    source_tx_hash: str | None = None
    target_tx_hash: str | None = None
    lock_time: datetime | None = None
    confirm_time: datetime | None = None


class Stake(SQLModel, table=True):
    """On-chain staking record"""
    __tablename__ = "stake"
    __table_args__ = {"extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    address: str = Field(index=True)
    amount: int
    locked_until: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = Field(default="active")  # active, withdrawn, slashed


class AgentIdentity(SQLModel, table=True):
    """On-chain agent identity record for verification"""
    __tablename__ = "agent_identity"
    __table_args__ = (
        UniqueConstraint("chain_id", "agent_id", name="uix_agent_identity_chain_agent"),
        {"extend_existing": True}
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    agent_address: str = Field(index=True)
    display_name: str | None = None
    agent_type: str = Field(default="general")  # general, provider, consumer
    capabilities: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    status: str = Field(default="active")  # active, suspended, revoked
    is_verified: bool = Field(default=False)
    verified_at: datetime | None = None
    verified_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GovernanceProposal(SQLModel, table=True):
    """On-chain governance proposal record"""
    __tablename__ = "governance_proposal"
    __table_args__ = (
        UniqueConstraint("chain_id", "proposal_id", name="uix_gov_proposal_chain_id"),
        {"extend_existing": True}
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    proposal_id: str = Field(index=True)
    proposer_address: str = Field(index=True)
    title: str
    description: str
    category: str = Field(default="general")
    status: str = Field(default="draft")  # draft, active, succeeded, defeated, executed, cancelled
    votes_for: int = Field(default=0)
    votes_against: int = Field(default=0)
    votes_abstain: int = Field(default=0)
    quorum_required: int = Field(default=0)
    passing_threshold: float = Field(default=0.5)
    execution_payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    voting_starts: datetime
    voting_ends: datetime
    executed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GovernanceVote(SQLModel, table=True):
    """On-chain governance vote record"""
    __tablename__ = "governance_vote"
    __table_args__ = (
        UniqueConstraint("chain_id", "proposal_id", "voter_address", name="uix_gov_vote_unique"),
        {"extend_existing": True}
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    proposal_id: str = Field(index=True)
    voter_address: str = Field(index=True)
    vote_type: str = Field(default="for")  # for, against, abstain
    voting_power: int = Field(default=0)
    reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
