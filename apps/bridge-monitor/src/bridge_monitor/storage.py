"""SQLite storage for bridge deposit tracking."""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum

DATA_DIR = os.getenv("DATA_DIR", "/var/lib/aitbc")
DB_PATH = os.path.join(DATA_DIR, "bridge_deposits.db")


class BridgeDepositStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def init_db():
    """Initialize bridge deposits database."""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bridge_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            eth_tx_hash TEXT UNIQUE NOT NULL,
            eth_from_address TEXT NOT NULL,
            eth_amount TEXT NOT NULL,
            ait_recipient TEXT NOT NULL,
            ait_amount TEXT,
            eth_usd_price TEXT,
            ait_usd_price TEXT,
            ait_tx_hash TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            processed_at TEXT,
            error_message TEXT
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_eth_tx_hash ON bridge_deposits(eth_tx_hash)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_status ON bridge_deposits(status)
    """)
    
    conn.commit()
    conn.close()


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_deposit(
    eth_tx_hash: str,
    eth_from_address: str,
    eth_amount: str,
    ait_recipient: str
) -> int:
    """Create a new bridge deposit record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            INSERT INTO bridge_deposits 
            (eth_tx_hash, eth_from_address, eth_amount, ait_recipient, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (eth_tx_hash, eth_from_address, eth_amount, ait_recipient, BridgeDepositStatus.PENDING, datetime.utcnow().isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Transaction already exists
        return None
    finally:
        conn.close()


def update_deposit(
    eth_tx_hash: str,
    ait_amount: Optional[str] = None,
    eth_usd_price: Optional[str] = None,
    ait_usd_price: Optional[str] = None,
    ait_tx_hash: Optional[str] = None,
    status: Optional[BridgeDepositStatus] = None,
    error_message: Optional[str] = None
) -> bool:
    """Update bridge deposit record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if ait_amount is not None:
        updates.append("ait_amount = ?")
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
    
    if status is not None:
        updates.append("processed_at = ?")
        params.append(datetime.utcnow().isoformat())
    
    params.append(eth_tx_hash)
    
    if updates:
        query = f"UPDATE bridge_deposits SET {', '.join(updates)} WHERE eth_tx_hash = ?"
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False


def get_deposit(eth_tx_hash: str) -> Optional[Dict]:
    """Get deposit by transaction hash."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM bridge_deposits WHERE eth_tx_hash = ?", (eth_tx_hash,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def get_deposits(
    status: Optional[BridgeDepositStatus] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict]:
    """Get deposits with optional status filter."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute(
            "SELECT * FROM bridge_deposits WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status.value, limit, offset)
        )
    else:
        cursor.execute(
            "SELECT * FROM bridge_deposits ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def count_deposits(status: Optional[BridgeDepositStatus] = None) -> int:
    """Count deposits with optional status filter."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute("SELECT COUNT(*) FROM bridge_deposits WHERE status = ?", (status.value,))
    else:
        cursor.execute("SELECT COUNT(*) FROM bridge_deposits")
    
    count = cursor.fetchone()[0]
    conn.close()
    
    return count
