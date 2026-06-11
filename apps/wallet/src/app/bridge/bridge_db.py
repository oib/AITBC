"""
ETH-AIT Bridge Database
SQLite database for tracking ETH deposits and AIT minting operations.
"""

import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

DB_PATH = "/var/lib/aitbc/bridge_deposits.db"


def init_db():
    """Initialize the bridge database with required tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eth_deposits (
            id TEXT PRIMARY KEY,
            tx_hash TEXT UNIQUE NOT NULL,
            from_address TEXT NOT NULL,
            amount_eth REAL NOT NULL,
            amount_ait REAL NOT NULL,
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
            eth_usd_price REAL NOT NULL,
            eth_eur_price REAL NOT NULL,
            exchange_rate_usd REAL NOT NULL,
            exchange_rate_eur REAL NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()


def insert_deposit(tx_hash: str, from_address: str, amount_eth: float, amount_ait: float) -> str:
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
            (deposit_id, tx_hash, from_address, amount_eth, amount_ait, datetime.now().isoformat())
        )
        conn.commit()
        return deposit_id
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Deposit with tx_hash {tx_hash} already exists")
    finally:
        conn.close()


def get_pending_deposits() -> List[Dict]:
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
            "created_at": row[6]
        }
        for row in rows
    ]


def update_deposit_status(deposit_id: str, status: str) -> bool:
    """Update deposit status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    timestamp_field = "verified_at" if status == "verified" else "completed_at"
    
    cursor.execute(
        f"""
        UPDATE eth_deposits
        SET status = ?, {timestamp_field} = ?
        WHERE id = ?
        """,
        (status, datetime.now().isoformat(), deposit_id)
    )
    
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    
    return rows_affected > 0


def get_deposit_by_tx_hash(tx_hash: str) -> Optional[Dict]:
    """Get deposit by transaction hash."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at
        FROM eth_deposits
        WHERE tx_hash = ?
    """, (tx_hash,))
    
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
        "completed_at": row[8]
    }


def get_all_deposits(limit: int = 50, offset: int = 0) -> List[Dict]:
    """Get all deposits with pagination."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at
        FROM eth_deposits
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    
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
            "completed_at": row[8]
        }
        for row in rows
    ]


def insert_price_history(eth_usd: float, eth_eur: float, exchange_rate_usd: float, exchange_rate_eur: float):
    """Insert a new price history record."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        """
        INSERT INTO price_history (eth_usd_price, eth_eur_price, exchange_rate_usd, exchange_rate_eur)
        VALUES (?, ?, ?, ?)
        """,
        (eth_usd, eth_eur, exchange_rate_usd, exchange_rate_eur)
    )
    
    conn.commit()
    conn.close()


def get_all_time_average() -> Dict:
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
            "count": result[4]
        }
    
    return None


def cleanup_old_prices(days: int = 30):
    """Clean up price history older than specified days."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        """
        DELETE FROM price_history
        WHERE timestamp < datetime('now', '-{} days')
        """.format(days)
    )
    
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    
    return deleted_count
