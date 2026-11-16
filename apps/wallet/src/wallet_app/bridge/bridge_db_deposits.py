"""ETH->AIT deposit rows for the shared bridge ledger.

Split out of ``bridge_db.py`` (pure code motion): ``eth_deposits`` insert,
lookup, lifecycle-CAS and status vocabulary. Connection handling, ``DB_PATH``
and the schema live in ``bridge_db`` — helpers are imported back from that
module so a monkeypatched ``bridge_db.DB_PATH`` keeps applying here.
"""

import sqlite3
from collections.abc import Collection
from decimal import Decimal
from typing import Any

from wallet_app.utc_time import utc_now_iso

from .bridge_db import _canon_tx_hash, _connect_db, _tx_hash_keys


def insert_deposit(
    tx_hash: str,
    from_address: str,
    amount_eth: Decimal,
    amount_ait: Decimal,
    recipient: str | None = None,
    deposit_address: str | None = None,
) -> str:
    """Insert a new deposit record. ``tx_hash`` is stored canonicalized —
    see _canon_tx_hash (issue #668)."""
    import uuid

    tx_hash = _canon_tx_hash(tx_hash)

    deposit_id = f"deposit_{uuid.uuid4().hex[:8]}"

    conn = _connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO eth_deposits (id, tx_hash, from_address, recipient, amount_eth, amount_ait, status, created_at, deposit_address)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                deposit_id,
                tx_hash,
                from_address,
                recipient,
                amount_eth,
                amount_ait,
                utc_now_iso(),
                deposit_address,
            ),
        )
        conn.commit()
        return deposit_id
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Deposit with tx_hash {tx_hash} already exists") from None
    finally:
        conn.close()


def insert_exchange_prepay_deposit(tx_hash: str, from_address: str, amount_eth: Decimal, tag: str) -> str:
    """Record an exchange-prepay ETH deposit atomically as
    'exchange_prepay' — outside the payout loop's 'pending' vocabulary, so
    it can never be auto-minted. The raw tag the buyer typed stays in
    ``recipient``; the settlement monitor canonicalizes and validates it.
    ``amount_ait`` is 0: no AIT is owed, the credit lands exchange-side."""
    import uuid

    tx_hash = _canon_tx_hash(tx_hash)

    deposit_id = f"deposit_{uuid.uuid4().hex[:8]}"
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO eth_deposits (id, tx_hash, from_address, recipient, amount_eth, amount_ait, status, created_at)
            VALUES (?, ?, ?, ?, ?, '0', 'exchange_prepay', ?)
            """,
            (
                deposit_id,
                tx_hash,
                from_address,
                f"EXCHANGE_DEPOSIT:{tag}",
                amount_eth,
                utc_now_iso(),
            ),
        )
        conn.commit()
        return deposit_id
    except sqlite3.IntegrityError:
        raise ValueError(f"Deposit with tx_hash {tx_hash} already exists") from None
    finally:
        conn.close()


def get_pending_deposits(limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
    """Get pending deposits (bounded — was an unbounded full-table scan, #1408)."""
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at, recipient, ait_tx_hash
        FROM eth_deposits
        WHERE status = 'pending'
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """,
        (limit, offset),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "tx_hash": row[1],
            "from_address": row[2],
            "amount_eth": row[3],
            "amount_ait": row[4],
            "status": row[5],
            "created_at": row[6],
            "verified_at": row[7],
            "completed_at": row[8],
            "recipient": row[9],
            "ait_tx_hash": row[10],
        }
        for row in rows
    ]


# Canonical eth_deposits lifecycle vocabulary (#1795 / #1424 residual):
# the mint path walks pending -> verified -> completed; 'exchange_prepay'
# rows are written by insert_exchange_prepay_deposit and consumed by the
# settlement monitor; 'rejected' is the documented operator-terminal state
# (bridge_routes /deposits filter); 'failed' is the monitor's terminal
# error state (timestamp-free write, see test_coder_c_sweep). Anything
# else is a typo that would park the row outside every worklist — reject
# it here, the only write path for this column.
#
# This table is SHARED with aitbc-bridge-monitor, whose
# BridgeDepositStatus vocabulary adds processing/pending_retry/submitted/
# written_off/funding — all rejected here at write time, and vice versa
# the monitor rejects 'verified'/'rejected' (#1919). The overlap is only
# pending/completed/failed/exchange_prepay. Consequence: a 'verified'
# (or 'pending') row the monitor did not create is invisible to every
# monitor worklist — the monitor's stranded-row detector
# (BRIDGE_STRANDED_DEPOSIT_HOURS) is the alert net, and resolution is
# deliberate (admin write-off / manual-payout / wallet-side completion),
# never an automatic monitor payout — a 'verified' row's wallet-side
# TRANSFER may already have landed.
_ETH_DEPOSIT_STATUSES = frozenset({"pending", "verified", "completed", "exchange_prepay", "rejected", "failed"})


def update_deposit_status(deposit_id: str, status: str, *, expected_statuses: Collection[str] | None = None) -> bool:
    """Update deposit status.

    ``expected_statuses`` is the CAS predicate (#1796): when given, the
    UPDATE only lands while the row still sits in one of those statuses,
    so a stale writer cannot overwrite a state that has already moved on
    (e.g. re-verifying a completed deposit). rowcount 0 -> False.
    """
    if status not in _ETH_DEPOSIT_STATUSES:
        raise ValueError(f"unknown deposit status: {status!r}")
    conn = _connect_db()
    cursor = conn.cursor()

    # Only the status's own timestamp column is stamped: stamping
    # completed_at on a 'pending' reset fabricated a completion time that
    # _normalize_deposit then reported as processed_at (#1452). 'pending'
    # additionally clears a stale completed_at — a re-pended row was never
    # completed. timestamp_field values are hardcoded literals, never
    # caller input; `status` itself is bound as a ? parameter.
    now = utc_now_iso()
    params: tuple[str, ...]
    if status == "verified":
        query = "UPDATE eth_deposits SET status = ?, verified_at = ? WHERE id = ?"  # nosec
        params = (status, now, deposit_id)
    elif status == "completed":
        query = "UPDATE eth_deposits SET status = ?, completed_at = ? WHERE id = ?"  # nosec
        params = (status, now, deposit_id)
    elif status == "pending":
        query = "UPDATE eth_deposits SET status = ?, completed_at = NULL WHERE id = ?"  # nosec
        params = (status, deposit_id)
    else:
        query = "UPDATE eth_deposits SET status = ? WHERE id = ?"  # nosec
        params = (status, deposit_id)
    if expected_statuses:
        expected = tuple(expected_statuses)
        query += f" AND status IN ({', '.join('?' for _ in expected)})"  # nosec
        params = (*params, *expected)
    cursor.execute(query, params)

    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()

    return rows_affected > 0


def update_deposit_tx_hash(deposit_id: str, ait_tx_hash: str, *, expected_statuses: Collection[str] | None = None) -> bool:
    """Record the AIT transaction hash for a completed deposit.

    Same CAS predicate as update_deposit_status (#1796): pass
    ``{"completed"}`` so a delayed writer cannot stamp a hash onto a row
    that has since moved to another state.
    """
    conn = _connect_db()
    cursor = conn.cursor()
    query = "UPDATE eth_deposits SET ait_tx_hash = ? WHERE id = ?"
    params: tuple = (ait_tx_hash, deposit_id)
    if expected_statuses:
        expected = tuple(expected_statuses)
        query += f" AND status IN ({', '.join('?' for _ in expected)})"  # nosec
        params = (*params, *expected)
    cursor.execute(query, params)
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def get_deposit_by_tx_hash(tx_hash: str) -> dict[str, Any] | None:
    """Get deposit by transaction hash."""
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at, recipient, ait_tx_hash
        FROM eth_deposits
        WHERE lower(tx_hash) IN (?, ?)
    """,
        _tx_hash_keys(tx_hash),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "tx_hash": row[1],
        "from_address": row[2],
        "amount_eth": row[3],
        "amount_ait": row[4],
        "status": row[5],
        "created_at": row[6],
        "verified_at": row[7],
        "completed_at": row[8],
        "recipient": row[9],
        "ait_tx_hash": row[10],
    }


def get_deposit_by_id(deposit_id: str) -> dict[str, Any] | None:
    """Get deposit by its local deposit id."""
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at, recipient, ait_tx_hash
        FROM eth_deposits
        WHERE id = ?
    """,
        (deposit_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "tx_hash": row[1],
        "from_address": row[2],
        "amount_eth": row[3],
        "amount_ait": row[4],
        "status": row[5],
        "created_at": row[6],
        "verified_at": row[7],
        "completed_at": row[8],
        "recipient": row[9],
        "ait_tx_hash": row[10],
    }


def get_all_deposits(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Get all deposits with pagination."""
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at, recipient, ait_tx_hash
        FROM eth_deposits
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """,
        (limit, offset),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "tx_hash": row[1],
            "from_address": row[2],
            "amount_eth": row[3],
            "amount_ait": row[4],
            "status": row[5],
            "created_at": row[6],
            "verified_at": row[7],
            "completed_at": row[8],
            "recipient": row[9],
            "ait_tx_hash": row[10],
        }
        for row in rows
    ]


def get_deposits_by_recipient(recipient: str, limit: int = 10) -> list[dict[str, Any]]:
    """Get deposits for a single AIT recipient, newest first.

    Non-enumerable counterpart to get_all_deposits: the caller must already
    know the recipient address, so this can stay public where the full index
    is operator-only. Matching is case-insensitive because recipients arrive
    both checksummed and lowercase depending on how the depositor encoded
    the transaction data field.
    """
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at, recipient, ait_tx_hash
        FROM eth_deposits
        WHERE LOWER(recipient) = LOWER(?)
        ORDER BY created_at DESC
        LIMIT ?
    """,
        (recipient, limit),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "tx_hash": row[1],
            "from_address": row[2],
            "amount_eth": row[3],
            "amount_ait": row[4],
            "status": row[5],
            "created_at": row[6],
            "verified_at": row[7],
            "completed_at": row[8],
            "recipient": row[9],
            "ait_tx_hash": row[10],
        }
        for row in rows
    ]
