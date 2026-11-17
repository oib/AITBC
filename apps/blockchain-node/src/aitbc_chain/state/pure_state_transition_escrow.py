"""ESCROW_* state-delta computation for the pure state-transition split.

Release/refund/fee-sweep delta builders plus the v23 obligation-bound and
settlement-authority gates. Import ``aitbc_chain.state.pure_state_transition``
first (it re-exports every name here); this module is not meant to be
imported directly.
"""

from __future__ import annotations

from typing import Any

from ..models import Account
from .pure_state_transition_base import (
    StateDelta,
    _decode_payload,
    _escrow_address,
    _escrow_fee_recipient,
    _escrow_settlement_authority,
)


def _escrow_v3_release_refund_delta(
    account_map: dict[str, Account],
    sender: str,
    recipient: str,
    value: int,
    fee: int,
    tx_type: str,
    tx_hash: str,
    job_id: str,
    context: dict[str, Any],
) -> StateDelta:
    """Compute a v3 ESCROW_RELEASE/ESCROW_REFUND delta (value comes from escrow)."""
    escrow_addr = context.get("escrow_addr") or _escrow_address(job_id)
    escrow_account = account_map.get(escrow_addr)
    escrow_balance = escrow_account.balance if escrow_account else 0
    if escrow_balance < value:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"Escrow {job_id} has insufficient balance: {escrow_balance} < {value}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    sender_account = account_map.get(sender)
    if not sender_account or sender_account.balance < fee:
        bal = sender_account.balance if sender_account else 0
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"Insufficient balance for fee: {bal} < {fee}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    return StateDelta(
        sender=sender,
        recipient=recipient,
        sender_balance_change=-fee,
        recipient_balance_change=value,
        sender_nonce_change=1,
        success=True,
        tx_type=tx_type,
        tx_hash=tx_hash,
        extra_debits={escrow_addr: -value},
    )


def _escrow_v2_release_refund_delta(
    account_map: dict[str, Account],
    sender: str,
    recipient: str,
    value: int,
    fee: int,
    tx_type: str,
    tx_hash: str,
) -> StateDelta:
    """Compute a v2 (lock_version < 3) ESCROW_RELEASE/ESCROW_REFUND delta."""
    total_cost = value + fee
    sender_account = account_map.get(sender)
    if not sender_account or sender_account.balance < total_cost:
        bal = sender_account.balance if sender_account else 0
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"Insufficient balance for {sender}: {bal} < {total_cost}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    return StateDelta(
        sender=sender,
        recipient=recipient,
        sender_balance_change=-total_cost,
        recipient_balance_change=value,
        sender_nonce_change=1,
        success=True,
        tx_type=tx_type,
        tx_hash=tx_hash,
    )


# v23 governed fee allowance (#1261). A normally settled escrow ends
# lock L -> release ~97.5% L -> sweep ~2.5% L, and the chain records no fee split, so
# the fee slice stays "remaining obligation" forever. The allowance lets the
# settlement authority sweep up to ``escrow_fee_cap_bps`` of the locked amount
# out of that slice. Consensus value, deliberately not an env setting: nodes
# must agree, so an on-chain ``escrow_fee_cap_bps`` chain parameter overrides
# this default.
DEFAULT_ESCROW_FEE_CAP_BPS = 300
MAX_ESCROW_FEE_CAP_BPS = 10_000


def escrow_sweep_ceiling(custody: int, remaining: int, fee_allowance: int) -> int:
    """Most an ESCROW_FEE_SWEEP may take from ``custody`` at v23.

    Residue (custody beyond the remaining obligation) is always sweepable;
    on top of that the governed fee allowance may eat into the obligation.
    ``fee_allowance`` is 0 until the job has settled and shrinks by what was
    already swept (see ``_escrow_obligation_state``).
    """
    return custody - max(0, remaining - fee_allowance)


def _escrow_v23_release_obligation_error(
    context: dict[str, Any], job_id: str, value: int, tx_type: str, tx_hash: str
) -> str | None:
    """v23 obligation bound for ESCROW_RELEASE/ESCROW_REFUND (pure path).

    Mirrors ``validate_transaction``: the context must carry the prefetch
    obligation state; a missing entry fails closed because the pure path
    cannot query the DB.
    """
    if "remaining_obligation" not in context or context.get("obligation_unbounded"):
        return f"{tx_type} for {job_id} cannot verify escrow obligation — missing or unbounded context"
    remaining_obligation = context["remaining_obligation"]
    if remaining_obligation is not None and value > remaining_obligation:
        return f"{tx_type} for {job_id} exceeds remaining obligation {remaining_obligation}"
    return None


def _escrow_v23_sweep_obligation_error(
    account_map: dict[str, Account], context: dict[str, Any], job_id: str, value: int, tx_hash: str
) -> str | None:
    """v23 bound for ESCROW_FEE_SWEEP (pure path).

    Mirrors ``validate_transaction``: the sweep may take residue (custody minus
    the job's remaining obligation) plus the governed fee allowance carried in
    the context, never more of the obligation than that.
    """
    if "remaining_obligation" not in context or context.get("obligation_unbounded"):
        return f"ESCROW_FEE_SWEEP for {job_id} cannot verify escrow obligation — missing or unbounded context"
    remaining_obligation = context["remaining_obligation"]
    if remaining_obligation is None:
        return None
    if "fee_allowance" not in context:
        return f"ESCROW_FEE_SWEEP for {job_id} cannot verify fee allowance — missing context"
    escrow_addr = context.get("escrow_addr") or _escrow_address(job_id)
    escrow_account = account_map.get(escrow_addr)
    custody = escrow_account.balance if escrow_account else 0
    sweepable = escrow_sweep_ceiling(custody, remaining_obligation, context["fee_allowance"])
    if value > sweepable:
        return f"ESCROW_FEE_SWEEP for {job_id} exceeds sweepable {sweepable}"
    return None


def _escrow_settlement_authority_delta(
    context: dict[str, Any],
    sender: str,
    recipient: str,
    tx_type: str,
    tx_hash: str,
    block_version: int,
) -> StateDelta | None:
    """v3+ settlement-authority gate for ESCROW_RELEASE/ESCROW_REFUND (pure path).

    The DB-capable context builder resolves the on-chain
    escrow_settlement_authority parameter (env fallback) once per batch;
    context-free callers fall back to the env-only lookup. Returns the
    failure delta, or None when the sender is authorized / the version
    predates the gate.
    """
    if block_version < 3:
        return None
    if "settlement_authority" in context:
        authority = context["settlement_authority"]
    else:
        authority = _escrow_settlement_authority()
    if authority is None:
        # v5 fails closed; below it the lenient rule keeps sealed history
        # replaying. Mirrors validate_transaction.
        if block_version >= 5:
            return StateDelta(
                sender=sender,
                recipient=recipient,
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error=f"{tx_type} requires a settlement authority: set the escrow_settlement_authority chain parameter",
                tx_type=tx_type,
                tx_hash=tx_hash,
            )
    elif sender != authority:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"{tx_type} must be signed by settlement authority {authority}, got {sender}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    return None


def _escrow_release_refund_delta(
    account_map: dict[str, Account],
    tx_data: dict[str, Any],
    sender: str,
    recipient: str,
    value: int,
    fee: int,
    tx_type: str,
    tx_hash: str,
    block_version: int,
    escrow_context: dict[str, dict[str, Any]] | None,
) -> StateDelta:
    """Validate and compute an ESCROW_RELEASE/ESCROW_REFUND delta."""
    payload = _decode_payload(tx_data.get("payload", {}) or {})
    job_id = payload.get("job_id", "")
    if not job_id:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"{tx_type} payload must include job_id",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    context = (escrow_context or {}).get(job_id, {})
    lock_version = context.get("lock_version")
    if lock_version is None:
        lock_version = 2 if block_version < 3 else 3
    expected_beneficiary = context.get("expected_beneficiary")
    if expected_beneficiary and recipient != expected_beneficiary:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"{tx_type} for {job_id} must pay {expected_beneficiary}, got {recipient}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    if block_version >= 23:
        obligation_error = _escrow_v23_release_obligation_error(context, job_id, value, tx_type, tx_hash)
        if obligation_error:
            return StateDelta(
                sender=sender,
                recipient=recipient,
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error=obligation_error,
                tx_type=tx_type,
                tx_hash=tx_hash,
            )
    authority_delta = _escrow_settlement_authority_delta(context, sender, recipient, tx_type, tx_hash, block_version)
    if authority_delta is not None:
        return authority_delta
    if lock_version >= 3:
        return _escrow_v3_release_refund_delta(account_map, sender, recipient, value, fee, tx_type, tx_hash, job_id, context)
    return _escrow_v2_release_refund_delta(account_map, sender, recipient, value, fee, tx_type, tx_hash)


def _escrow_fee_sweep_delta(
    account_map: dict[str, Account],
    tx_data: dict[str, Any],
    sender: str,
    recipient: str,
    value: int,
    fee: int,
    tx_type: str,
    tx_hash: str,
    block_version: int,
    escrow_context: dict[str, dict[str, Any]] | None,
) -> StateDelta:
    """Validate and compute a v11 ESCROW_FEE_SWEEP delta.

    The sweep pays the governed fee recipient out of the job's custody account
    — the same delta shape as a v3 release/refund (escrow debited via
    ``extra_debits``, sender pays only the fee) but with the recipient pinned
    to ``escrow_fee_recipient`` instead of the lock's beneficiary, and no lock
    requirement: the custody account is derived from ``payload.job_id``, and a
    job without one (v2-era lock, mistyped id) fails the balance check
    naturally. Mirrors ``validate_transaction``'s ESCROW_FEE_SWEEP branch.
    """
    payload = _decode_payload(tx_data.get("payload", {}) or {})
    job_id = payload.get("job_id", "")
    if not job_id:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error="ESCROW_FEE_SWEEP payload must include job_id",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    context = (escrow_context or {}).get(job_id, {})
    # Like settlement_authority: the DB-capable context builder resolves the
    # on-chain parameters at the block's height; context-free callers fall
    # back to the env-only lookups. v11 postdates v5, so an unset authority
    # always fails closed — no legacy lenient branch exists.
    if "settlement_authority" in context:
        authority = context["settlement_authority"]
    else:
        authority = _escrow_settlement_authority()
    if authority is None:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error="ESCROW_FEE_SWEEP requires a settlement authority: set the escrow_settlement_authority chain parameter",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    if sender != authority:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"ESCROW_FEE_SWEEP must be signed by settlement authority {authority}, got {sender}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    if "fee_recipient" in context:
        fee_recipient = context["fee_recipient"]
    else:
        fee_recipient = _escrow_fee_recipient()
    if fee_recipient is None:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error="ESCROW_FEE_SWEEP requires a fee recipient: set the escrow_fee_recipient chain parameter",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    if recipient != fee_recipient:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"ESCROW_FEE_SWEEP must pay {fee_recipient}, got {recipient}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )
    if block_version >= 23:
        sweep_error = _escrow_v23_sweep_obligation_error(account_map, context, job_id, value, tx_hash)
        if sweep_error:
            return StateDelta(
                sender=sender,
                recipient=recipient,
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error=sweep_error,
                tx_type=tx_type,
                tx_hash=tx_hash,
            )
    return _escrow_v3_release_refund_delta(account_map, sender, recipient, value, fee, tx_type, tx_hash, job_id, context)
