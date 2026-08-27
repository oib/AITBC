"""
ETH-AIT Bridge Database
SQLite database for tracking ETH deposits and AIT minting operations.
"""

import os
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Any

DB_PATH = "/var/lib/aitbc/bridge_deposits.db"


def init_db() -> None:
    """Initialize the bridge database with required tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eth_deposits (
            id TEXT PRIMARY KEY,
            tx_hash TEXT UNIQUE NOT NULL,
            from_address TEXT NOT NULL,
            amount_eth NUMERIC NOT NULL,
            amount_ait NUMERIC NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            verified_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            eth_usd_price NUMERIC NOT NULL,
            eth_eur_price NUMERIC NOT NULL,
            exchange_rate_usd NUMERIC NOT NULL,
            exchange_rate_eur NUMERIC NOT NULL
        )
    """)

    # Migrate existing tables from REAL to NUMERIC column affinity.
    # SQLite doesn't support ALTER COLUMN TYPE, so we recreate the table
    # (standard SQLite migration pattern). Only runs if columns are REAL.
    _migrate_real_to_numeric(conn)

    conn.commit()
    conn.close()


def _migrate_real_to_numeric(conn: sqlite3.Connection) -> None:
    """Migrate eth_deposits and price_history from REAL to NUMERIC affinity."""
    cursor = conn.cursor()

    for table, _cols in [
        ("eth_deposits", ["amount_eth", "amount_ait"]),
        ("price_history", ["eth_usd_price", "eth_eur_price", "exchange_rate_usd", "exchange_rate_eur"]),
    ]:
        # Check if table exists and has REAL columns
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        if not columns:
            continue
        has_real = any(col[2].upper() == "REAL" for col in columns)
        if not has_real:
            continue

        # Recreate table with NUMERIC columns (SQLite migration pattern)
        temp_name = f"_old_{table}"
        cursor.execute(f"ALTER TABLE {table} RENAME TO {temp_name}")

        if table == "eth_deposits":
            cursor.execute("""
                CREATE TABLE eth_deposits (
                    id TEXT PRIMARY KEY,
                    tx_hash TEXT UNIQUE NOT NULL,
                    from_address TEXT NOT NULL,
                    amount_eth NUMERIC NOT NULL,
                    amount_ait NUMERIC NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    verified_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            query = f"INSERT INTO eth_deposits SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at FROM {temp_name}"  # nosec B608 - temp_name is a hardcoded literal table name from this function's own migration list (`table` above), never external input
            cursor.execute(query)
        else:
            cursor.execute("""
                CREATE TABLE price_history (
                    id INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    eth_usd_price NUMERIC NOT NULL,
                    eth_eur_price NUMERIC NOT NULL,
                    exchange_rate_usd NUMERIC NOT NULL,
                    exchange_rate_eur NUMERIC NOT NULL
                )
            """)
            query = f"INSERT INTO price_history SELECT id, timestamp, eth_usd_price, eth_eur_price, exchange_rate_usd, exchange_rate_eur FROM {temp_name}"  # nosec B608 - temp_name is a hardcoded literal table name from this function's own migration list (`table` above), never external input
            cursor.execute(query)
        cursor.execute(f"DROP TABLE {temp_name}")  # nosec B608 - temp_name is a hardcoded literal (see above)


def insert_deposit(tx_hash: str, from_address: str, amount_eth: Decimal, amount_ait: Decimal) -> str:
    """Insert a new deposit record."""
    import uuid

    deposit_id = f"deposit_{uuid.uuid4().hex[:8]}"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO eth_deposits (id, tx_hash, from_address, amount_eth, amount_ait, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (deposit_id, tx_hash, from_address, amount_eth, amount_ait, datetime.now().isoformat()),
        )
        conn.commit()
        return deposit_id
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Deposit with tx_hash {tx_hash} already exists") from None
    finally:
        conn.close()


def get_pending_deposits() -> list[dict[str, Any]]:
    """Get all pending deposits."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at
        FROM eth_deposits
        WHERE status = 'pending'
        ORDER BY created_at DESC
    """)

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
        }
        for row in rows
    ]


def update_deposit_status(deposit_id: str, status: str) -> bool:
    """Update deposit status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # timestamp_field is one of exactly two hardcoded literals below, never
    # derived from caller input -- `status` itself is bound as a ? parameter.
    timestamp_field = "verified_at" if status == "verified" else "completed_at"

    query = f"UPDATE eth_deposits SET status = ?, {timestamp_field} = ? WHERE id = ?"  # nosec B608 - timestamp_field is one of exactly two hardcoded literals above, never caller input
    cursor.execute(
        query,
        (status, datetime.now().isoformat(), deposit_id),
    )

    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()

    return rows_affected > 0


def get_deposit_by_tx_hash(tx_hash: str) -> dict[str, Any] | None:
    """Get deposit by transaction hash."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at
        FROM eth_deposits
        WHERE tx_hash = ?
    """,
        (tx_hash,),
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
    }


def get_deposit_by_id(deposit_id: str) -> dict[str, Any] | None:
    """Get deposit by its local deposit id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at
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
    }


def get_all_deposits(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Get all deposits with pagination."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at
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
        }
        for row in rows
    ]


def insert_price_history(eth_usd: Decimal, eth_eur: Decimal, exchange_rate_usd: Decimal, exchange_rate_eur: Decimal) -> None:
    """Insert a new price history record."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO price_history (eth_usd_price, eth_eur_price, exchange_rate_usd, exchange_rate_eur)
        VALUES (?, ?, ?, ?)
        """,
        (eth_usd, eth_eur, exchange_rate_usd, exchange_rate_eur),
    )

    conn.commit()
    conn.close()


def get_all_time_average() -> dict[str, Any] | None:
    """Get all-time average prices from history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            AVG(eth_usd_price) as avg_usd,
            AVG(eth_eur_price) as avg_eur,
            AVG(exchange_rate_usd) as avg_rate_usd,
            AVG(exchange_rate_eur) as avg_rate_eur,
            COUNT(*) as count
        FROM price_history
    """)

    result = cursor.fetchone()
    conn.close()

    if result and result[4] > 0:  # count > 0
        return {
            "eth_usd_avg": result[0],
            "eth_eur_avg": result[1],
            "exchange_rate_usd_avg": result[2],
            "exchange_rate_eur_avg": result[3],
            "count": result[4],
        }

    return None


def cleanup_old_prices(days: int = 30) -> int:
    """Clean up price history older than specified days."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM price_history
        WHERE timestamp < datetime('now', ?)
        """,
        (f"-{int(days)} days",),
    )

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted_count
