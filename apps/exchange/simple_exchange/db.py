"""Database setup for the AITBC Trade Exchange (FastAPI backend).

Monetary columns use TEXT storage (Decimal-as-string) for exact arithmetic,
matching the Numeric(18, 8) approach in the FastAPI exchange_api.py models.
This prevents float rounding drift in order amounts, prices, and totals.

For existing databases with REAL columns, ``init_db()`` automatically
migrates them to TEXT via table rebuild.
"""

import os
import sqlite3

from aitbc.constants import DATA_DIR


def get_db_path():
    """Get database path and ensure directory exists.

    Supports both ``sqlite:///path`` URI format and raw filesystem paths.
    The ``EXCHANGE_DATABASE_URL`` env var overrides the default location.
    """
    raw = os.getenv("EXCHANGE_DATABASE_URL", f"sqlite:///{DATA_DIR}/data/exchange/exchange.db")
    # Strip sqlite: prefix and any number of slashes
    if raw.startswith("sqlite:"):
        raw = raw[len("sqlite:") :]
    while raw.startswith("/"):
        raw = raw[1:]
    # Reconstruct as absolute path under DATA_DIR
    db_path = "/" + raw

    # Create directory if it doesn't exist
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    return db_path


# Schema definitions — monetary columns are TEXT (Decimal-as-string) for exact arithmetic.
# Using TEXT instead of REAL prevents float rounding drift (e.g., 0.1 * 0.3 = 0.03, not 0.030000000000000002).

_TRADES_SCHEMA = """
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount TEXT NOT NULL,
        price TEXT NOT NULL,
        total TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

_ORDERS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),
        amount TEXT NOT NULL,
        price TEXT NOT NULL,
        total TEXT NOT NULL,
        filled TEXT DEFAULT '0',
        remaining TEXT NOT NULL,
        status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_address TEXT,
        tx_hash TEXT
    )
"""

_MARKETPLACE_OFFERS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS marketplace_offers (
        id TEXT PRIMARY KEY,
        item TEXT NOT NULL,
        item_type TEXT NOT NULL,
        price TEXT NOT NULL,
        wallet TEXT,
        status TEXT DEFAULT 'active',
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

_MARKETPLACE_ORDERS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS marketplace_orders (
        id TEXT PRIMARY KEY,
        order_type TEXT NOT NULL,
        item TEXT NOT NULL,
        price TEXT NOT NULL,
        wallet TEXT,
        status TEXT DEFAULT 'open',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""


def _get_column_types(cursor, table_name):
    """Return {column_name: declared_type} for a table."""
    if not _is_valid_identifier(table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1]: row[2].upper() for row in cursor.fetchall()}


# Whitelist of allowed table names for migration operations.
_ALLOWED_TABLES = frozenset({"trades", "orders", "marketplace_offers", "marketplace_orders"})


def _is_valid_identifier(name: str) -> bool:
    """Validate that a string is a safe SQL identifier (table/column name)."""
    if not name or len(name) > 128:
        return False
    return name.replace("_", "").isalnum() and name[0].isalpha()


def _migrate_real_to_text(conn, cursor, table_name, schema_sql, monetary_columns):
    """Migrate a table's REAL columns to TEXT via table rebuild.

    SQLite doesn't support ALTER COLUMN, so we:
    1. Rename the old table
    2. Create the new table with TEXT columns
    3. Copy data, casting monetary columns to TEXT
    4. Drop the old table
    """
    if table_name not in _ALLOWED_TABLES:
        raise ValueError(f"Table '{table_name}' not in allowed list for migration")
    cols = _get_column_types(cursor, table_name)
    needs_migration = any(cols.get(col) == "REAL" for col in monetary_columns if col in cols)
    if not needs_migration:
        return False

    old_name = f"{table_name}_old_real"
    # Clean up any leftover temp table from a previous failed migration
    cursor.execute(f"DROP TABLE IF EXISTS {old_name}")

    # Rename old table
    cursor.execute(f"ALTER TABLE {table_name} RENAME TO {old_name}")

    # Create new table with TEXT columns
    cursor.execute(schema_sql)

    # Get column names from old table
    cursor.execute(f"PRAGMA table_info({old_name})")
    old_cols = [row[1] for row in cursor.fetchall()]

    # Build SELECT with CAST for monetary columns
    select_parts = []
    for col in old_cols:
        if col in monetary_columns:
            select_parts.append(f"CAST({col} AS TEXT) AS {col}")
        else:
            select_parts.append(col)
    col_list = ", ".join(old_cols)
    select_list = ", ".join(select_parts)

    cursor.execute(f"INSERT INTO {table_name} ({col_list}) SELECT {select_list} FROM {old_name}")  # nosec B608 - table_name validated against _ALLOWED_TABLES above; old_name/col_list derive from it and the DB's own schema, never external input
    cursor.execute(f"DROP TABLE {old_name}")
    return True


def init_db():
    """Initialize SQLite database.

    Creates tables with TEXT monetary columns (exact Decimal arithmetic).
    For existing databases with REAL columns, automatically migrates them
    to TEXT via table rebuild.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables (IF NOT EXISTS — won't alter existing tables)
    cursor.execute(_TRADES_SCHEMA)
    cursor.execute(_ORDERS_SCHEMA)
    cursor.execute(_MARKETPLACE_OFFERS_SCHEMA)
    cursor.execute(_MARKETPLACE_ORDERS_SCHEMA)

    # Add columns if they don't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN user_address TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN tx_hash TEXT")
    except Exception:
        pass

    # B2 migration: convert REAL columns to TEXT for exact decimal storage
    # Only runs if existing tables have REAL columns (pre-v0.10.3 databases)
    migrations = [
        ("trades", _TRADES_SCHEMA, ["amount", "price", "total"]),
        ("orders", _ORDERS_SCHEMA, ["amount", "price", "total", "filled", "remaining"]),
        ("marketplace_offers", _MARKETPLACE_OFFERS_SCHEMA, ["price"]),
        ("marketplace_orders", _MARKETPLACE_ORDERS_SCHEMA, ["price"]),
    ]
    for table, schema, money_cols in migrations:
        try:
            migrated = _migrate_real_to_text(conn, cursor, table, schema, money_cols)
            if migrated:
                import logging

                logging.getLogger(__name__).info("Migrated %s REAL columns to TEXT", table)
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("Could not migrate %s: %s", table, e)

    conn.commit()
    conn.close()
