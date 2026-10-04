"""Sender-authority checks at mempool admission (register V-8).

``StateTransition.validate_transaction`` refuses a GOVERNANCE_EXECUTE from a sender outside the on-chain
``governance_executors`` list, an ESCROW_RELEASE / ESCROW_REFUND from anyone but the
``escrow_settlement_authority``, and — from v11 — an ESCROW_FEE_SWEEP from anyone else or paying anyone but the
``escrow_fee_recipient``. It runs when a proposer applies a block, so the intake doors used to admit such a
transaction: it sat in the mempool until a proposer drained it, dropped it unsealed ("... is not an authorized
executor") and wrote nothing. This module asks the same question at admission, from the same chain parameters, with the
same version rules and the same messages, so a transaction that apply would refuse is refused at the door.

It mirrors the sender gates in ``validate_transaction`` instead of being called by it: the apply path is consensus
code and stays untouched. ``tests/test_admission_authority.py`` runs both over a matrix of block versions, parameter
states and senders and fails if they ever disagree. BOND_SLASH is not covered here: its authority check lives in the
apply function, not in ``validate_transaction``. The below-v11 refusal of ESCROW_FEE_SWEEP is *not* part of this
helper — below the gate the type has no consensus meaning, so ``validate_transaction`` treats it as a plain
transfer; the "not active yet" refusal lives in ``rpc/transactions.py`` next to the GPU_DEREGISTER one.
"""

from __future__ import annotations

from sqlmodel import Session

from ..base_models import _to_ait_address
from .state_transition import _escrow_fee_recipient, _escrow_settlement_authority, _governance_executors

# The types whose sender ``validate_transaction`` checks against an on-chain authority.
AUTHORITY_GATED_TYPES = frozenset({"GOVERNANCE_EXECUTE", "ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP"})


def sender_authority_error(
    session: Session,
    chain_id: str,
    tx_type: str,
    sender: str,
    *,
    block_version: int,
    block_height: int | None = None,
    recipient: str = "",
) -> str | None:
    """Why ``sender`` may not send ``tx_type`` under the rules of ``block_version``, or None when it may.

    ``block_version`` and ``block_height`` are those of the block the transaction would land in: the authority
    parameters resolve to the value in force at ``block_height`` (None means the current value). ``recipient`` is
    the transaction's ``to`` address — only ESCROW_FEE_SWEEP pins it (to the resolved fee recipient). Types that
    carry no sender authority return None.
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
    elif tx_type == "ESCROW_FEE_SWEEP" and block_version >= 11:
        # Same checks, same order, same messages as validate_transaction's
        # sweep branch — authority first, then the recipient pin. v11
        # postdates v5, so an unset authority always fails closed.
        authority = _escrow_settlement_authority(session, chain_id, block_height)
        if authority is None:
            return "ESCROW_FEE_SWEEP requires a settlement authority: set the escrow_settlement_authority chain parameter"
        if sender_addr != authority:
            return f"ESCROW_FEE_SWEEP must be signed by settlement authority {authority}, got {sender_addr}"
        fee_recipient = _escrow_fee_recipient(session, chain_id, block_height)
        if fee_recipient is None:
            return "ESCROW_FEE_SWEEP requires a fee recipient: set the escrow_fee_recipient chain parameter"
        if _to_ait_address(recipient or "") != fee_recipient:
            return f"ESCROW_FEE_SWEEP must pay {fee_recipient}, got {_to_ait_address(recipient or '')}"
    return None
