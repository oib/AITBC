"""Auxiliary chain-record tables split from ``aitbc_chain.base_models`` (#1860 pure-move split).

``aitbc_chain.base_models`` re-exports every name defined here, so
``from aitbc_chain.base_models import X`` keeps working unchanged.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Index, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, select

from .metadata import ChainBase


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
    # GAP-47: optional release amount (compute-units) credited on the target
    # chain. ``None`` means "release the locked amount" — the bridge default.
    # Cross-chain swaps set this to the quoted/converted amount so a swap
    # cannot silently deliver bridge semantics at a different rate.
    release_amount: int | None = None


class CrossChainSwap(ChainBase, table=True):
    """Cross-chain swap record (GAP-47).

    A swap is a bridge transfer with a rate quote: ``amount`` is locked on
    the source chain and the underlying ``CrossChainTransfer`` settles it on
    the target chain. The row stores the quote metadata; the lifecycle state
    is derived live from the linked transfer so a swap can never claim a
    status the bridge did not reach.
    """

    __tablename__ = "cross_chain_swap"

    swap_id: str = Field(primary_key=True)
    transfer_id: str = Field(index=True)
    chain_id: str = Field(index=True)  # source chain this swap was locked on
    from_chain: str
    to_chain: str
    from_token: str
    to_token: str
    amount: str  # human-readable source amount (AIT decimal string)
    amount_units: int  # locked amount in compute-units
    expected_amount: str | None = None  # quoted target amount (AIT decimal string)
    min_amount: str | None = None
    rate: float = 1.0
    total_fees: str = "0"
    slippage_tolerance: float = 0.01
    user_address: str = Field(index=True)
    recipient: str
    status: str = Field(default="pending", index=True)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


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
    # Block height at which expire_bounty may run. None = no deadline:
    # expiry is allowed at any time, exactly as before the field existed.
    deadline_height: int | None = None
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
    # Height of the block whose GOVERNANCE_EXECUTE last set this parameter.
    # NULL on rows written before height tracking (or outside the apply path —
    # e.g. operator-seeded dormant chains): resolvers treat NULL as
    # "set at an unknown height" and apply the value at every height, the
    # pre-tracking status quo.
    applied_height: int | None = Field(default=None)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChainParameterHistory(ChainBase, table=True):
    """Every chain-parameter change with the block height it took effect at.

    Lets resolvers answer "the value in force at height H" instead of the
    current value: a node replaying history must see the parameter as it was
    when each block was sealed, or a parameter set mid-history wrongly
    governs — or wrongly rejects — earlier blocks (the GOVERNANCE_EXECUTE
    sender gate applies at every version once the parameter is set). Written
    wherever `chain_parameter` is written: apply-time parameter_change,
    genesis seeding, and sync upserts that carry a height.
    """

    __tablename__ = "chain_parameter_history"
    __table_args__ = (UniqueConstraint("chain_id", "parameter", "applied_height", name="uix_chain_parameter_history"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    parameter: str = Field(index=True)
    value: str
    proposal_id: str | None = Field(default=None, index=True)
    applied_height: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def record_chain_parameter_history(
    session,
    chain_id: str,
    parameter: str,
    value: str,
    proposal_id: str | None,
    applied_height: int,
    overwrite: bool = False,
) -> None:
    """Append a ``chain_parameter_history`` row unless this (param, height) is recorded.

    Called from every ``chain_parameter`` write path (apply-time
    parameter_change, genesis seeding, height backfill, sync upserts) so the
    value-in-force-at-height answer stays complete however the row arrived.

    ``overwrite`` makes the write last-write-wins: two GOVERNANCE_EXECUTEs in
    the same block changing one parameter must leave the second value — the
    one ``chain_parameter`` ends with — recorded for every later height.
    Callers replaying or applying sealed history (apply path, init rebuild)
    pass it; seeding/upsert paths keep first-write-wins.
    """
    # Sessions run autoflush=False — flush pending rows first or a second
    # call for the same (param, height) misses the unflushed row and
    # double-inserts, violating the unique constraint.
    session.flush()
    exists = session.exec(
        select(ChainParameterHistory).where(
            ChainParameterHistory.chain_id == chain_id,
            ChainParameterHistory.parameter == parameter,
            ChainParameterHistory.applied_height == applied_height,
        )
    ).first()
    if exists is None:
        session.add(
            ChainParameterHistory(
                chain_id=chain_id,
                parameter=parameter,
                value=value,
                proposal_id=proposal_id,
                applied_height=applied_height,
            )
        )
    elif overwrite and (exists.value != value or exists.proposal_id != proposal_id):
        exists.value = value
        exists.proposal_id = proposal_id
        session.add(exists)


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
    # #1940 F3-B: JSON object mapping str(sequence) -> committed block_hash —
    # this node's cross-view PBFT commit locks. "{}" on rows that predate it.
    pbft_commit_locks_json: str = Field(default="{}")
    # #2005 F3-C: JSON object mapping str(sequence) -> VIEW_CHANGE protocol
    # record {"floor","prepared","commit_lock","proposals"} — the durable
    # per-height state the floor rule, commit-lock reports and proposal-body
    # availability (Option R) depend on across restarts. "{}" on rows that
    # predate it; auto-added by _migrate_existing_columns like the locks.
    pbft_view_change_json: str = Field(default="{}")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidatorDeactivation(ChainBase, table=True):
    """On-chain validator deactivation marker (#1198).

    Written by a ``VALIDATOR_DEACTIVATE`` transaction at block apply, so the
    slash-driven half of the proposer active set becomes a pure function of
    canonical chain state instead of node-local ``ConsensusState`` mutation.
    One row per (chain_id, validator_address): the first deactivation wins;
    a reorg that un-seals the carrying block removes the row and the
    validator deterministically re-enters the active set on every node.
    """

    __tablename__ = "validator_deactivation"
    __table_args__ = (UniqueConstraint("chain_id", "validator_address", name="uix_validator_deactivation_chain_addr"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    validator_address: str = Field(index=True)  # canonical_address(strict=True) EIP-55 form
    evidence_hash: str = Field(default="")  # sha256 over the canonical evidence bundle (audit-only in v1)
    deactivation_tx_hash: str = Field(default="", index=True)
    block_height: int | None = Field(default=None, index=True)  # height of the carrying block; NULL for non-consensus applies
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
