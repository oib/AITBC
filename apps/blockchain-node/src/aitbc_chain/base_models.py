import re
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import field_validator
from sqlalchemy import BigInteger, Column, ForeignKeyConstraint, Index, Numeric, String, TypeDecorator, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, Relationship

from .metadata import ChainBase

from aitbc.crypto.signature_recovery import canonical_address
from decimal import Decimal

_HEX_PATTERN = re.compile(r"^(0x)?[0-9a-fA-F]+$")


def _validate_hex(value: str, field_name: str) -> str:
    if not _HEX_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a hex-encoded string")
    return value.lower()


def _validate_optional_hex(value: str | None, field_name: str) -> str | None:
    if value is None:
        return value
    return _validate_hex(value, field_name)


def _to_evm_address(address: str) -> str:
    """Return the canonical EIP-55 `0x` spelling of a chain account address.

    Valid `0x...` addresses are returned as EIP-55 checksum strings. Anything
    that does not look like a 40-hex EVM address is passed through unchanged so
    callers that use short/alias values do not break.

    Delegates the parsing to :func:`canonical_address`, which answers the same
    question for signature verification. The two must agree on what counts as an
    address or the chain and the signature layer would disagree about who an
    account belongs to; they both now hand back EIP-55 `0x` (V23-66).
    """
    return canonical_address(address)


# Backward-compatible alias for callers that have not yet been updated.
_to_ait_address = _to_evm_address


def evm_address_spellings(address: str) -> list[str]:
    """Every spelling of ``address`` a verbatim column may be holding.

    With legacy prefixes removed, the only supported spellings are the EIP-55
    checksum and its lowercase form. Callers can compare against
    ``lower(column)`` if they do not know the checksum casing.
    """
    canonical = _to_evm_address(address)
    if canonical.startswith("0x") and len(canonical) == 42:
        return [canonical, canonical.lower()]
    return [canonical]


# Backward-compatible alias until call sites are updated.
address_spellings = evm_address_spellings


class EvmAddress(TypeDecorator):
    """Canonical EVM address column for chain account tables.

    Both inserts and lookups are normalised to EIP-55 `0x` 40-hex. This is the
    single normalisation point for on-chain account access; the trie layer
    (``StateManager._encode_address``) canonicalises to the same value.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if not isinstance(value, str):
            return value
        return _to_evm_address(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if not isinstance(value, str):
            return value
        return _to_evm_address(value)


# Backward-compatible alias for SQLModel columns that still reference AccountAddress.
AccountAddress = EvmAddress


class Block(ChainBase, table=True):
    __tablename__ = "block"
    __table_args__ = (
        UniqueConstraint("chain_id", "height", name="uix_block_chain_height"),
        UniqueConstraint("chain_id", "hash", name="uix_block_chain_hash"),
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
    bridge_state_root: str | None = None
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

    @field_validator("bridge_state_root", mode="before")
    @classmethod
    def _bridge_state_root_is_hex(cls, value: str | None) -> str | None:
        return _validate_optional_hex(value, "Block.bridge_state_root")


class Transaction(ChainBase, table=True):
    __tablename__ = "transaction"
    __table_args__ = (
        UniqueConstraint("chain_id", "tx_hash", name="uix_transaction_chain_hash"),
        Index("idx_tx_chain_height", "chain_id", "block_height"),
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    tx_hash: str = Field(index=True)
    block_height: int | None = Field(
        default=None,
        index=True,
    )
    # Plain columns, deliberately. These two are `from` and `to` in the message the
    # client signed, and `verify_transaction_signature` rebuilds that message out of
    # them — normalising either one changes the bytes and the signature stops
    # recovering. Lookups canonicalise the value they search for instead; see
    # `address_spellings` (V23-65).
    sender: str = Field(index=True)
    recipient: str = Field(index=True)
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

    # New fields added to schema
    nonce: int = Field(default=0)
    value: int = Field(default=0)  # in compute-units (1 AIT = 36_000_000)
    fee: int = Field(default=0)  # in compute-units (1 AIT = 36_000_000)
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


class Receipt(ChainBase, table=True):
    __tablename__ = "receipt"
    __table_args__ = (UniqueConstraint("chain_id", "receipt_id", name="uix_receipt_chain_id"),)

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
    minted_amount: int | None = None  # in compute-units (1 AIT = 36_000_000)
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


class Account(ChainBase, table=True):
    __tablename__ = "account"

    chain_id: str = Field(primary_key=True)
    address: str = Field(sa_column=Column(AccountAddress(), primary_key=True))
    balance: int = Field(default=0, sa_type=BigInteger)  # in compute-units (1 AIT = 36_000_000)
    nonce: int = Field(default=0, sa_type=BigInteger)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Escrow(ChainBase, table=True):
    __tablename__ = "escrow"
    # Chain-scoped, like block, transaction and receipt. `50fb6691025c` gave account the
    # composite `(chain_id, address)` primary key and did not bring escrow along, which
    # left the old references pointing at a column that is not unique on its own. SQLite
    # accepts that at CREATE time and then fails `PRAGMA foreign_key_check` for the entire
    # database -- "foreign key mismatch" -- so nothing in the chain database could be
    # integrity-checked. V23-64 wanted these constraints; this is the shape that resolves
    # (migration c9a4f1e2b73d).
    __table_args__ = (
        ForeignKeyConstraint(
            ["chain_id", "buyer"],
            ["account.chain_id", "account.address"],
            name="fk_escrow_buyer_account",
        ),
        ForeignKeyConstraint(
            ["chain_id", "provider"],
            ["account.chain_id", "account.address"],
            name="fk_escrow_provider_account",
        ),
    )

    job_id: str = Field(primary_key=True)
    chain_id: str = Field(index=True)
    # The constraints sit in `__table_args__` because they span two columns. Do not move
    # them back onto the fields as `foreign_key=`: that is SQLModel's `Field` argument, and
    # passing it to `Column` makes SQLAlchemy read it as a dialect option named
    # `foreign.key`, silently dropping the constraint (V23-64).
    buyer: str = Field(sa_column=Column(AccountAddress()))
    provider: str = Field(sa_column=Column(AccountAddress()))
    amount: int  # in compute-units (1 AIT = 36_000_000)
    status: str = Field(default="locked")  # locked, released, refunded
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    released_at: datetime | None = None
    refunded_at: datetime | None = None
    lock_tx_hash: str | None = None  # TX hash of the ESCROW_LOCK transaction
    job_tx_hash: str | None = None  # TX hash of software_job completion (proof of work)
    release_tx_hash: str | None = None  # TX hash of the ESCROW_RELEASE transaction
    refund_tx_hash: str | None = None  # TX hash of escrow refund
    # A metered release bills what the job used, not what was locked, so the two
    # settled legs are recorded rather than inferred from `amount`. NULL marks a row
    # written before partial releases existed, where a settlement moved the whole lock.
    released_amount: int | None = None  # compute-units paid to the provider, net of fee
    refunded_amount: int | None = None  # compute-units returned to the buyer unbilled


class CrossChainTransfer(ChainBase, table=True):
    """Cross-chain bridge transfer record"""

    __tablename__ = "cross_chain_transfer"

    transfer_id: str = Field(primary_key=True)
    source_chain: str = Field(index=True)
    target_chain: str = Field(index=True)
    sender: str = Field(index=True)
    recipient: str = Field(index=True)
    amount: int  # in compute-units (1 AIT = 36_000_000)
    asset: str = Field(default="native")
    status: str = Field(default="pending", index=True)  # pending, locked, confirmed, completed, failed, refunded
    source_tx_hash: str | None = None
    target_tx_hash: str | None = None
    lock_time: datetime | None = None
    confirm_time: datetime | None = None
    # v0.18.0: persisted proof hash for cross-restart replay protection.
    proof_hash: str | None = Field(default=None, index=True)


class BridgeValidator(ChainBase, table=True):
    """Bridge validator registration (v0.7.1).

    Persists validator set memberships per chain per epoch. Loaded into
    the in-memory ValidatorSetRegistry (aitbc.bridge.validators) for
    fast lookup during proof verification.
    """

    __tablename__ = "bridge_validators"
    __table_args__ = (Index("ix_bridge_validators_chain_epoch", "chain_id", "epoch"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)  # chain this validator serves
    address: str = Field(index=True)  # checksum address (0x...)
    public_key: str  # secp256k1 public key hex (0x...)
    epoch: int = Field(default=0, index=True)  # validator set epoch number
    is_active: bool = Field(default=True)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BridgeBlockHeader(ChainBase, table=True):
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
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)  # remote chain this header belongs to
    height: int = Field(index=True)
    hash: str = Field(index=True)
    parent_hash: str
    proposer: str  # proposer address
    state_root: str  # account state root at this block
    bridge_state_root: str = ""  # bridge event trie root at this block — used for Merkle proof verification
    signature: str = ""  # proposer signature (v0.7.1 block header signature)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finality_confirmed: bool = False  # set when confirmation_count >= finality_blocks
    confirmation_count: int = 0  # number of confirmations seen (child blocks)


class Stake(ChainBase, table=True):
    """On-chain staking record"""

    __tablename__ = "stake"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    address: str = Field(index=True)
    amount: int  # in compute-units (1 AIT = 36_000_000)
    locked_until: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = Field(default="active", index=True)  # active, withdrawn, slashed


class AgentStakeRecord(ChainBase, table=True):
    """Agent-economy stake (distinct from consensus Stake)."""

    __tablename__ = "agent_stake"
    __table_args__ = (UniqueConstraint("chain_id", "stake_id", name="uix_agent_stake_chain_id"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    stake_id: str = Field(index=True)
    staker_address: str = Field(index=True)
    agent_wallet: str = Field(index=True)
    amount: int  # compute-units
    lock_period: int = Field(default=30)
    locked_until: datetime
    status: str = Field(default="active", index=True)  # active, unbonding, completed
    unbonding_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentStakeMemo(ChainBase, table=True):
    """Signed memo for performance / distribute / claim (no extra debit)."""

    __tablename__ = "agent_stake_memo"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    kind: str = Field(index=True)
    external_id: str = Field(default="", index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BountyContract(ChainBase, table=True):
    """On-chain bounty lock. remaining_amount is what expire refunds."""

    __tablename__ = "bounty_contract"
    __table_args__ = (UniqueConstraint("chain_id", "bounty_id", name="uix_bounty_contract_chain_id"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    bounty_id: str = Field(index=True)
    creator_address: str = Field(index=True)
    reward_amount: int
    remaining_amount: int
    status: str = Field(default="active", index=True)  # active, completed, expired, disputed
    winner_address: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BountySubmissionRecord(ChainBase, table=True):
    """On-chain bounty submission memo."""

    __tablename__ = "bounty_submission"
    __table_args__ = (UniqueConstraint("chain_id", "submission_id", name="uix_bounty_submission_chain_id"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    bounty_id: str = Field(index=True)
    submission_id: str = Field(index=True)
    submitter_address: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Bond(ChainBase, table=True):
    """On-chain performance bond record."""

    __tablename__ = "bond"
    __table_args__ = (UniqueConstraint("chain_id", "bond_id", name="uix_bond_chain_bond_id"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    bond_id: str = Field(index=True)
    provider: str = Field(index=True)
    amount: int = Field(default=0)  # remaining locked amount in compute-units
    locked_until: datetime | None = None
    status: str = Field(default="active", index=True)  # active, released, slashed
    created_tx_hash: str | None = None
    released_tx_hash: str | None = None
    slashed_tx_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentIdentity(ChainBase, table=True):
    """On-chain agent identity record for verification"""

    __tablename__ = "agent_identity"
    __table_args__ = (UniqueConstraint("chain_id", "agent_id", name="uix_agent_identity_chain_agent"),)

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


class GovernanceProposal(ChainBase, table=True):
    """On-chain governance proposal record"""

    __tablename__ = "governance_proposal"
    __table_args__ = (UniqueConstraint("chain_id", "proposal_id", name="uix_gov_proposal_chain_id"),)

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
    execution_tx_hash: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GovernanceVote(ChainBase, table=True):
    """On-chain governance vote record"""

    __tablename__ = "governance_vote"
    __table_args__ = (UniqueConstraint("chain_id", "proposal_id", "voter_address", name="uix_gov_vote_unique"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    proposal_id: str = Field(index=True)
    voter_address: str = Field(index=True)
    vote_type: str = Field(default="for")  # for, against, abstain
    voting_power: int = Field(default=0)
    reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChainParameter(ChainBase, table=True):
    """On-chain parameter set by a governance proposal execution."""

    __tablename__ = "chain_parameter"
    __table_args__ = (UniqueConstraint("chain_id", "parameter", name="uix_chain_parameter"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    parameter: str = Field(index=True)
    value: str
    proposal_id: str | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConsensusState(ChainBase, table=True):
    """Persisted multi-validator consensus state (v0.7.5 B11).

    Survives node restart so that validator set, PBFT view/sequence,
    and slashing history are not lost. One row per chain_id.
    """

    __tablename__ = "consensus_state"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True, unique=True)
    current_view: int = Field(default=0)
    current_sequence: int = Field(default=0)
    current_epoch: int = Field(default=0)
    validator_set_json: str = Field(default="")  # JSON-serialized validator set
    slashing_events_json: str = Field(default="[]")  # JSON-serialized slashing history
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CrossChainEscrowRecord(ChainBase, table=True):
    """Cross-chain escrow record for atomic settlement (v0.9.0).

    Persists the HTLC escrow lifecycle: pending → locked → verified →
    executing → completed (or refunded/failed/disputed).
    """

    __tablename__ = "cross_chain_escrows"
    __table_args__ = (
        UniqueConstraint("escrow_id", name="uix_escrow_id"),
        Index("ix_escrow_trade_id", "trade_id"),
        Index("ix_escrow_status", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    escrow_id: str = Field(index=True)
    trade_id: str = Field(index=True)
    source_chain: str = Field(index=True)
    dest_chain: str
    sender: str
    recipient: str
    amount: int
    asset: str = "native"
    status: str = "pending"  # EscrowStatus value
    secret_hash: str = ""
    secret: str = ""
    source_timelock: int = 0
    dest_timelock: int = 0
    source_lock_tx_hash: str = ""
    dest_execution_tx_hash: str = ""
    source_release_tx_hash: str = ""
    dest_release_tx_hash: str = ""
    timeout_seconds: int = 3600
    timeout_extended: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    locked_at: datetime | None = None
    settled_at: datetime | None = None
    refunded_at: datetime | None = None


class EscrowProofRecord(ChainBase, table=True):
    """Proof record in the settlement proof chain (v0.9.0).

    Each escrow has up to 5 proofs: lock → verification → execution →
    release → settlement. Proofs are chained via previous_proof_hash.
    """

    __tablename__ = "escrow_proofs"
    __table_args__ = (
        Index("ix_proof_escrow_id", "escrow_id"),
        Index("ix_proof_type", "proof_type"),
    )

    id: int | None = Field(default=None, primary_key=True)
    escrow_id: str = Field(index=True)
    proof_type: str  # ProofType value
    chain_id: str
    block_height: int
    block_hash: str
    tx_hash: str
    proposer_signature: str = ""
    validator_signatures_json: str = "[]"
    merkle_proof_json: str = "[]"
    previous_proof_hash: str = ""
    timestamp: float = 0.0


class HTLCSwapState(ChainBase, table=True):
    """Persistent HTLC swap state (v0.9.0 B4).

    Mirrors the Solidity ``mapping(bytes32 => Swap)`` storage. Each row
    represents a single atomic swap with its lock state and fund movement
    status.
    """

    __tablename__ = "htlc_swaps"
    __table_args__ = (
        Index("ix_htlc_initiator", "initiator"),
        Index("ix_htlc_participant", "participant"),
        Index("ix_htlc_status", "status"),
    )

    swap_id: str = Field(primary_key=True)
    initiator: str = Field(index=True)
    participant: str = Field(index=True)
    token: str = "native"
    amount: int = 0
    hashlock: str = ""
    timelock: int = 0
    status: str = Field(default="open", index=True)  # open, completed, refunded
    secret: str = ""
    created_at: float = 0.0
    completed_at: float | None = None
    refunded_at: float | None = None


class SmartContract(ChainBase, table=True):
    """Deployed smart contract registry entry.

    Stores contract metadata and deployed bytecode/ABI. The contract address
    is deterministically derived from the deployer address, contract name, and
    deployment nonce.
    """

    __tablename__ = "smart_contract"
    __table_args__ = (UniqueConstraint("chain_id", "address", name="uix_smart_contract_chain_address"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    address: str = Field(index=True)
    name: str = Field(index=True)
    contract_type: str = Field(default="general")  # zk-verifier, escrow, governance, general
    deployer: str = Field(index=True)
    bytecode: str = Field(default="")  # hex-encoded contract bytecode
    abi: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    state: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    status: str = Field(default="deployed", index=True)  # deployed, destroyed
    deployed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LiquidityPool(ChainBase, table=True):
    """On-chain AIT-only liquidity pool."""

    __tablename__ = "liquidity_pool"
    __table_args__ = ()

    pool_id: str = Field(primary_key=True)
    chain_id: str = Field(primary_key=True)
    token: str = Field(default="AIT")
    total_staked: int = Field(default=0, sa_column=Column(BigInteger, default=0))
    reward_per_share: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(28, 18), default=0))
    last_distribution_at: datetime | None = None
    status: str = Field(default="active", index=True)  # active, paused
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LiquidityStake(ChainBase, table=True):
    """A single liquidity provider position in a pool."""

    __tablename__ = "liquidity_stake"
    __table_args__ = ()

    stake_id: str = Field(primary_key=True)
    chain_id: str = Field(primary_key=True)
    pool_id: str = Field(index=True)
    address: str = Field(sa_column=Column(EvmAddress, nullable=False, index=True))
    amount: int = Field(sa_column=Column(BigInteger, default=0))
    lock_days: int = Field(default=0)
    locked_until: datetime | None = None
    reward_per_share_at_stake: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(28, 18), default=0))
    rewards_claimed: int = Field(default=0, sa_column=Column(BigInteger, default=0))
    status: str = Field(default="active", index=True)  # active, withdrawn
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LiquidityDistribution(ChainBase, table=True):
    """Record of a reward or fee distribution into a pool."""

    __tablename__ = "liquidity_distribution"
    __table_args__ = ()

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    pool_id: str = Field(index=True)
    amount: int = Field(sa_column=Column(BigInteger, default=0))
    source: str = Field(default="")  # escrow_fee, gas_fee, bridge_fee, emission
    reward_per_share_before: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(28, 18), default=0))
    reward_per_share_after: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(28, 18), default=0))
    total_staked: int = Field(default=0, sa_column=Column(BigInteger, default=0))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
