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
from typing import Any, cast

from sqlmodel import Session, select
from sqlalchemy import func, text

from ..base_models import Block, IPFSSubscription, _to_ait_address
from ..config import settings
from ..models import Account, Receipt


def _escrow_address(job_id: str) -> str:
    from aitbc.crypto.signature_recovery import canonical_address
    from eth_utils import keccak

    return canonical_address("0x" + keccak(f"aitbc.escrow.{job_id}".encode()).hex()[:40])


def _escrow_settlement_authority() -> str | None:
    """Return the canonical settlement authority for v3 escrow releases/refunds."""
    addr = settings.escrow_settlement_authority or ""
    if not addr:
        return None
    return _to_ait_address(addr)


def _decode_payload(payload: Any) -> dict[str, Any]:
    """Return payload as a dict, decoding JSON string if necessary."""
    if isinstance(payload, str):
        try:
            import json

            return cast(dict[str, Any], json.loads(payload))
        except Exception:
            return {}
    if not payload:
        return {}
    return cast(dict[str, Any], payload)


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
    if block_version >= 3:
        authority = _escrow_settlement_authority()
        if authority and sender != authority:
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
    if lock_version >= 3:
        return _escrow_v3_release_refund_delta(account_map, sender, recipient, value, fee, tx_type, tx_hash, job_id, context)
    return _escrow_v2_release_refund_delta(account_map, sender, recipient, value, fee, tx_type, tx_hash)


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
    # For IPFS_SUBSCRIPTION: subscription record to be written to the DB
    ipfs_subscription: dict[str, Any] | None = None
    # For ESCROW_LOCK v2/v3: additional accounts (e.g. provider) that the
    # sequential path would ensure exist. They carry zero balance change but
    # must be present in account state for matching state roots.
    extra_accounts: list[str] | None = None
    # For ESCROW_RELEASE/ESCROW_REFUND v3: per-account balance debits beyond
    # sender and recipient (e.g. the per-escrow address that loses value).
    extra_debits: dict[str, int] | None = None


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
    block_version: int = 2,
    escrow_context: dict[str, dict[str, Any]] | None = None,
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
        block_version: State-transition rule version active for the block.
        escrow_context: Per-job lock metadata needed for ESCROW_RELEASE/ESCROW_REFUND
            (lock_version, expected_beneficiary, escrow_addr). Callers must supply
            this when enabling parallel processing for blocks containing those tx types.

    Returns:
        StateDelta with balance/nonce changes, or success=False with error.
    """
    sender = _to_ait_address(tx_data.get("from", ""))
    recipient = _to_ait_address(tx_data.get("to", ""))
    tx_type = _determine_tx_type(tx_data)
    value = tx_data.get("value", tx_data.get("amount", 0))
    fee = tx_data.get("fee", 0)

    # S-4: release/refund logic is handled after sender/nonce validation.
    extra_debits: dict[str, int] | None = None

    # S-4: ESCROW_LOCK always creates the provider account, and v3 also
    # redirects the locked value to a deterministic per-escrow address.
    extra_accounts: list[str] | None = None
    if tx_type == "ESCROW_LOCK":
        payload = tx_data.get("payload", {}) or {}
        if isinstance(payload, str):
            try:
                import json

                payload = json.loads(payload)
            except Exception:
                payload = {}
        provider_addr = _to_ait_address(payload.get("provider", ""))
        extra_accounts = [a for a in [provider_addr] if a]
        if block_version >= 3:
            job_id = payload.get("job_id", "")
            if not job_id:
                return StateDelta(
                    sender=sender,
                    recipient=recipient,
                    sender_balance_change=0,
                    recipient_balance_change=0,
                    sender_nonce_change=0,
                    success=False,
                    error="ESCROW_LOCK v3 payload must include job_id",
                    tx_type=tx_type,
                    tx_hash=tx_hash,
                )
            if not payload.get("provider"):
                return StateDelta(
                    sender=sender,
                    recipient=recipient,
                    sender_balance_change=0,
                    recipient_balance_change=0,
                    sender_nonce_change=0,
                    success=False,
                    error="ESCROW_LOCK v3 payload must include provider",
                    tx_type=tx_type,
                    tx_hash=tx_hash,
                )
            recipient = _escrow_address(job_id)

    # Liquidity pool transactions update non-account state (pools, stakes,
    # distributions) that the parallel delta map cannot yet model. Force a
    # sequential fallback so StateTransition.apply_transaction handles them.
    if tx_type in {"LIQUIDITY_DEPOSIT", "LIQUIDITY_WITHDRAW", "LIQUIDITY_CLAIM"}:
        return StateDelta(
            sender=sender,
            recipient=recipient,
            sender_balance_change=0,
            recipient_balance_change=0,
            sender_nonce_change=0,
            success=False,
            error=f"{tx_type} must be processed sequentially",
            tx_type=tx_type,
            tx_hash=tx_hash,
        )

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

    # S-4: ESCROW_RELEASE/ESCROW_REFUND require the matching lock metadata.
    if tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND"):
        return _escrow_release_refund_delta(
            account_map,
            tx_data,
            sender,
            recipient,
            value,
            fee,
            tx_type,
            tx_hash,
            block_version,
            escrow_context,
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

    # IPFS_SUBSCRIPTION: payload must contain island subscription terms
    if tx_type == "IPFS_SUBSCRIPTION":
        payload = tx_data.get("payload", {}) or {}
        if isinstance(payload, str):
            try:
                import json

                payload = json.loads(payload)
            except Exception:
                return StateDelta(
                    sender=sender,
                    recipient=recipient,
                    sender_balance_change=0,
                    recipient_balance_change=0,
                    sender_nonce_change=0,
                    success=False,
                    error="IPFS_SUBSCRIPTION payload is not valid JSON",
                    tx_type=tx_type,
                    tx_hash=tx_hash,
                )
        if not payload.get("island_id"):
            return StateDelta(
                sender=sender,
                recipient=recipient,
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error="IPFS_SUBSCRIPTION payload must include island_id",
                tx_type=tx_type,
                tx_hash=tx_hash,
            )
        duration_blocks = payload.get("duration_blocks")
        if not isinstance(duration_blocks, int) or duration_blocks <= 0:
            return StateDelta(
                sender=sender,
                recipient=recipient,
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error="IPFS_SUBSCRIPTION payload must include positive duration_blocks",
                tx_type=tx_type,
                tx_hash=tx_hash,
            )
        quota_bytes = payload.get("quota_bytes")
        if not isinstance(quota_bytes, int) or quota_bytes < 0:
            return StateDelta(
                sender=sender,
                recipient=recipient,
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error="IPFS_SUBSCRIPTION payload must include non-negative quota_bytes",
                tx_type=tx_type,
                tx_hash=tx_hash,
            )
        if value <= 0:
            return StateDelta(
                sender=sender,
                recipient=recipient,
                sender_balance_change=0,
                recipient_balance_change=0,
                sender_nonce_change=0,
                success=False,
                error="IPFS_SUBSCRIPTION requires value > 0",
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

    # v0.25.5: recipient accounts are created on first credit, so a missing
    # recipient is not a validation failure.  The in-memory and DB apply paths
    # both create the account when the delta is committed.
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
        extra_accounts=extra_accounts,
        extra_debits=extra_debits,
    )

    # IPFS_SUBSCRIPTION: capture subscription terms for apply_deltas_to_db
    if tx_type == "IPFS_SUBSCRIPTION":
        payload = tx_data.get("payload", {}) or {}
        if isinstance(payload, str):
            try:
                import json

                payload = json.loads(payload)
            except Exception:
                payload = {}
        delta.ipfs_subscription = {
            "island_id": payload.get("island_id"),
            "duration_blocks": payload.get("duration_blocks", 0),
            "quota_bytes": payload.get("quota_bytes", 0),
        }

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


def apply_deltas_to_db(
    session: Session,
    deltas: list[StateDelta],
    chain_id: str,
    block_version: int = 2,
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

    # Ensure extra accounts exist (ESCROW_LOCK provider, etc.)
    for delta in successful:
        if delta.extra_accounts:
            for addr in delta.extra_accounts:
                if addr and addr != delta.recipient:
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

    # Apply extra debits (e.g. v3 escrow release refunds from escrow address)
    for delta in successful:
        if delta.extra_debits:
            for addr, change in delta.extra_debits.items():
                if not addr:
                    continue
                account = session.get(Account, (chain_id, addr))
                if account:
                    session.execute(
                        text(
                            "UPDATE account SET balance = balance + :balance_change "
                            "WHERE chain_id = :chain_id AND address = :address"
                        ),
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

    # Handle IPFS_SUBSCRIPTION deltas
    for delta in successful:
        if delta.tx_type == "IPFS_SUBSCRIPTION" and delta.ipfs_subscription:
            island_id = delta.ipfs_subscription.get("island_id")
            duration_blocks = delta.ipfs_subscription.get("duration_blocks", 0)
            quota_bytes = delta.ipfs_subscription.get("quota_bytes", 0)
            if not island_id or not isinstance(duration_blocks, int) or duration_blocks <= 0:
                continue
            current_height = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).first() or 0
            expires_at_block = current_height + duration_blocks
            existing = session.exec(
                select(IPFSSubscription).where(
                    IPFSSubscription.chain_id == chain_id,
                    IPFSSubscription.island_id == island_id,
                    IPFSSubscription.member_address == delta.sender,
                )
            ).first()
            from datetime import UTC, datetime

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

    session.flush()


def _add_receipt_rw_set(tx_data: dict[str, Any], read_set: set[str]) -> None:
    """Add the receipt dependency for RECEIPT_CLAIM transactions."""
    receipt_id = tx_data.get("payload", {}).get("receipt_id")
    if receipt_id:
        read_set.add(f"receipt:{receipt_id}")


def _add_ipfs_rw_set(tx_data: dict[str, Any], sender: str, read_set: set[str], write_set: set[str]) -> None:
    """Add island subscription read/write dependencies for IPFS_SUBSCRIPTION."""
    payload = _decode_payload(tx_data.get("payload", {}) or {})
    island_id = payload.get("island_id")
    if island_id:
        read_set.add(f"ipfs_subscription:{island_id}:{sender}")
        write_set.add(f"ipfs_subscription:{island_id}:{sender}")


def _add_escrow_rw_set(tx_data: dict[str, Any], read_set: set[str], write_set: set[str]) -> None:
    """Add per-escrow read/write dependencies for ESCROW_RELEASE/ESCROW_REFUND."""
    payload = _decode_payload(tx_data.get("payload", {}) or {})
    job_id = payload.get("job_id", "")
    if job_id:
        escrow_addr = _escrow_address(job_id)
        read_set.add(escrow_addr)
        write_set.add(escrow_addr)


def extract_read_write_sets(tx_data: dict[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    """Extract read/write sets from transaction data for dependency analysis.

    Args:
        tx_data: Transaction data (from, to, amount, fee, type, etc.).

    Returns:
        Tuple of (read_set, write_set) — sets of account addresses.
    """
    sender = _to_ait_address(tx_data.get("from", ""))
    recipient = _to_ait_address(tx_data.get("to", ""))
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
        _add_receipt_rw_set(tx_data, read_set)

    if tx_type == "IPFS_SUBSCRIPTION":
        _add_ipfs_rw_set(tx_data, sender, read_set, write_set)

    if tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND"):
        _add_escrow_rw_set(tx_data, read_set, write_set)

    return frozenset(read_set), frozenset(write_set)
