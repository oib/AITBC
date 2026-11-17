"""Pure state transition functions for parallel transaction validation.

This module provides pure functions that compute state deltas WITHOUT
touching the database. This enables parallel execution of transaction
validation — multiple threads can compute deltas simultaneously since
there are no shared mutable resources (no session, no SQL, no cache).

The existing `state_transition.py:apply_transaction` remains as the
sequential fallback path. This module is the parallel path.

Key design:
- `compute_state_delta` reads from `account_map` (in-memory), returns a `StateDelta`
- `apply_delta_to_map` mutates `account_map` in place (still no DB)
- `apply_deltas_to_db` writes accumulated deltas to the DB in a single batch

The shared primitives, escrow-delta builders, compute pipeline and
read/write-set helpers live in sibling modules
(``pure_state_transition_base``, ``pure_state_transition_escrow``,
``pure_state_transition_compute``, ``pure_state_transition_rwsets``); every
name is re-exported below so ``from
aitbc_chain.state.pure_state_transition import X`` keeps working unchanged.
"""

from __future__ import annotations

import os as os
from dataclasses import dataclass as dataclass
from datetime import UTC, datetime
from typing import Any as Any, cast as cast

from sqlmodel import Session, select
from sqlalchemy import func, text

from ..base_models import Block, IPFSSubscription, _to_ait_address as _to_ait_address
from ..config import settings as settings
from ..logger import get_logger
from .v9_policy import (
    V17_PAYLOAD_AUTH_TX_TYPES as V17_PAYLOAD_AUTH_TX_TYPES,
    _payload_auth_of as _payload_auth_of,
    count_v9_would_reject as count_v9_would_reject,
    v9_signature_verdict as v9_signature_verdict,
)
from ..models import Account, Receipt
from .bridge_credit import (
    bridge_refund_lock_hash as bridge_refund_lock_hash,
    validate_bridge_refund_lock as validate_bridge_refund_lock,
    verify_bridge_credit_signature as verify_bridge_credit_signature,
    verify_bridge_lock_signature as verify_bridge_lock_signature,
)
from .pure_state_transition_base import StateDelta

logger = get_logger(__name__)


def _ensure_extra_accounts_in_map(account_map: dict[str, Account], extra_accounts: list[str] | None, chain_id: str) -> None:
    """Create zero-balance accounts for any extra accounts that are missing."""
    if not extra_accounts:
        return
    for addr in extra_accounts:
        if addr and addr not in account_map:
            account_map[addr] = Account(
                chain_id=chain_id,
                address=addr,
                balance=0,
                nonce=0,
            )


def _apply_extra_debits_to_map(account_map: dict[str, Account], extra_debits: dict[str, int] | None, chain_id: str) -> None:
    """Apply per-account extra debits (e.g. v3 escrow release)."""
    if not extra_debits:
        return
    for addr, change in extra_debits.items():
        if not addr:
            continue
        account = account_map.get(addr)
        if account:
            account.balance += change
        else:
            account_map[addr] = Account(
                chain_id=chain_id,
                address=addr,
                balance=change,
                nonce=0,
            )


def apply_delta_to_map(
    account_map: dict[str, Account],
    delta: StateDelta,
    chain_id: str,
    block_version: int = 2,
) -> None:
    """Apply a StateDelta to the in-memory account_map.

    Mutates account_map in place. Does NOT touch the DB.
    Creates new Account entries for new recipients.

    Args:
        account_map: In-memory account state (will be mutated).
        delta: StateDelta from compute_state_delta.
        chain_id: Chain identifier.
        block_version: State-transition rule version active for the block.
    """
    if not delta.success:
        return

    # S-4 (ESCROW_LOCK): ensure provider/per-escrow accounts exist in the
    # in-memory map so the resulting account set matches the sequential path.
    _ensure_extra_accounts_in_map(account_map, delta.extra_accounts, chain_id)

    # Update sender
    sender_account = account_map.get(delta.sender)
    if sender_account:
        sender_account.balance += delta.sender_balance_change
        sender_account.nonce += delta.sender_nonce_change

    # Update recipient (if not MESSAGE type and recipient exists)
    if delta.tx_type != "MESSAGE" and delta.recipient:
        recipient_account = account_map.get(delta.recipient)
        if recipient_account:
            recipient_account.balance += delta.recipient_balance_change
        else:
            # Create new account for recipient
            new_account = Account(
                chain_id=chain_id,
                address=delta.recipient,
                balance=delta.recipient_balance_change,
                nonce=0,
            )
            account_map[delta.recipient] = new_account

    # S-4 (v3 release/refund): apply extra debits (e.g. per-escrow address)
    _apply_extra_debits_to_map(account_map, delta.extra_debits, chain_id)


def _apply_sender_updates(session: Session, successful: list[StateDelta], chain_id: str) -> None:
    """Batch UPDATE sender balances and nonces."""
    for delta in successful:
        session.execute(
            text(
                "UPDATE account SET balance = balance + :balance_change, "
                "nonce = nonce + :nonce_change "
                "WHERE chain_id = :chain_id AND address = :address"
            ),
            {
                "balance_change": delta.sender_balance_change,
                "nonce_change": delta.sender_nonce_change,
                "chain_id": chain_id,
                "address": delta.sender,
            },
        )


def _ensure_extra_account_in_db(session: Session, chain_id: str, addr: str) -> None:
    """Create a zero-balance account row for ``addr`` when it does not exist."""
    extra_account = session.get(Account, (chain_id, addr))
    if not extra_account:
        session.add(
            Account(
                chain_id=chain_id,
                address=addr,
                balance=0,
                nonce=0,
            )
        )


def _ensure_extra_accounts_in_db(session: Session, successful: list[StateDelta], chain_id: str) -> None:
    """Ensure extra accounts exist (ESCROW_LOCK provider, etc.)."""
    for delta in successful:
        if delta.extra_accounts:
            for addr in delta.extra_accounts:
                if addr and addr != delta.recipient:
                    _ensure_extra_account_in_db(session, chain_id, addr)


def _apply_recipient_update_in_db(session: Session, delta: StateDelta, chain_id: str) -> None:
    """Credit one delta's recipient balance, creating the row when missing."""
    # Check if recipient exists in DB
    recipient_account = session.get(Account, (chain_id, delta.recipient))
    if recipient_account:
        session.execute(
            text("UPDATE account SET balance = balance + :balance_change WHERE chain_id = :chain_id AND address = :address"),
            {
                "balance_change": delta.recipient_balance_change,
                "chain_id": chain_id,
                "address": delta.recipient,
            },
        )
    else:
        # Create new account for recipient
        new_account = Account(
            chain_id=chain_id,
            address=delta.recipient,
            balance=delta.recipient_balance_change,
            nonce=0,
        )
        session.add(new_account)


def _apply_recipient_updates(session: Session, successful: list[StateDelta], chain_id: str) -> None:
    """Batch UPDATE recipient balances (skip MESSAGE type)."""
    for delta in successful:
        if delta.tx_type != "MESSAGE" and delta.recipient:
            _apply_recipient_update_in_db(session, delta, chain_id)


def _apply_extra_debit_in_db(session: Session, chain_id: str, addr: str, change: int) -> None:
    """Apply one extra debit (e.g. v3 escrow release refund) to ``addr``."""
    account = session.get(Account, (chain_id, addr))
    if account:
        session.execute(
            text("UPDATE account SET balance = balance + :balance_change WHERE chain_id = :chain_id AND address = :address"),
            {
                "balance_change": change,
                "chain_id": chain_id,
                "address": addr,
            },
        )
    else:
        session.add(
            Account(
                chain_id=chain_id,
                address=addr,
                balance=change,
                nonce=0,
            )
        )


def _apply_extra_debits_in_db(session: Session, successful: list[StateDelta], chain_id: str) -> None:
    """Apply extra debits (e.g. v3 escrow release refunds from escrow address)."""
    for delta in successful:
        if delta.extra_debits:
            for addr, change in delta.extra_debits.items():
                if not addr:
                    continue
                _apply_extra_debit_in_db(session, chain_id, addr, change)


def _settle_receipt_row(
    session: Session,
    receipt: Receipt | None,
    delta: StateDelta,
    receipt_id: str,
    chain_id: str,
    block_height: int | None,
    block_time: datetime | None,
) -> Receipt | None:
    """Materialise a carried-issuance receipt row or settle a pending one (#687).

    Returns the receipt row (still possibly None) for the minted_amount check.
    """
    if receipt is None and delta.receipt_record is not None:
        # Carried issuance (#687): materialise the receipt row from the
        # claim payload so every node converges on the same claimed
        # record — minted_amount stays NULL (claim never mints).
        receipt = Receipt(
            chain_id=chain_id,
            job_id=str(delta.receipt_record.get("job_id") or ""),
            receipt_id=receipt_id,
            block_height=block_height,
            payload=delta.receipt_record.get("payload") if isinstance(delta.receipt_record.get("payload"), dict) else {},
            miner_signature=delta.receipt_record["miner_signature"],
            coordinator_attestations=delta.receipt_record["coordinator_attestations"],
            minted_amount=None,
            status="claimed",
            claimed_at=block_time or datetime.now(UTC),
            claimed_by=delta.sender,
        )
        session.add(receipt)
    elif receipt is not None and receipt.status == "pending" and not receipt.minted_amount:
        # A service-recorded pending row claimed with no mint attached:
        # settle it so nodes holding the row converge with the
        # materialised-claimed shape other nodes build (#687).
        receipt.status = "claimed"
        receipt.claimed_by = delta.sender
        receipt.claimed_at = block_time or datetime.now(UTC)
    return receipt


def _apply_receipt_claim_delta(
    session: Session,
    delta: StateDelta,
    receipt_id: str,
    chain_id: str,
    block_height: int | None,
    block_time: datetime | None,
) -> None:
    """Handle one RECEIPT_CLAIM delta (receipt status + minted amount)."""
    receipt = session.exec(select(Receipt).where(Receipt.chain_id == chain_id, Receipt.receipt_id == receipt_id)).first()
    receipt = _settle_receipt_row(session, receipt, delta, receipt_id, chain_id, block_height, block_time)
    if receipt and receipt.minted_amount:
        # Add minted amount to sender balance
        session.execute(
            text("UPDATE account SET balance = balance + :minted_amount WHERE chain_id = :chain_id AND address = :address"),
            {
                "minted_amount": receipt.minted_amount,
                "chain_id": chain_id,
                "address": delta.sender,
            },
        )
        receipt.status = "claimed"
        receipt.claimed_by = delta.sender
        receipt.claimed_at = block_time or datetime.now(UTC)


def _apply_receipt_claim_deltas(
    session: Session,
    successful: list[StateDelta],
    chain_id: str,
    block_height: int | None,
    block_time: datetime | None,
) -> None:
    """Handle RECEIPT_CLAIM deltas (updates receipt status + mints amount)."""
    for delta in successful:
        receipt_id = delta.receipt_id
        if delta.tx_type == "RECEIPT_CLAIM" and receipt_id:
            _apply_receipt_claim_delta(session, delta, receipt_id, chain_id, block_height, block_time)


def _upsert_ipfs_subscription(session: Session, delta: StateDelta, chain_id: str) -> None:
    """Write one IPFS_SUBSCRIPTION delta's subscription row."""
    subscription = delta.ipfs_subscription
    if subscription is None:
        return
    island_id = subscription.get("island_id")
    duration_blocks = subscription.get("duration_blocks", 0)
    quota_bytes = subscription.get("quota_bytes", 0)
    if not island_id or not isinstance(duration_blocks, int) or duration_blocks <= 0:
        return
    current_height = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).first() or 0
    expires_at_block = current_height + duration_blocks
    existing = session.exec(
        select(IPFSSubscription).where(
            IPFSSubscription.chain_id == chain_id,
            IPFSSubscription.island_id == island_id,
            IPFSSubscription.member_address == delta.sender,
        )
    ).first()
    now = datetime.now(UTC)
    if existing:
        existing.expires_at_block = max(existing.expires_at_block, expires_at_block)
        existing.quota_bytes += quota_bytes
        existing.updated_tx_hash = delta.tx_hash
        existing.updated_at = now
    else:
        session.add(
            IPFSSubscription(
                chain_id=chain_id,
                island_id=island_id,
                member_address=delta.sender,
                expires_at_block=expires_at_block,
                quota_bytes=quota_bytes,
                used_bytes=0,
                created_tx_hash=delta.tx_hash,
                updated_tx_hash=delta.tx_hash,
                created_at=now,
                updated_at=now,
            )
        )


def _apply_ipfs_subscription_deltas(session: Session, successful: list[StateDelta], chain_id: str) -> None:
    """Handle IPFS_SUBSCRIPTION deltas."""
    for delta in successful:
        if delta.tx_type == "IPFS_SUBSCRIPTION" and delta.ipfs_subscription:
            _upsert_ipfs_subscription(session, delta, chain_id)


def apply_deltas_to_db(
    session: Session,
    deltas: list[StateDelta],
    chain_id: str,
    block_version: int = 2,
    *,
    block_height: int | None = None,
    block_time: datetime | None = None,
) -> None:
    """Write accumulated state deltas to the DB in a single batch.

    Groups all sender debits and recipient credits into batch UPDATEs.
    Much faster than per-tx SQL UPDATEs.

    Also handles RECEIPT_CLAIM deltas (updates receipt status + mints amount).

    Args:
        session: Database session.
        deltas: List of successful StateDelta objects.
        chain_id: Chain identifier.
        block_version: State-transition rule version active for the block.
        block_height: Height of the block being applied — stamped onto
            receipt rows a carried-issuance RECEIPT_CLAIM materialises.
        block_time: Sealed block-header timestamp for the same rows'
            ``claimed_at`` (falls back to wall-clock when absent).
    """
    successful = [d for d in deltas if d.success]
    if not successful:
        return

    _apply_sender_updates(session, successful, chain_id)

    # Ensure extra accounts exist (ESCROW_LOCK provider, etc.)
    _ensure_extra_accounts_in_db(session, successful, chain_id)

    # Batch UPDATE recipient balances (skip MESSAGE type)
    _apply_recipient_updates(session, successful, chain_id)

    # Apply extra debits (e.g. v3 escrow release refunds from escrow address)
    _apply_extra_debits_in_db(session, successful, chain_id)

    # Handle RECEIPT_CLAIM deltas
    _apply_receipt_claim_deltas(session, successful, chain_id, block_height, block_time)

    # Handle IPFS_SUBSCRIPTION deltas
    _apply_ipfs_subscription_deltas(session, successful, chain_id)

    session.flush()


# Pure-move split re-exports: every name this module defined before the split
# stays importable from ``aitbc_chain.state.pure_state_transition`` —
# including private helpers and monkeypatch targets. ``StateDelta`` and
# ``logger`` are already bound above.
from .pure_state_transition_base import (
    SEQUENTIAL_ONLY_TX_TYPES as SEQUENTIAL_ONLY_TX_TYPES,
    _carried_receipt_record as _carried_receipt_record,
    _decode_payload as _decode_payload,
    _determine_tx_type as _determine_tx_type,
    _escrow_address as _escrow_address,
    _escrow_fee_recipient as _escrow_fee_recipient,
    _escrow_settlement_authority as _escrow_settlement_authority,
    _fail_delta as _fail_delta,
)
from .pure_state_transition_escrow import (
    DEFAULT_ESCROW_FEE_CAP_BPS as DEFAULT_ESCROW_FEE_CAP_BPS,
    MAX_ESCROW_FEE_CAP_BPS as MAX_ESCROW_FEE_CAP_BPS,
    _escrow_fee_sweep_delta as _escrow_fee_sweep_delta,
    _escrow_release_refund_delta as _escrow_release_refund_delta,
    _escrow_settlement_authority_delta as _escrow_settlement_authority_delta,
    _escrow_v2_release_refund_delta as _escrow_v2_release_refund_delta,
    _escrow_v23_release_obligation_error as _escrow_v23_release_obligation_error,
    _escrow_v23_sweep_obligation_error as _escrow_v23_sweep_obligation_error,
    _escrow_v3_release_refund_delta as _escrow_v3_release_refund_delta,
    escrow_sweep_ceiling as escrow_sweep_ceiling,
)
from .pure_state_transition_compute import (
    _auth_gates_delta as _auth_gates_delta,
    _bridge_credit_delta as _bridge_credit_delta,
    _bridge_lock_signature_error as _bridge_lock_signature_error,
    _bridge_refund_lock_error as _bridge_refund_lock_error,
    _escrow_dispatch_delta as _escrow_dispatch_delta,
    _escrow_lock_precheck as _escrow_lock_precheck,
    _finalize_delta as _finalize_delta,
    _generic_transfer_delta as _generic_transfer_delta,
    _ipfs_subscription_field_error as _ipfs_subscription_field_error,
    _ipfs_subscription_validate as _ipfs_subscription_validate,
    _payload_auth_gate_delta as _payload_auth_gate_delta,
    _pre_sender_delta as _pre_sender_delta,
    _pre_transfer_validation_delta as _pre_transfer_validation_delta,
    _sender_account_and_nonce_delta as _sender_account_and_nonce_delta,
    _sender_signature_gate_delta as _sender_signature_gate_delta,
    _v9_signature_gate_delta as _v9_signature_gate_delta,
    compute_state_delta as compute_state_delta,
)
from .pure_state_transition_rwsets import (
    _add_escrow_rw_set as _add_escrow_rw_set,
    _add_ipfs_rw_set as _add_ipfs_rw_set,
    _add_receipt_rw_set as _add_receipt_rw_set,
    extract_read_write_sets as extract_read_write_sets,
)
