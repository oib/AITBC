"""SQLite storage for bridge deposit tracking.

Writes into ``eth_deposits`` — the same table the wallet service reads for
/v1/bridge/* routes and the public website. Column names differ between the
two services' vocabularies, so every query aliases the wallet schema back to
the monitor's field names; callers see one consistent dict shape.
"""

import os
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

DATA_DIR = os.getenv("DATA_DIR", "/var/lib/aitbc")
DB_PATH = os.path.join(DATA_DIR, "bridge_deposits.db")


class BridgeDepositStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PENDING_RETRY = "pending_retry"
    COMPLETED = "completed"
    FAILED = "failed"


# SELECT projection shared by every read: wallet column -> monitor key.
_DEPOSIT_SELECT = """
    SELECT id,
           tx_hash        AS eth_tx_hash,
           from_address   AS eth_from_address,
           amount_eth     AS eth_amount,
           recipient      AS ait_recipient,
           amount_ait     AS ait_amount,
           eth_usd_price,
           ait_usd_price,
           ait_tx_hash,
           status,
           created_at,
           completed_at   AS processed_at,
           verified_at,
           error_message,
           retry_count,
           next_retry_at
    FROM eth_deposits
"""


def init_db() -> None:
    """Initialize bridge deposits database."""
    os.makedirs(DATA_DIR, exist_ok=True)

    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.cursor()

        # Full column set — identical to wallet_app.bridge.bridge_db.init_db.
        # The monitor's extra lifecycle columns (error_message, retry fields,
        # usd prices) live on the shared table so either service can migrate
        # an older DB forward; the wallet runs the same ALTERs on its side.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS eth_deposits (
                id TEXT PRIMARY KEY,
                tx_hash TEXT UNIQUE NOT NULL,
                from_address TEXT NOT NULL,
                recipient TEXT,
                amount_eth NUMERIC NOT NULL,
                amount_ait NUMERIC NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                ait_tx_hash TEXT,
                eth_usd_price TEXT,
                ait_usd_price TEXT,
                error_message TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                next_retry_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        for column, col_type in [
            ("eth_usd_price", "TEXT"),
            ("ait_usd_price", "TEXT"),
            ("error_message", "TEXT"),
            ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
            ("next_retry_at", "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE eth_deposits ADD COLUMN {column} {col_type}")
            except sqlite3.OperationalError:
                pass  # column already present

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bridge_cursor (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_eth_deposits_tx_hash ON eth_deposits(tx_hash)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_eth_deposits_status ON eth_deposits(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_eth_deposits_next_retry ON eth_deposits(next_retry_at)
        """)

        conn.commit()


def _db_connection() -> sqlite3.Connection:
    """Get a fresh database connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_deposit(eth_tx_hash: str, eth_from_address: str, eth_amount: str, ait_recipient: str) -> str | None:
    """Create a new bridge deposit record.

    amount_ait starts at '0' — the oracle-priced value lands via
    update_deposit once crediting is attempted. Returns the generated id,
    or None when the tx hash is already recorded.
    """
    deposit_id = f"deposit_{uuid.uuid4().hex[:8]}"
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO eth_deposits
                (id, tx_hash, from_address, recipient, amount_eth, amount_ait, status, created_at)
                VALUES (?, ?, ?, ?, ?, '0', ?, ?)
                """,
                (
                    deposit_id,
                    eth_tx_hash,
                    eth_from_address,
                    ait_recipient,
                    eth_amount,
                    BridgeDepositStatus.PENDING,
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()
            return deposit_id
        except sqlite3.IntegrityError:
            # Transaction already exists
            return None


def update_deposit(
    eth_tx_hash: str,
    ait_amount: str | None = None,
    eth_usd_price: str | None = None,
    ait_usd_price: str | None = None,
    ait_tx_hash: str | None = None,
    status: BridgeDepositStatus | None = None,
    error_message: str | None = None,
    retry_count: int | None = None,
    next_retry_at: str | None = None,
) -> bool:
    """Update bridge deposit record."""
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()

        updates = []
        params: list[Any] = []

        if ait_amount is not None:
            updates.append("amount_ait = ?")
            params.append(ait_amount)
        if eth_usd_price is not None:
            updates.append("eth_usd_price = ?")
            params.append(eth_usd_price)
        if ait_usd_price is not None:
            updates.append("ait_usd_price = ?")
            params.append(ait_usd_price)
        if ait_tx_hash is not None:
            updates.append("ait_tx_hash = ?")
            params.append(ait_tx_hash)
        if status is not None:
            updates.append("status = ?")
            params.append(status.value)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if retry_count is not None:
            updates.append("retry_count = ?")
            params.append(retry_count)
        if next_retry_at is not None:
            updates.append("next_retry_at = ?")
            params.append(next_retry_at)

        if status is not None and status in (BridgeDepositStatus.COMPLETED, BridgeDepositStatus.FAILED):
            updates.append("completed_at = ?")
            params.append(datetime.now(UTC).isoformat())

        params.append(eth_tx_hash)

        if updates:
            query = f"UPDATE eth_deposits SET {', '.join(updates)} WHERE tx_hash = ?"  # nosec B608 - every `updates` entry is a hardcoded "column = ?" literal above; values are bound via params
            cursor.execute(query, params)
            conn.commit()
            return True

        return False


def get_deposit(eth_tx_hash: str) -> dict[str, Any] | None:
    """Get deposit by transaction hash."""
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()

        cursor.execute(f"{_DEPOSIT_SELECT} WHERE tx_hash = ?", (eth_tx_hash,))
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None


def get_deposits(status: BridgeDepositStatus | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Get deposits with optional status filter."""
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()

        if status:
            cursor.execute(
                f"{_DEPOSIT_SELECT} WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status.value, limit, offset),
            )
        else:
            cursor.execute(f"{_DEPOSIT_SELECT} ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))

        rows = cursor.fetchall()

        return [dict(row) for row in rows]


def count_deposits(status: BridgeDepositStatus | None = None) -> int:
    """Count deposits with optional status filter."""
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()

        if status:
            cursor.execute("SELECT COUNT(*) FROM eth_deposits WHERE status = ?", (status.value,))
        else:
            cursor.execute("SELECT COUNT(*) FROM eth_deposits")

        count: int = cursor.fetchone()[0]

        return count


def get_deposits_for_retry(now_iso: str | None = None) -> list[dict[str, Any]]:
    """Get deposits in PENDING_RETRY status whose next_retry_at has passed."""
    if now_iso is None:
        now_iso = datetime.now(UTC).isoformat()
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"{_DEPOSIT_SELECT} WHERE status = ? AND (next_retry_at IS NULL OR next_retry_at <= ?) ORDER BY created_at ASC",
            (BridgeDepositStatus.PENDING_RETRY.value, now_iso),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_cursor(key: str = "last_processed_block") -> int | None:
    """Get the persisted block cursor."""
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM bridge_cursor WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None


def set_cursor(key: str, value: int) -> None:
    """Set the persisted block cursor."""
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bridge_cursor (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
        )
        conn.commit()
