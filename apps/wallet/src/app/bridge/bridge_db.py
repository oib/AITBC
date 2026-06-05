"""
ETH-AIT Bridge Database
SQLite database for tracking ETH deposits and AIT minting operations.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict

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
