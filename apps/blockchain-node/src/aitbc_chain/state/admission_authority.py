"""Sender-authority checks at mempool admission (register V-8).

``StateTransition.validate_transaction`` refuses a GOVERNANCE_EXECUTE from a sender outside the on-chain
``governance_executors`` list, and an ESCROW_RELEASE / ESCROW_REFUND from anyone but the
``escrow_settlement_authority``. It runs when a proposer applies a block, so the intake doors used to admit such a
transaction: it sat in the mempool until a proposer drained it, dropped it unsealed ("... is not an authorized
executor") and wrote nothing. This module asks the same question at admission, from the same chain parameters, with the
same version rules and the same messages, so a transaction that apply would refuse is refused at the door.

It mirrors the two sender gates in ``validate_transaction`` instead of being called by it: the apply path is consensus
code and stays untouched. ``tests/test_admission_authority.py`` runs both over a matrix of block versions, parameter
states and senders and fails if they ever disagree. BOND_SLASH is not covered here: its authority check lives in the
apply function, not in ``validate_transaction``.
"""

from __future__ import annotations

from sqlmodel import Session

from ..base_models import _to_ait_address
from .state_transition import _escrow_settlement_authority, _governance_executors

# The types whose sender ``validate_transaction`` checks against an on-chain authority.
AUTHORITY_GATED_TYPES = frozenset({"GOVERNANCE_EXECUTE", "ESCROW_RELEASE", "ESCROW_REFUND"})


def sender_authority_error(
    session: Session,
    chain_id: str,
    tx_type: str,
    sender: str,
    *,
    block_version: int,
    block_height: int | None = None,
) -> str | None:
    """Why ``sender`` may not send ``tx_type`` under the rules of ``block_version``, or None when it may.

    ``block_version`` and ``block_height`` are those of the block the transaction would land in: the authority
    parameters resolve to the value in force at ``block_height`` (None means the current value). Types that carry no
    sender authority return None.
    """
    sender_addr = _to_ait_address(sender or "")
    if tx_type == "GOVERNANCE_EXECUTE":
        executors = _governance_executors(session, chain_id, block_height)
        if executors is None:
            # Fails closed from v5; below it the lenient rule keeps sealed history replayable.
            if block_version >= 5:
                return "GOVERNANCE_EXECUTE rejected: governance_executors chain parameter is not set"
        elif sender_addr not in executors:
            return f"GOVERNANCE_EXECUTE sender {sender_addr} is not an authorized executor"
    elif tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND") and block_version >= 3:
        authority = _escrow_settlement_authority(session, chain_id, block_height)
        if authority is None:
            if block_version >= 5:
                return f"{tx_type} requires a settlement authority: set the escrow_settlement_authority chain parameter"
        elif sender_addr != authority:
            return f"{tx_type} must be signed by settlement authority {authority}, got {sender_addr}"
    return None
