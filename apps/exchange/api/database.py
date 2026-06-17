"""
Database setup and initialization for exchange API.
"""

import os
import random
import sqlite3
from datetime import UTC, datetime, timedelta

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR

logger = get_logger(__name__)


def get_db_path():
    """Get database path and ensure directory exists"""
    db_path = os.getenv("EXCHANGE_DATABASE_URL", f"sqlite:///{DATA_DIR}/data/exchange/exchange.db").replace("sqlite://///", "")

    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    return db_path


def init_db():
    """Initialize SQLite database"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),
            amount REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            filled REAL DEFAULT 0,
            remaining REAL NOT NULL,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_address TEXT,
            tx_hash TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_offers (
            id TEXT PRIMARY KEY,
            item TEXT NOT NULL,
            item_type TEXT NOT NULL,
            price REAL NOT NULL,
            wallet TEXT,
            status TEXT DEFAULT 'active',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_orders (
            id TEXT PRIMARY KEY,
            order_type TEXT NOT NULL,
            item TEXT NOT NULL,
            price REAL NOT NULL,
            wallet TEXT,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN user_address TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN tx_hash TEXT")
    except Exception:
        pass

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")


def create_mock_trades():
    """Create some mock trades"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM trades")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    now = datetime.now(UTC)
    for _i in range(20):
        amount = random.uniform(10, 500)
        price = random.uniform(0.000009, 0.000012)
        total = amount * price
        created_at = now - timedelta(minutes=random.randint(0, 60))

        cursor.execute(
            """
            INSERT INTO trades (amount, price, total, created_at)
            VALUES (?, ?, ?, ?)
        """,
            (amount, price, total, created_at),
        )

    conn.commit()
    conn.close()
    logger.info("Mock trades created")
