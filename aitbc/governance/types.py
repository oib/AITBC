"""Shared governance types for on-chain proposals, voting, and execution (v0.7.3 §A1).

These are the canonical shared SDK types for AITBC on-chain governance.
They define the transaction payload structures for GOVERNANCE_PROPOSE,
GOVERNANCE_VOTE, and GOVERNANCE_EXECUTE transactions, plus configuration
and parameter-change schema types.

The governance service (``apps/governance/``) and CLI consume these types
to build and validate on-chain governance transactions before submitting
them to the blockchain node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GovernanceTxType(StrEnum):
    """Governance transaction types for on-chain proposals/votes/execution.

    These are the values used in the ``type`` field of a blockchain
    transaction's ``content`` dict (see ``TransactionRequest.type`` in
    ``rpc/transactions.py:30``). The blockchain node's tx processing
    (``poa.py:348``) already handles arbitrary type strings — these
    types add governance-specific payload validation.
    """

    PROPOSE = "GOVERNANCE_PROPOSE"
    VOTE = "GOVERNANCE_VOTE"
    EXECUTE = "GOVERNANCE_EXECUTE"


class ProposalType(StrEnum):
    """Types of governance proposals."""

    PARAMETER_CHANGE = "parameter_change"
    FUND_ALLOCATION = "fund_allocation"
    VALIDATOR_CHANGE = "validator_change"
    EMERGENCY = "emergency"
    GENERAL = "general"


class VoteChoice(StrEnum):
    """Vote choices for governance proposals."""

    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"


@dataclass
class GovernanceConfig:
    """Configuration for governance operations.

    The governance service runs on port 8105 (``GOVERNANCE_BIND_PORT``
    env var, verified in ``main.py:408``). The blockchain node RPC runs
    on port 8202 (verified in ``aitbc/constants.py:50``).
    """

    rpc_url: str = "http://localhost:8105"  # governance service
    blockchain_rpc_url: str = "http://localhost:8202"  # blockchain node
    chain_id: str = "ait-hub"
    voting_period_blocks: int = 7200  # ~2 days at 2s block time
    quorum_percent: float = 30.0
    approval_percent: float = 50.0
    timelock_blocks: int = 86400  # 48h at 2s block time
    snapshot_delay_blocks: int = 100  # blocks before voting starts
    timeout: int = 30  # HTTP client timeout


@dataclass
class ProposalData:
    """Payload for a GOVERNANCE_PROPOSE transaction.

    This dataclass mirrors the fields stored in the governance service's
    ``Proposal`` SQLModel (``domain/governance.py:58``) but is
    dependency-free for use by the CLI and other services.
    """

    proposal_id: str
    proposer: str
    title: str
    description: str
    proposal_type: str = "general"  # ProposalType value
    parameters: dict[str, Any] = field(default_factory=dict)
    voting_starts_block: int = 0
    voting_ends_block: int = 0
    chain_id: str = "ait-hub"


@dataclass
class VoteData:
    """Payload for a GOVERNANCE_VOTE transaction.

    The ``voting_power`` field is the voter's on-chain AIT balance at the
    proposal's snapshot block — queried from the blockchain node via
    ``GET /rpc/account/{address}``.
    """

    proposal_id: str
    voter: str
    vote_type: str  # VoteChoice value: "for", "against", "abstain"
    voting_power: float = 0.0  # snapshot balance
    reason: str = ""
    chain_id: str = "ait-hub"


@dataclass
class ExecuteData:
    """Payload for a GOVERNANCE_EXECUTE transaction."""

    proposal_id: str
    executor: str
    chain_id: str = "ait-hub"


@dataclass
class ParameterChangeSchema:
    """Schema for a parameter change proposal.

    Describes what parameter to change, in which service, and the old→new
    values. This is stored in ``ProposalData.parameters`` for
    ``parameter_change`` type proposals.

    Parameter automation (actually applying the change to the target
    service) is deferred to v0.8.x — v0.7.3 only records the schema
    on-chain for transparency and auditability.
    """

    target_service: str  # "blockchain", "pool-hub", "marketplace"
    parameter_name: str
    old_value: Any
    new_value: Any
    description: str = ""
