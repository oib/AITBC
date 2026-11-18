import re
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import field_validator
from sqlalchemy import BigInteger, Column, ForeignKeyConstraint, Index, Numeric, String, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, Relationship

from .base_models_aux import (
    AgentIdentity as AgentIdentity,
    AgentStakeMemo as AgentStakeMemo,
    AgentStakeRecord as AgentStakeRecord,
    Bond as Bond,
    BountyContract as BountyContract,
    BountySubmissionRecord as BountySubmissionRecord,
    BridgeBlockHeader as BridgeBlockHeader,
    BridgeValidator as BridgeValidator,
    ChainParameter as ChainParameter,
    ChainParameterHistory as ChainParameterHistory,
    ConsensusState as ConsensusState,
    CrossChainSwap as CrossChainSwap,
    CrossChainTransfer as CrossChainTransfer,
    GovernanceProposal as GovernanceProposal,
    GovernanceVote as GovernanceVote,
    Stake as Stake,
    ValidatorDeactivation as ValidatorDeactivation,
    record_chain_parameter_history as record_chain_parameter_history,
)
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
    # v14 (V-3, shared ACT-1 activation): the 13-table side-table root
    # fingerprint committed into the block hash. None on every pre-v14 block —
    # the hash preimage only gains the aux term when this is set.
    aux_state_root: str | None = None
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

    @field_validator("aux_state_root", mode="before")
    @classmethod
    def _aux_state_root_is_hex(cls, value: str | None) -> str | None:
        return _validate_optional_hex(value, "Block.aux_state_root")


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
    # Full signed transaction envelope as received (signature included) —
    # what fork-resolution requeue needs to push the tx back through real
    # mempool admission. Older rows may carry None; the requeue falls back
    # to a reconstructed payload for those.
    envelope: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
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


class BlockStateDelta(ChainBase, table=True):
    """One before-image row of the per-block undo journal.

    Written inside the same transaction that commits the block, so a block
    that committed always carries its undo information. ``op`` is one of
    ``ins`` (row did not exist pre-block — undo deletes it), ``upd`` (undo
    restores ``before_json`` columns; a NULL ``before_json`` means the row
    must not exist after undo — it was pending-insert when a raw
    ``UPDATE account`` ran), and ``del`` (undo re-inserts ``before_json``).
    ``state.block_deltas`` owns the semantics.
    """

    __tablename__ = "block_state_delta"
    __table_args__ = (Index("idx_block_state_delta_chain_height", "chain_id", "height"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    height: int = Field(index=True)
    table_name: str
    op: str
    pk_json: str = Field(sa_column=Column(Text, nullable=False))
    before_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))


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
        # contract_id is derived from (buyer, provider, job_id) and job_id is the primary
        # key, so uniqueness here is a guard on the derivation rather than a second key.
        # NULLs stay legal: a row from before #780 has none until its backfill ran.
        Index("uq_escrow_contract_id", "contract_id", unique=True),
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
    # A7: billed gross the release route consumed, recorded per release
    # submission as {"tx_hash": <leg hash>, "billed": <units>}. The settlement
    # passes prove each sealed release leg by recomputing the route's own fee
    # rule from this instead of inverting the sealed value — the only proof
    # that covers protected bumps and floor-rounded billings. NULL on legacy
    # rows means unproven.
    billed_legs: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    # E1: fixed-duration GPU rental energy floor snapshot, frozen at lock time.
    protected: bool = Field(default=False)
    energy_quote_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    energy_quote_id: str | None = None
    energy_quote_digest: str | None = None
    energy_settlement_route: str | None = None
    energy_settlement_asset: str | None = None
    energy_settlement_unit_scale: int | None = None
    energy_net_floor_units: int | None = None
    energy_provider_credit_units: int | None = None
    energy_fee_basis_points: int | None = None
    # #780 (b): the row is the contract. Until now the escrow's lifecycle lived in each RPC
    # worker's EscrowManager and this table held only the money facts, so two workers kept
    # two copies of the contract (and generated two contract_ids). These columns move the
    # rest into chain.db, where every worker reads the same answer. All are NULL on a row
    # written before the migration (see the escrow_contract_state revision) until its
    # backfill ran; readers derive the value from the older columns instead of trusting NULL.
    contract_id: str | None = None  # contracts.escrow.contract_id_for(buyer, provider, job_id)
    state: str | None = None  # contracts.escrow.EscrowState value
    expires_at: datetime | None = None
    fee_bps: int | None = None  # platform fee in basis points (avoids Decimal in the row)
    milestones: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    current_milestone: int = Field(default=0)
    dispute_reason: str | None = None
    dispute_evidence: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    resolution: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    buyer_agent_id: str | None = Field(default=None, index=True, max_length=128)
    provider_agent_id: str | None = Field(default=None, index=True, max_length=128)


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


class IPFSSubscription(ChainBase, table=True):
    """On-chain IPFS subscription for island members.

    Records a paid subscription that grants access to a private island IPFS
    swarm. The subscription is keyed by (chain_id, island_id, member_address).
    """

    __tablename__ = "ipfs_subscription"
    __table_args__ = (UniqueConstraint("chain_id", "island_id", "member_address", name="uix_ipfs_subscription"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    island_id: str = Field(index=True)
    member_address: str = Field(sa_column=Column(AccountAddress(), index=True))
    expires_at_block: int = Field(default=0)
    quota_bytes: int = Field(default=0)
    # Never incremented by any writer -- quota accounting for IPFS storage is
    # done off-chain by the market (see contexts/ipfs island access docs).
    used_bytes: int = Field(default=0)
    created_tx_hash: str | None = None
    updated_tx_hash: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AIJobCancellation(ChainBase, table=True):
    """Per-node service bookkeeping for an AI-job cancel.

    Deliberately NOT the sealed ``transaction`` row: a cancel used to rewrite
    ``tx.status``/``tx.payload`` on the serving host only, leaving the
    canonical copy of a sealed row divergent across the fleet
    (AI-CANCEL-SEALED-TX-1, #386). The mark lives here instead; read paths
    overlay ``status="cancelled"`` when a row for the job exists. The table
    is in no committed fingerprint set at any version, so per-node
    divergence is legitimate service state.
    """

    __tablename__ = "ai_job_cancellation"

    job_id: str = Field(primary_key=True)
    chain_id: str = Field(index=True)
    tx_hash: str = Field(index=True)
    cancelled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MinerRegistry(ChainBase, table=True):
    """Node-local bookkeeping for the ``aitbc mining`` RPC stub (#2211).

    The chain is PBFT/PoA — there is no proof-of-work mining, so these rows
    record only admin start/stop intent for ``/rpc/mining/*``; no hashrate,
    blocks, or rewards exist. The table lives in chain.db (shared by every
    RPC worker on the node) so all four endpoints agree, replacing the old
    per-process ``start_mining_route.miners`` function attribute and the
    unrelated coordinator-api ``/v1/miners`` AI-job registry the read paths
    used to prefer. It is in ``SERVICE_STATE_TABLES`` — per-node divergence
    is legitimate service state, never apply or aux-sync state.
    """

    __tablename__ = "miner_registry"

    chain_id: str = Field(primary_key=True)
    miner_address: str = Field(primary_key=True, max_length=128)
    threads: int = Field(default=1)
    enabled: bool = Field(default=True)
    authorized_by: str = Field(default="", max_length=128)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stopped_at: datetime | None = Field(default=None)


class AgentSpendSession(ChainBase, table=True):
    """On-chain agent spend session credential (AGENT-SPEND-B-1, #1142).

    Written only by apply at ``block_version >= 21`` via ``AGENT_SESSION_GRANT``
    (create) and ``AGENT_SESSION_REVOKE`` (set ``revoked_height``); every value
    is derived from the signed payload or the block height, so the table is a
    pure function of sealed history and sits in the v21 committed fingerprint
    set. There are no ``_at`` columns: expiry and revocation are heights, not
    wall-clock stamps.

    A sender is *session-bound* while at least one row for its address has
    ``revoked_height IS NULL`` — from then on every ``TRANSFER``/``ESCROW_LOCK``
    it signs must name a live ``payload.session_id`` and fit the daily cap. The
    agent can always unbind itself: ``AGENT_SESSION_REVOKE`` accepts the
    session's owner or the agent address as signer, so a squatter grant cannot
    lock the victim out.
    """

    __tablename__ = "agent_spend_session"
    __table_args__ = (
        Index("idx_agent_spend_session_agent", "chain_id", "agent_address"),
        {"extend_existing": True},
    )

    chain_id: str = Field(primary_key=True)
    session_id: str = Field(primary_key=True, max_length=128)
    agent_id: str = Field(default="", max_length=128)
    agent_address: str = Field(sa_column=Column(AccountAddress(), nullable=False))
    owner_address: str = Field(sa_column=Column(AccountAddress(), nullable=False))
    # Compute-units per day-bucket (block_height // 1290 ≈ 24 h at 67 s/block —
    # the same block-"day" the governance timelock uses).
    daily_cap: int = Field(default=0, sa_type=BigInteger)
    ops: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    expires_at_height: int | None = Field(default=None)
    revoked_height: int | None = Field(default=None)
    created_height: int = Field(default=0)


class AgentSpendLedger(ChainBase, table=True):
    """On-chain spent counter for one (session, day-bucket) pair.

    Written only by apply at ``block_version >= 21`` inside the same database
    transaction that debits the sender, so the daily cap is atomic with the
    spend. ``spent`` is in compute-units and counts the tx ``value`` only —
    the fee is protocol burn, not spend policy.
    """

    __tablename__ = "agent_spend_ledger"

    chain_id: str = Field(primary_key=True)
    session_id: str = Field(primary_key=True, max_length=128)
    day: int = Field(primary_key=True)
    spent: int = Field(default=0, sa_type=BigInteger)
    last_height: int = Field(default=0)
