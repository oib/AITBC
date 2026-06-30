"""On-chain governance transaction payload builders + validation (v0.7.3 §A3).

These utilities build the ``content`` dict for GOVERNANCE_PROPOSE,
GOVERNANCE_VOTE, and GOVERNANCE_EXECUTE transactions. The blockchain
node's tx processing (``consensus/poa.py:348``) already stores arbitrary
``type`` strings from ``tx.content`` — these builders produce payloads
that conform to the governance schema, and ``validate_governance_payload``
is used by the blockchain node (Agent B B7) to reject malformed
governance transactions at the consensus layer.

The payload structure mirrors the dataclasses in ``types.py``:
- GOVERNANCE_PROPOSE: ProposalData fields + tx_type
- GOVERNANCE_VOTE: VoteData fields + tx_type
- GOVERNANCE_EXECUTE: ExecuteData fields + tx_type
"""

from __future__ import annotations

from typing import Any

from .types import (
    GovernanceTxType,
    ParameterChangeSchema,
    ProposalData,
    ProposalType,
    VoteChoice,
    VoteData,
)

# Required fields per governance tx type (used by validate_governance_payload)
_REQUIRED_FIELDS: dict[str, list[str]] = {
    GovernanceTxType.PROPOSE: ["proposal_id", "proposer", "title", "description", "proposal_type"],
    GovernanceTxType.VOTE: ["proposal_id", "voter", "vote_type"],
    GovernanceTxType.EXECUTE: ["proposal_id", "executor"],
}

_VALID_PROPOSAL_TYPES = {p.value for p in ProposalType}
_VALID_VOTE_CHOICES = {v.value for v in VoteChoice}


def build_proposal_tx(data: ProposalData) -> dict[str, Any]:
    """Build a GOVERNANCE_PROPOSE transaction payload.

    The returned dict is the ``content`` field of a TransactionRequest
    (see ``rpc/transactions.py:21``). The blockchain node stores this
    verbatim and validates it via ``validate_governance_payload`` (B7).
    """
    return {
        "type": GovernanceTxType.PROPOSE.value,
        "proposal_id": data.proposal_id,
        "proposer": data.proposer,
        "title": data.title,
        "description": data.description,
        "proposal_type": data.proposal_type,
        "parameters": data.parameters,
        "voting_starts_block": data.voting_starts_block,
        "voting_ends_block": data.voting_ends_block,
        "chain_id": data.chain_id,
    }


def build_vote_tx(data: VoteData) -> dict[str, Any]:
    """Build a GOVERNANCE_VOTE transaction payload."""
    return {
        "type": GovernanceTxType.VOTE.value,
        "proposal_id": data.proposal_id,
        "voter": data.voter,
        "vote_type": data.vote_type,
        "voting_power": data.voting_power,
        "reason": data.reason,
        "chain_id": data.chain_id,
    }


def build_execute_tx(proposal_id: str, executor: str, chain_id: str = "ait-hub") -> dict[str, Any]:
    """Build a GOVERNANCE_EXECUTE transaction payload."""
    return {
        "type": GovernanceTxType.EXECUTE.value,
        "proposal_id": proposal_id,
        "executor": executor,
        "chain_id": chain_id,
    }


def build_parameter_change_params(schema: ParameterChangeSchema) -> dict[str, Any]:
    """Build the ``parameters`` dict for a parameter_change proposal.

    This is stored in ``ProposalData.parameters`` and records the
    old→new value transition for auditability. Actual parameter
    application is performed by ``build_parameter_apply_tx`` (v0.7.4)
    which creates a GOVERNANCE_EXECUTE payload that target services
    consume to apply the change.
    """
    return {
        "target_service": schema.target_service,
        "parameter_name": schema.parameter_name,
        "old_value": schema.old_value,
        "new_value": schema.new_value,
        "description": schema.description,
    }


# Known target services and their configurable parameters (v0.7.4 §A4).
# Used by validate_parameter_change to reject unknown service/parameter
# combinations at the SDK layer before tx submission.
_KNOWN_TARGET_SERVICES: dict[str, set[str]] = {
    "blockchain": {
        "block_reward",
        "max_block_size",
        "block_interval_seconds",
        "max_transactions_per_block",
        "bridge_fee_basis_points",
    },
    "pool-hub": {
        "reward_distribution_enabled",
        "reward_sync_interval_blocks",
        "default_chain_id",
        "agent_coordinator_url",
    },
    "marketplace": {
        "default_chain_id",
        "agent_coordinator_url",
        "matching_algorithm",
    },
    "governance": {
        "voting_period_blocks",
        "quorum_percent",
        "approval_percent",
        "timelock_blocks",
        "emergency_quorum_percent",
        "emergency_timelock_blocks",
    },
}


def validate_parameter_change(
    schema: ParameterChangeSchema,
    target_service_config: dict[str, Any] | None = None,
) -> list[str]:
    """Validate a parameter change before applying it.

    Returns a list of error strings. An empty list means the change is valid.

    Checks:
    1. target_service is a known service
    2. parameter_name is a known parameter for that service
    3. old_value matches the current config value (if config provided)
    4. new_value is not the same as old_value (no-op check)
    """
    errors: list[str] = []

    # Check target_service is known
    known_params = _KNOWN_TARGET_SERVICES.get(schema.target_service)
    if known_params is None:
        errors.append(f"unknown target_service: {schema.target_service} (must be one of {sorted(_KNOWN_TARGET_SERVICES)})")
        return errors

    # Check parameter_name is known for this service
    if schema.parameter_name not in known_params:
        errors.append(
            f"unknown parameter_name: {schema.parameter_name} "
            f"for service {schema.target_service} "
            f"(must be one of {sorted(known_params)})"
        )

    # No-op check: new_value should differ from old_value
    if schema.new_value == schema.old_value:
        errors.append(f"no-op change: new_value ({schema.new_value}) equals old_value ({schema.old_value})")

    # If current config is provided, verify old_value matches
    if target_service_config is not None:
        current = target_service_config.get(schema.parameter_name)
        if current is not None and current != schema.old_value:
            errors.append(
                f"old_value mismatch: expected {schema.old_value} but current config "
                f"has {current} for {schema.target_service}.{schema.parameter_name}"
            )

    return errors


def build_parameter_apply_tx(
    schema: ParameterChangeSchema,
    proposal_id: str,
    executor: str,
    chain_id: str = "ait-hub",
) -> dict[str, Any]:
    """Build a GOVERNANCE_EXECUTE transaction payload that applies a parameter change.

    This is the execution payload for a parameter_change proposal that has
    passed voting and the timelock. Target services (pool-hub, marketplace,
    blockchain-node) consume this payload via their governance-triggered
    parameter API endpoints (Agent B B3/B4) to apply the change.

    The payload includes the full ParameterChangeSchema so the target service
    can validate the old→new transition before applying.
    """
    return {
        "type": GovernanceTxType.EXECUTE.value,
        "proposal_id": proposal_id,
        "executor": executor,
        "chain_id": chain_id,
        "parameter_change": {
            "target_service": schema.target_service,
            "parameter_name": schema.parameter_name,
            "old_value": schema.old_value,
            "new_value": schema.new_value,
            "description": schema.description,
        },
    }


def validate_governance_payload(
    tx_type: GovernanceTxType,
    payload: dict[str, Any],
) -> list[str]:
    """Validate a governance transaction payload.

    Returns a list of error strings. An empty list means the payload
    is valid. Used by the blockchain node (B7) to reject malformed
    governance transactions at the consensus layer before they are
    included in a block.
    """
    errors: list[str] = []

    # Check tx_type matches the payload's declared type (if present)
    declared_type = payload.get("type")
    if declared_type is not None and declared_type != tx_type.value:
        errors.append(f"type mismatch: expected {tx_type.value}, got {declared_type}")

    # Check required fields
    required = _REQUIRED_FIELDS.get(tx_type.value, [])
    for field_name in required:
        value = payload.get(field_name)
        if value is None:
            errors.append(f"missing required field: {field_name}")
        elif isinstance(value, str) and not value.strip():
            errors.append(f"empty required field: {field_name}")

    # Type-specific validation
    if tx_type == GovernanceTxType.PROPOSE:
        proposal_type = payload.get("proposal_type")
        if proposal_type is not None and proposal_type not in _VALID_PROPOSAL_TYPES:
            errors.append(f"invalid proposal_type: {proposal_type} (must be one of {sorted(_VALID_PROPOSAL_TYPES)})")
        voting_starts = payload.get("voting_starts_block")
        voting_ends = payload.get("voting_ends_block")
        if isinstance(voting_starts, int) and isinstance(voting_ends, int) and voting_ends <= voting_starts:
            errors.append("voting_ends_block must be greater than voting_starts_block")

    elif tx_type == GovernanceTxType.VOTE:
        vote_type = payload.get("vote_type")
        if vote_type is not None and vote_type not in _VALID_VOTE_CHOICES:
            errors.append(f"invalid vote_type: {vote_type} (must be one of {sorted(_VALID_VOTE_CHOICES)})")
        voting_power = payload.get("voting_power")
        if voting_power is not None and not isinstance(voting_power, int | float):
            errors.append(f"voting_power must be numeric, got {type(voting_power).__name__}")
        if isinstance(voting_power, int | float) and voting_power < 0:
            errors.append("voting_power must be non-negative")

    return errors


# ---------------------------------------------------------------------------
# Cross-chain governance utilities (v0.7.4 §A3)
# ---------------------------------------------------------------------------

# Governance tx subtypes for cross-chain operations. These are stored in
# the ``parameters`` dict of a GOVERNANCE_PROPOSE or GOVERNANCE_EXECUTE tx
# and are consumed by the bridge layer to propagate proposals / aggregate
# votes across islands.
_CROSS_CHAIN_OP_PROPOSAL_PROPAGATION = "proposal_propagation"
_CROSS_CHAIN_OP_VOTE_AGGREGATION = "vote_aggregation"
_CROSS_CHAIN_OP_CROSS_CHAIN_EXECUTE = "cross_chain_execute"


def build_proposal_propagation_tx(
    proposal_data: ProposalData,
    target_chain: str,
    executor: str = "",
) -> dict[str, Any]:
    """Build a GOVERNANCE_EXECUTE tx that propagates a proposal to a target chain.

    The proposal is replicated on the target chain via a bridge
    transaction. The target chain's governance service receives the
    proposal data and creates a local copy with the same proposal_id,
    allowing votes to be cast on both chains.

    Args:
        proposal_data: The original proposal to propagate.
        target_chain: The destination chain ID (island).
        executor: The address submitting the propagation tx.

    Returns:
        A GOVERNANCE_EXECUTE payload with ``cross_chain_op`` and
        ``proposal`` fields that the bridge layer consumes.
    """
    return {
        "type": GovernanceTxType.EXECUTE.value,
        "proposal_id": proposal_data.proposal_id,
        "executor": executor,
        "chain_id": target_chain,
        "cross_chain_op": _CROSS_CHAIN_OP_PROPOSAL_PROPAGATION,
        "target_chain": target_chain,
        "proposal": {
            "proposal_id": proposal_data.proposal_id,
            "proposer": proposal_data.proposer,
            "title": proposal_data.title,
            "description": proposal_data.description,
            "proposal_type": proposal_data.proposal_type,
            "parameters": proposal_data.parameters,
            "voting_starts_block": proposal_data.voting_starts_block,
            "voting_ends_block": proposal_data.voting_ends_block,
            "source_chain": proposal_data.chain_id,
        },
    }


def build_vote_aggregation_tx(
    votes: list[VoteData],
    source_chain: str,
    proposal_id: str = "",
    executor: str = "",
) -> dict[str, Any]:
    """Build a GOVERNANCE_EXECUTE tx that aggregates votes from a source chain.

    Votes cast on a remote chain are bridged back to the hub chain for
    aggregation. The governance service on the hub chain merges these
    votes with locally-cast votes to compute the final tally.

    Args:
        votes: List of votes from the source chain.
        source_chain: The chain where the votes were cast.
        proposal_id: The proposal being voted on (inferred from votes if empty).
        executor: The address submitting the aggregation tx.

    Returns:
        A GOVERNANCE_EXECUTE payload with ``cross_chain_op`` and ``votes``
        fields.
    """
    pid = proposal_id or (votes[0].proposal_id if votes else "")
    return {
        "type": GovernanceTxType.EXECUTE.value,
        "proposal_id": pid,
        "executor": executor,
        "chain_id": "ait-hub",  # aggregation always targets the hub
        "cross_chain_op": _CROSS_CHAIN_OP_VOTE_AGGREGATION,
        "source_chain": source_chain,
        "votes": [
            {
                "proposal_id": v.proposal_id,
                "voter": v.voter,
                "vote_type": v.vote_type,
                "voting_power": v.voting_power,
                "reason": v.reason,
                "source_chain": v.chain_id,
            }
            for v in votes
        ],
    }


def build_cross_chain_execute_tx(
    proposal_id: str,
    target_chains: list[str],
    executor: str = "",
) -> dict[str, Any]:
    """Build a GOVERNANCE_EXECUTE tx that executes a proposal on all chains.

    After a proposal passes voting and the timelock on the hub chain,
    this tx triggers execution on all target chains. Each target chain's
    governance service applies the proposal's parameter changes (if any)
    via its local parameter-apply endpoint.

    Args:
        proposal_id: The approved proposal to execute.
        target_chains: List of chain IDs to execute on.
        executor: The address submitting the execution tx.

    Returns:
        A GOVERNANCE_EXECUTE payload with ``cross_chain_op`` and
        ``target_chains`` fields.
    """
    return {
        "type": GovernanceTxType.EXECUTE.value,
        "proposal_id": proposal_id,
        "executor": executor,
        "chain_id": "ait-hub",
        "cross_chain_op": _CROSS_CHAIN_OP_CROSS_CHAIN_EXECUTE,
        "target_chains": list(target_chains),
    }
