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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select
from sqlalchemy import text

from ..models import Account, Receipt


@dataclass
class StateDelta:
    """State change resulting from a transaction.

    Captures the balance/nonce changes without touching the DB.
    The delta can be applied to account_map (in-memory) or to the DB (batch).
    """

    sender: str
    recipient: str
    sender_balance_change: int  # negative (debit)
    recipient_balance_change: int  # positive (credit)
    sender_nonce_change: int  # +1
    success: bool
    error: str = ""
    tx_type: str = "TRANSFER"
    tx_hash: str = ""
    # For RECEIPT_CLAIM: the receipt_id and minted_amount (if claimed)
    receipt_id: str | None = None
    minted_amount: int | None = None


def _determine_tx_type(tx_data: dict[str, Any]) -> str:
    """Determine the transaction type from tx_data.

    Mirrors the logic in state_transition.py:150-161 but without DB access.
    """
    tx_type = tx_data.get("type", "TRANSFER")
    if not tx_type or tx_type == "TRANSFER":
        payload = tx_data.get("payload", {})
        if isinstance(payload, dict):
            tx_type = payload.get("type", "TRANSFER")
    if tx_type:
        return str(tx_type).upper()
    return "TRANSFER"


def compute_state_delta(
    account_map: dict[str, Account],
    tx_data: dict[str, Any],
    chain_id: str,
    tx_hash: str = "",
    existing_tx_hashes: set[str] | None = None,
) -> StateDelta:
    """Compute the state delta for a transaction WITHOUT modifying the DB.

    Pure function — reads from account_map (in-memory), returns a StateDelta.
    Does NOT touch the session, does NOT execute SQL, does NOT invalidate cache.

    Args:
        account_map: In-memory account state (pre-fetched from DB).
        tx_data: Transaction data (from, to, amount, fee, type, etc.).
        chain_id: Chain identifier.
        tx_hash: Transaction hash (for duplicate detection).
        existing_tx_hashes: Set of already-processed tx hashes (for duplicate check).

    Returns:
        StateDelta with balance/nonce changes, or success=False with error.
    """
    sender = tx_data.get("from", "")
    recipient = tx_data.get("to", "")
    tx_type = _determine_tx_type(tx_data)
    value = tx_data.get("value", tx_data.get("amount", 0))
    fee = tx_data.get("fee", 0)

    # Validate sender exists
    if not sender:
        return StateDelta(
            sender="",
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error="Missing sender",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )

    # Chain isolation check
    tx_chain_id = tx_data.get("chain_id")
    if tx_chain_id and tx_chain_id != chain_id:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"Chain isolation violation: transaction chain_id={tx_chain_id} does not match node chain_id={chain_id}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )

    # Duplicate tx check (in-memory)
    if existing_tx_hashes is not None and tx_hash in existing_tx_hashes:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"Transaction {tx_hash} already processed (replay attack)",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )

    sender_account = account_map.get(sender)
    if not sender_account:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"Sender account not found: {sender}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )

    # Nonce validation
    expected_nonce = sender_account.nonce if sender_account.nonce is not None else 0
    tx_nonce = tx_data.get("nonce", 0)
    if tx_nonce != expected_nonce:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"Invalid nonce for {sender}: expected {expected_nonce}, got {tx_nonce}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )

    # MESSAGE type: value must be 0
    if tx_type == "MESSAGE" and value != 0:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"MESSAGE transactions must have value=0, got {value}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )

    # Calculate total cost
    if tx_type == "MESSAGE":
        total_cost = fee
    else:
        total_cost = value + fee

    # Balance check
    if sender_account.balance < total_cost:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"Insufficient balance for {sender}: {sender_account.balance} < {total_cost}",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )

    # For non-MESSAGE, non-RECEIPT_CLAIM: recipient must exist
    if tx_type not in {"MESSAGE", "RECEIPT_CLAIM"}:
        if not recipient:
            return StateDelta(
                sender=sender,
                recipient="",
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error="Missing recipient",
                tx_type=tx_type,
                tx_hash=tx_hash,
            )
        recipient_account = account_map.get(recipient)
        if not recipient_account:
            return StateDelta(
                sender=sender,
                recipient=recipient,
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error=f"Recipient account not found: {recipient}",
                tx_type=tx_type,
                tx_hash=tx_hash,
            )

    # Compute delta
    sender_balance_change = -total_cost
    recipient_balance_change = 0
    if tx_type != "MESSAGE":
        recipient_balance_change = value

    delta = StateDelta(
        sender=sender,
        recipient=recipient,
        sender_balance_change=sender_balance_change,
        recipient_balance_change=recipient_balance_change,
        sender_nonce_change=1,
        success=True,
        tx_type=tx_type,
        tx_hash=tx_hash,
    )

    # RECEIPT_CLAIM: note the receipt_id for later DB processing
    # (receipt validation requires DB access, so we just record it here)
    if tx_type == "RECEIPT_CLAIM":
        receipt_id = tx_data.get("payload", {}).get("receipt_id")
        if not receipt_id:
            return StateDelta(
                sender=sender,
                recipient=recipient,
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error="RECEIPT_CLAIM transactions must include receipt_id in payload",
                tx_type=tx_type,
                tx_hash=tx_hash,
            )
        delta.receipt_id = receipt_id
        # minted_amount will be set during apply_deltas_to_db (requires DB read)

    return delta


def apply_delta_to_map(
    account_map: dict[str, Account],
    delta: StateDelta,
    chain_id: str,
) -> None:
    """Apply a StateDelta to the in-memory account_map.

    Mutates account_map in place. Does NOT touch the DB.
    Creates new Account entries for new recipients.

    Args:
        account_map: In-memory account state (will be mutated).
        delta: StateDelta from compute_state_delta.
        chain_id: Chain identifier.
    """
    if not delta.success:
        return

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


def apply_deltas_to_db(
    session: Session,
    deltas: list[StateDelta],
    chain_id: str,
) -> None:
    """Write accumulated state deltas to the DB in a single batch.

    Groups all sender debits and recipient credits into batch UPDATEs.
    Much faster than per-tx SQL UPDATEs.

    Also handles RECEIPT_CLAIM deltas (updates receipt status + mints amount).

    Args:
        session: Database session.
        deltas: List of successful StateDelta objects.
        chain_id: Chain identifier.
    """
    successful = [d for d in deltas if d.success]
    if not successful:
        return

    # Batch UPDATE sender balances and nonces
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

    # Batch UPDATE recipient balances (skip MESSAGE type)
    for delta in successful:
        if delta.tx_type != "MESSAGE" and delta.recipient:
            # Check if recipient exists in DB
            recipient_account = session.get(Account, (chain_id, delta.recipient))
            if recipient_account:
                session.execute(
                    text(
                        "UPDATE account SET balance = balance + :balance_change "
                        "WHERE chain_id = :chain_id AND address = :address"
                    ),
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

    # Handle RECEIPT_CLAIM deltas
    for delta in successful:
        if delta.tx_type == "RECEIPT_CLAIM" and delta.receipt_id:
            receipt = session.exec(
                select(Receipt).where(Receipt.chain_id == chain_id, Receipt.receipt_id == delta.receipt_id)
            ).first()
            if receipt and receipt.minted_amount:
                # Add minted amount to sender balance
                session.execute(
                    text(
                        "UPDATE account SET balance = balance + :minted_amount "
                        "WHERE chain_id = :chain_id AND address = :address"
                    ),
                    {
                        "minted_amount": receipt.minted_amount,
                        "chain_id": chain_id,
                        "address": delta.sender,
                    },
                )
                receipt.status = "claimed"
                receipt.claimed_by = delta.sender
                from datetime import UTC, datetime

                receipt.claimed_at = datetime.now(UTC)

    session.flush()


def extract_read_write_sets(tx_data: dict[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    """Extract read/write sets from transaction data for dependency analysis.

    Args:
        tx_data: Transaction data (from, to, amount, fee, type, etc.).

    Returns:
        Tuple of (read_set, write_set) — sets of account addresses.
    """
    sender = tx_data.get("from", "")
    recipient = tx_data.get("to", "")
    tx_type = _determine_tx_type(tx_data)

    read_set: set[str] = set()
    write_set: set[str] = set()

    if sender:
        read_set.add(sender)
        write_set.add(sender)

    if tx_type != "MESSAGE" and recipient:
        read_set.add(recipient)
        write_set.add(recipient)

    if tx_type == "RECEIPT_CLAIM":
        receipt_id = tx_data.get("payload", {}).get("receipt_id")
        if receipt_id:
            # Receipt is an additional read dependency
            read_set.add(f"receipt:{receipt_id}")

    return frozenset(read_set), frozenset(write_set)
