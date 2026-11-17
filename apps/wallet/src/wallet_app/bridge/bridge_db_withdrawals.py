"""AIT->ETH withdrawal rows and release-attempt audit for the shared bridge
ledger.

Split out of ``bridge_db.py`` (pure code motion): ``eth_withdrawals``
lifecycle plus the ETH-14 ``eth_withdrawal_release_attempts`` audit table.
Connection handling, ``DB_PATH`` and the schema live in ``bridge_db`` —
helpers are imported back from that module so a monkeypatched
``bridge_db.DB_PATH`` keeps applying here.
"""

import sqlite3
from collections.abc import Collection
from decimal import Decimal
from typing import Any

from wallet_app.utc_time import utc_now_iso

from .bridge_db import _connect_db


def insert_withdrawal(
    ait_tx_hash: str,
    from_address: str,
    eth_address: str,
    amount_ait: Decimal,
    fee_ait: Decimal,
    net_ait: Decimal,
    amount_eth: Decimal,
    status: str = "pending",
    error: str | None = None,
    ait_block_height: int | None = None,
    ait_block_hash: str | None = None,
) -> str:
    """Record a new ETH withdrawal request."""
    import uuid

    withdrawal_id = f"withdrawal_{uuid.uuid4().hex[:8]}"

    conn = _connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO eth_withdrawals (
                id, ait_tx_hash, from_address, eth_address, amount_ait, fee_ait, net_ait,
                amount_eth, status, error, created_at, ait_block_height, ait_block_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                withdrawal_id,
                ait_tx_hash,
                from_address,
                eth_address,
                amount_ait,
                fee_ait,
                net_ait,
                amount_eth,
                status,
                error,
                utc_now_iso(),
                ait_block_height,
                ait_block_hash,
            ),
        )
        conn.commit()
        return withdrawal_id
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Withdrawal with ait_tx_hash {ait_tx_hash} already exists") from None
    finally:
        conn.close()


def get_withdrawal_by_ait_tx_hash(ait_tx_hash: str) -> dict[str, Any] | None:
    """Get a withdrawal by its AIT transaction hash."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id, ait_tx_hash, from_address, eth_address, amount_ait, fee_ait, net_ait,
            amount_eth, status, eth_tx_hash, refund_tx_hash, error, created_at,
            released_at, completed_at, refunded_at, release_nonce, retry_count,
            ait_block_height, ait_block_hash
        FROM eth_withdrawals
        WHERE ait_tx_hash = ?
        """,
        (ait_tx_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    keys = [
        "id",
        "ait_tx_hash",
        "from_address",
        "eth_address",
        "amount_ait",
        "fee_ait",
        "net_ait",
        "amount_eth",
        "status",
        "eth_tx_hash",
        "refund_tx_hash",
        "error",
        "created_at",
        "released_at",
        "completed_at",
        "refunded_at",
        "release_nonce",
        "retry_count",
        "ait_block_height",
        "ait_block_hash",
    ]
    return dict(zip(keys, row, strict=False))


def get_pending_withdrawals() -> list[dict[str, Any]]:
    """Get all withdrawals not yet completed or refunded."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id, ait_tx_hash, from_address, eth_address, amount_ait, fee_ait, net_ait,
            amount_eth, status, eth_tx_hash, refund_tx_hash, error, created_at,
            released_at, completed_at, refunded_at, release_nonce,
            ait_block_height, ait_block_hash
        FROM eth_withdrawals
        WHERE status IN ('pending', 'insufficient_reserve', 'failed', 'releasing', 'needs_review',
                         'releasing_retry', 'needs_review_release')
        ORDER BY created_at ASC
        """,
    )
    rows = cursor.fetchall()
    conn.close()
    keys = [
        "id",
        "ait_tx_hash",
        "from_address",
        "eth_address",
        "amount_ait",
        "fee_ait",
        "net_ait",
        "amount_eth",
        "status",
        "eth_tx_hash",
        "refund_tx_hash",
        "error",
        "created_at",
        "released_at",
        "completed_at",
        "refunded_at",
        "release_nonce",
        "ait_block_height",
        "ait_block_hash",
    ]
    return [dict(zip(keys, row, strict=False)) for row in rows]


def get_resumable_withdrawals() -> list[dict[str, Any]]:
    """Withdrawals left mid-release ('releasing'/'releasing_retry') or
    unverifiable ('needs_review').

    A crash between the ETH broadcast and the status write leaves a
    'releasing' row; the monitor re-verifies these against the chain
    on every poll and after restart instead of retrying or refunding
    blindly. 'releasing_retry' rows are operator-driven re-releases —
    they are re-verified the same way, but a proven failure parks them
    at 'needs_review_release' instead of auto-refunding. That parked
    status is deliberately NOT resumable: only an operator moves it.
    """
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id, ait_tx_hash, from_address, eth_address, amount_ait, fee_ait, net_ait,
            amount_eth, status, eth_tx_hash, refund_tx_hash, error, created_at,
            released_at, completed_at, refunded_at, release_nonce,
            ait_block_height, ait_block_hash
        FROM eth_withdrawals
        WHERE status IN ('releasing', 'needs_review', 'releasing_retry')
        ORDER BY created_at ASC
        """,
    )
    rows = cursor.fetchall()
    conn.close()
    keys = [
        "id",
        "ait_tx_hash",
        "from_address",
        "eth_address",
        "amount_ait",
        "fee_ait",
        "net_ait",
        "amount_eth",
        "status",
        "eth_tx_hash",
        "refund_tx_hash",
        "error",
        "created_at",
        "released_at",
        "completed_at",
        "refunded_at",
        "release_nonce",
        "ait_block_height",
        "ait_block_hash",
    ]
    return [dict(zip(keys, row, strict=False)) for row in rows]


def get_awaiting_depth_withdrawals() -> list[dict[str, Any]]:
    """Withdrawals recorded before they reached BRIDGE_WITHDRAW_SEAL_DEPTH.

    The monitor re-checks these every poll: once the chain head clears
    their recorded ait_block_height by the required depth — and a
    canonical lookup still shows the tx sealed in that same block — they
    move to 'pending' and enter the normal release path. A tx that
    vanished from the canonical chain became 'orphaned' — the reorg
    already un-burned the AIT, so no refund is needed.
    """
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id, ait_tx_hash, from_address, eth_address, amount_ait, ait_block_height,
            ait_block_hash, status, created_at
        FROM eth_withdrawals
        WHERE status = 'awaiting_depth'
        ORDER BY created_at ASC
        """,
    )
    rows = cursor.fetchall()
    conn.close()
    keys = [
        "id",
        "ait_tx_hash",
        "from_address",
        "eth_address",
        "amount_ait",
        "ait_block_height",
        "ait_block_hash",
        "status",
        "created_at",
    ]
    return [dict(zip(keys, row, strict=False)) for row in rows]


def update_withdrawal_block(ait_tx_hash: str, ait_block_height: int, ait_block_hash: str | None) -> bool:
    """Refresh the sealing block on an awaiting-depth row after a reorg."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE eth_withdrawals SET ait_block_height = ?, ait_block_hash = ? WHERE ait_tx_hash = ?",
        (ait_block_height, ait_block_hash, ait_tx_hash),
    )
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def update_withdrawal_pricing(ait_tx_hash: str, *, fee_ait: Decimal, net_ait: Decimal, amount_eth: Decimal) -> bool:
    """Fill in the priced legs on a row inserted before pricing existed.

    'awaiting_depth' rows carry amount_eth=0 until they are deep enough to
    release; when the drain promotes one to 'pending' it stores the price
    it is about to pay so the ledger (and the payout audit) shows it.
    """
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE eth_withdrawals SET fee_ait = ?, net_ait = ?, amount_eth = ? WHERE ait_tx_hash = ?",
        (fee_ait, net_ait, amount_eth, ait_tx_hash),
    )
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def get_all_withdrawals(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Get all withdrawals with pagination."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id, ait_tx_hash, from_address, eth_address, amount_ait, fee_ait, net_ait,
            amount_eth, status, eth_tx_hash, refund_tx_hash, error, created_at,
            released_at, completed_at, refunded_at, release_nonce,
            ait_block_height, ait_block_hash
        FROM eth_withdrawals
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    rows = cursor.fetchall()
    conn.close()
    keys = [
        "id",
        "ait_tx_hash",
        "from_address",
        "eth_address",
        "amount_ait",
        "fee_ait",
        "net_ait",
        "amount_eth",
        "status",
        "eth_tx_hash",
        "refund_tx_hash",
        "error",
        "created_at",
        "released_at",
        "completed_at",
        "refunded_at",
        "release_nonce",
        "ait_block_height",
        "ait_block_hash",
    ]
    return [dict(zip(keys, row, strict=False)) for row in rows]


def update_withdrawal_status(
    ait_tx_hash: str,
    status: str,
    eth_tx_hash: str | None = None,
    refund_tx_hash: str | None = None,
    error: str | None = None,
    release_nonce: int | None = None,
    expected_statuses: Collection[str] | None = None,
) -> bool:
    """Update withdrawal status and optional hashes.

    ``expected_statuses`` is the CAS predicate (#1918), same shape as
    update_deposit_status (#1796): when given, the UPDATE only lands while
    the row still sits in one of those statuses, so a stale writer cannot
    overwrite a state that has already moved on. rowcount 0 -> False.
    """
    conn = _connect_db()
    cursor = conn.cursor()

    timestamp_field = "released_at"
    if status == "completed":
        timestamp_field = "completed_at"
    elif status == "refunded":
        timestamp_field = "refunded_at"

    # timestamp_field is a hardcoded literal above, never caller input
    query = f"""
        UPDATE eth_withdrawals
        SET status = ?, {timestamp_field} = ?, eth_tx_hash = COALESCE(?, eth_tx_hash),
            refund_tx_hash = COALESCE(?, refund_tx_hash), error = COALESCE(?, error),
            release_nonce = COALESCE(?, release_nonce)
        WHERE ait_tx_hash = ?
    """  # nosec
    params: tuple = (status, utc_now_iso(), eth_tx_hash, refund_tx_hash, error, release_nonce, ait_tx_hash)
    if expected_statuses:
        expected = tuple(expected_statuses)
        query += f" AND status IN ({', '.join('?' for _ in expected)})"
        params = (*params, *expected)
    cursor.execute(query, params)
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


# Withdrawal statuses where the ETH release happened or may have happened —
# the committed-since semantics mirror _SELL_ETH_COMMITTED_STATUSES: the cap
# measures ETH that left the wallet, so ambiguous rows count conservatively.
# `pending`/`insufficient_reserve` sent nothing; `failed`/`refunded` proved
# no completed send (only gas at worst) and are excluded.
_WITHDRAWAL_ETH_COMMITTED_STATUSES = (
    "releasing",
    "releasing_retry",
    "released",
    "needs_review",
    "needs_review_release",
    "completed",
)


def get_withdrawal_eth_committed_since(since_iso: str) -> Decimal:
    """Sum of ETH released (or possibly released) by withdrawals since a
    timestamp — the withdrawal lane's contribution to the release windows
    surfaced by GET /v1/bridge/float (CLI-5)."""
    conn = _connect_db()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in _WITHDRAWAL_ETH_COMMITTED_STATUSES)
    # placeholders are literal '?' generated from _WITHDRAWAL_ETH_COMMITTED_STATUSES; all values bound
    cursor.execute(
        f"""SELECT amount_eth FROM eth_withdrawals
            WHERE status IN ({placeholders})
              AND released_at >= ?""",  # nosec
        (*_WITHDRAWAL_ETH_COMMITTED_STATUSES, since_iso),
    )
    total = Decimal(0)
    for (amount,) in cursor.fetchall():
        if amount is not None:
            total += amount if isinstance(amount, Decimal) else Decimal(str(amount))
    conn.close()
    return total


# ---------------------------------------------------------------------------
# ETH-14 — operator release-retry attempts
# ---------------------------------------------------------------------------


def record_release_attempt(ait_tx_hash: str, resolved_by: str, operator_note: str | None) -> int:
    """Register an operator release attempt BEFORE the send is signed.

    Bumps ``retry_count`` on the withdrawal row and inserts the attempt
    record carrying who asked and why. Returns the attempt id — the caller
    fills in ``eth_tx_hash``/``release_nonce``/``outcome`` afterwards via
    :func:`update_release_attempt`.
    """
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE eth_withdrawals SET retry_count = COALESCE(retry_count, 0) + 1 WHERE ait_tx_hash = ?",
        (ait_tx_hash,),
    )
    cursor.execute(
        """
        INSERT INTO eth_withdrawal_release_attempts
            (ait_tx_hash, resolved_by, resolved_at, operator_note)
        VALUES (?, ?, ?, ?)
        """,
        (ait_tx_hash, resolved_by, utc_now_iso(), operator_note),
    )
    attempt_id = int(cursor.lastrowid or 0)
    conn.commit()
    conn.close()
    return attempt_id


def update_release_attempt(
    attempt_id: int,
    *,
    eth_tx_hash: str | None = None,
    release_nonce: int | None = None,
    outcome: str | None = None,
) -> bool:
    """Fill in an attempt row with the produced hash/nonce and its outcome."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE eth_withdrawal_release_attempts
        SET eth_tx_hash = COALESCE(?, eth_tx_hash),
            release_nonce = COALESCE(?, release_nonce),
            outcome = COALESCE(?, outcome)
        WHERE id = ?
        """,
        (eth_tx_hash, release_nonce, outcome, attempt_id),
    )
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def get_release_attempts(ait_tx_hash: str) -> list[dict[str, Any]]:
    """All recorded release attempts for a withdrawal, oldest first."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, ait_tx_hash, eth_tx_hash, release_nonce, resolved_by,
               resolved_at, operator_note, outcome
        FROM eth_withdrawal_release_attempts
        WHERE ait_tx_hash = ?
        ORDER BY id ASC
        """,
        (ait_tx_hash,),
    )
    rows = cursor.fetchall()
    conn.close()
    keys = [
        "id",
        "ait_tx_hash",
        "eth_tx_hash",
        "release_nonce",
        "resolved_by",
        "resolved_at",
        "operator_note",
        "outcome",
    ]
    return [dict(zip(keys, row, strict=False)) for row in rows]
