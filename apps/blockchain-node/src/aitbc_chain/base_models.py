import re
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import field_validator
from sqlalchemy import BigInteger, Column, Index, UniqueConstraint
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
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    height: int = Field(index=True)
    hash: str = Field(index=True)
    parent_hash: str = Field(index=True)
    proposer: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    tx_count: int = 0
    state_root: str | None = None
    block_metadata: str | None = Field(default=None)

    # Block header signature (v0.7.1) — secp256k1 signature over the block
    # hash by the proposer. Empty for legacy blocks (pre-v0.7.1). Verified by
    # PoA consensus during block validation when bridge_block_signature_required
    # is True. Enables bridge proof verification to tie proofs to signed blocks.
    signature: str = ""

    # Relationships - use sa_relationship_kwargs for lazy loading
    transactions: list["Transaction"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "primaryjoin": "and_(aitbc_chain.base_models.Transaction.block_height==Block.height, aitbc_chain.base_models.Transaction.chain_id==Block.chain_id)",
            "foreign_keys": "[aitbc_chain.base_models.Transaction.block_height, aitbc_chain.base_models.Transaction.chain_id]",
        },
    )
    receipts: list["Receipt"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "primaryjoin": "and_(Receipt.block_height==Block.height, Receipt.chain_id==Block.chain_id)",
            "foreign_keys": "[Receipt.block_height, Receipt.chain_id]",
        },
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
    __table_args__ = (
        UniqueConstraint("chain_id", "tx_hash", name="uix_transaction_chain_hash"),
        Index("idx_tx_chain_height", "chain_id", "block_height"),
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    tx_hash: str = Field(index=True)
    block_height: int | None = Field(
        default=None,
        index=True,
    )
    sender: str = Field(index=True)
    recipient: str = Field(index=True)
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

    # New fields added to schema
    nonce: int = Field(default=0)
    value: int = Field(default=0)  # in compute-seconds (1 AIT = 3600)
    fee: int = Field(default=0)  # in compute-seconds (1 AIT = 3600)
    type: str = Field(default="TRANSFER", index=True)
    status: str = Field(default="pending")
    timestamp: str | None = Field(default=None)
    tx_metadata: str | None = Field(default=None)

    # Relationship
    block: Optional["Block"] = Relationship(
        back_populates="transactions",
        sa_relationship_kwargs={
            "primaryjoin": "and_(aitbc_chain.base_models.Transaction.block_height==Block.height, aitbc_chain.base_models.Transaction.chain_id==Block.chain_id)",
            "foreign_keys": "[aitbc_chain.base_models.Transaction.block_height, aitbc_chain.base_models.Transaction.chain_id]",
        },
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
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    miner_signature: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    coordinator_attestations: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    minted_amount: int | None = None  # in compute-seconds (1 AIT = 3600)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    status: str = Field(default="pending", index=True)  # pending, claimed, invalid
    claimed_at: datetime | None = None
    claimed_by: str | None = None

    # Relationship
    block: Optional["Block"] = Relationship(
        back_populates="receipts",
        sa_relationship_kwargs={
            "primaryjoin": "and_(Receipt.block_height==Block.height, Receipt.chain_id==Block.chain_id)",
            "foreign_keys": "[Receipt.block_height, Receipt.chain_id]",
        },
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
    balance: int = Field(default=0, sa_type=BigInteger)  # in compute-seconds (1 AIT = 3600)
    nonce: int = Field(default=0, sa_type=BigInteger)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Escrow(SQLModel, table=True):
    __tablename__ = "escrow"
    __table_args__ = {"extend_existing": True}
    job_id: str = Field(primary_key=True)
    buyer: str = Field(foreign_key="account.address")
    provider: str = Field(foreign_key="account.address")
    amount: int  # in compute-seconds (1 AIT = 3600)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    released_at: datetime | None = None
    job_tx_hash: str | None = None  # TX hash of software_job completion (proof of work)


class CrossChainTransfer(SQLModel, table=True):
    """Cross-chain bridge transfer record"""

    __tablename__ = "cross_chain_transfer"
    __table_args__ = {"extend_existing": True}

    transfer_id: str = Field(primary_key=True)
    source_chain: str = Field(index=True)
    target_chain: str = Field(index=True)
    sender: str = Field(index=True)
    recipient: str = Field(index=True)
    amount: int  # in compute-seconds (1 AIT = 3600)
    asset: str = Field(default="native")
    status: str = Field(default="pending", index=True)  # pending, locked, confirmed, completed, failed, refunded
    source_tx_hash: str | None = None
    target_tx_hash: str | None = None
    lock_time: datetime | None = None
    confirm_time: datetime | None = None


class BridgeValidator(SQLModel, table=True):
    """Bridge validator registration (v0.7.1).

    Persists validator set memberships per chain per epoch. Loaded into
    the in-memory ValidatorSetRegistry (aitbc.bridge.validators) for
    fast lookup during proof verification.
    """

    __tablename__ = "bridge_validators"
    __table_args__ = (
        Index("ix_bridge_validators_chain_epoch", "chain_id", "epoch"),
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)  # chain this validator serves
    address: str = Field(index=True)  # checksum address (0x...)
    public_key: str  # secp256k1 public key hex (0x...)
    epoch: int = Field(default=0, index=True)  # validator set epoch number
    is_active: bool = Field(default=True)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BridgeBlockHeader(SQLModel, table=True):
    """Block header from a remote (source) chain (v0.7.2 §B2).

    Stored by the bridge when it learns about source chain blocks (via
    RPC, gossip, or explicit submission). Used to anchor bridge proofs —
    the Merkle proof is verified against ``state_root``, and the block
    header's proposer ``signature`` is verified against the v0.7.1
    validator set.
    """

    __tablename__ = "bridge_block_header"
    __table_args__ = (
        UniqueConstraint("chain_id", "height", name="uix_bridge_block_chain_height"),
        Index("idx_bridge_block_chain_finality", "chain_id", "finality_confirmed"),
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)  # remote chain this header belongs to
    height: int = Field(index=True)
    hash: str = Field(index=True)
    parent_hash: str
    proposer: str  # proposer address
    state_root: str  # state root at this block — used for Merkle proof verification
    signature: str = ""  # proposer signature (v0.7.1 block header signature)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finality_confirmed: bool = False  # set when confirmation_count >= finality_blocks
    confirmation_count: int = 0  # number of confirmations seen (child blocks)


class Stake(SQLModel, table=True):
    """On-chain staking record"""

    __tablename__ = "stake"
    __table_args__ = {"extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    address: str = Field(index=True)
    amount: int  # in compute-seconds (1 AIT = 3600)
    locked_until: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = Field(default="active", index=True)  # active, withdrawn, slashed


class AgentIdentity(SQLModel, table=True):
    """On-chain agent identity record for verification"""

    __tablename__ = "agent_identity"
    __table_args__ = (
        UniqueConstraint("chain_id", "agent_id", name="uix_agent_identity_chain_agent"),
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    agent_address: str = Field(index=True)
    display_name: str | None = None
    agent_type: str = Field(default="general")  # general, provider, consumer
    capabilities: dict[str, Any] = Field(
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
    __table_args__ = (UniqueConstraint("chain_id", "proposal_id", name="uix_gov_proposal_chain_id"), {"extend_existing": True})

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    proposal_id: str = Field(index=True)
    proposer_address: str = Field(index=True)
    title: str
    description: str
    category: str = Field(default="general")
    status: str = Field(default="draft", index=True)  # draft, active, succeeded, defeated, executed, cancelled
    votes_for: int = Field(default=0)
    votes_against: int = Field(default=0)
    votes_abstain: int = Field(default=0)
    quorum_required: int = Field(default=0)
    passing_threshold: float = Field(default=0.5)
    execution_payload: dict[str, Any] = Field(
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
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    proposal_id: str = Field(index=True)
    voter_address: str = Field(index=True)
    vote_type: str = Field(default="for")  # for, against, abstain
    voting_power: int = Field(default=0)
    reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConsensusState(SQLModel, table=True):
    """Persisted multi-validator consensus state (v0.7.5 B11).

    Survives node restart so that validator set, PBFT view/sequence,
    and slashing history are not lost. One row per chain_id.
    """

    __tablename__ = "consensus_state"
    __table_args__ = ({"extend_existing": True},)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True, unique=True)
    current_view: int = Field(default=0)
    current_sequence: int = Field(default=0)
    current_epoch: int = Field(default=0)
    validator_set_json: str = Field(default="")  # JSON-serialized validator set
    slashing_events_json: str = Field(default="[]")  # JSON-serialized slashing history
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
