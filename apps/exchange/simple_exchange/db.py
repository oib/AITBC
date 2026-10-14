"""Database setup for the AITBC Trade Exchange (FastAPI backend).

Monetary columns use TEXT storage (Decimal-as-string) for exact arithmetic,
matching the Numeric(18, 8) approach in the FastAPI exchange_api.py models.
This prevents float rounding drift in order amounts, prices, and totals.

For existing databases with REAL columns, ``init_db()`` automatically
migrates them to TEXT via table rebuild.
"""

import os
import sqlite3
from decimal import Decimal, InvalidOperation

from aitbc.constants import DATA_DIR

# Fixed-point representation for SQL comparisons.
#
# Monetary columns keep their TEXT (Decimal-as-string) values as the canonical
# API/display format, but TEXT cannot be compared numerically: '10' < '2'
# lexically, so order matching could fill a buy limited to 2 against a sell
# priced 10, and miss a sell priced 2 for a buy limited to 10. Each monetary
# column on ``orders`` therefore carries a parallel INTEGER column holding the
# value in ticks of ``TICKS_PER_UNIT`` (8 decimal places). All SQL comparisons
# and ORDER BY clauses run on tick columns; TEXT columns are written alongside
# and remain exact.
#
# Only ``orders`` gets tick columns: it is the only table whose monetary values
# appear in SQL predicates or ordering. ``trades``, ``market_offers`` and
# ``market_orders`` are append/read records ordered by created_at — and a
# trade total (qty * price) can legitimately carry more than 8 decimals, which
# TEXT stores exactly and an 8dp tick column could not.
TICKS_PER_UNIT = 100_000_000
TICK_DECIMAL_PLACES = 8
_INT64_MAX = (2**63) - 1


def to_ticks(value: Decimal) -> int:
    """Convert a Decimal to integer ticks — fail closed, never round.

    Raises ValueError for non-finite values, values with more than
    TICK_DECIMAL_PLACES decimals, or magnitudes that overflow int64.
    """
    if not value.is_finite():
        raise ValueError("monetary value must be finite")
    scaled = value * TICKS_PER_UNIT
    integral = scaled.to_integral_exact()
    if scaled != integral:
        raise ValueError(f"monetary value has more than {TICK_DECIMAL_PLACES} decimal places: {value}")
    ticks = int(integral)
    if abs(ticks) > _INT64_MAX:
        raise ValueError("monetary value exceeds int64 tick range")
    return ticks


def ticks_to_decimal(ticks: int) -> Decimal:
    """Convert integer ticks back to the exact Decimal value."""
    return (Decimal(ticks) / TICKS_PER_UNIT).normalize()


class TickMigrationError(RuntimeError):
    """Monetary values that cannot be represented exactly as ticks.

    Carries the offending (table, row_id, column, raw_value) rows so the
    operator can repair them; the migration commits nothing on failure.
    """

    def __init__(self, failures: list[tuple[str, object, str, str]]):
        self.failures = failures
        preview = "; ".join(f"{t}#{rid}.{col}={val!r}" for t, rid, col, val in failures[:20])
        super().__init__(
            f"{len(failures)} value(s) not representable at {TICK_DECIMAL_PLACES} decimal places: {preview}"
            + (" ..." if len(failures) > 20 else "")
        )


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

# Mirrored settlement vocabulary written onto trades rows by the internal
# endpoint (NULL = settlement not started / phase 3 off). The authoritative
# machine lives in the wallet ledger's exchange_settlements table; these
# values exist for the tape + the B13 join and are write-once per field.
_SETTLEMENT_STATES = (
    "locked",
    "releasing",
    "released",
    "settling",
    "refunding",
    "refund_pending",
    "needs_review",
    "needs_review_release",
    "needs_review_sweep",
    "queued_reserve",
    "queued_fee_settle",
    "queued_fee_refund",
    "settled",
    "refunded",
    "failed",
)
_SETTLEMENT_STATES_SQL = ", ".join(f"'{s}'" for s in _SETTLEMENT_STATES)

_TRADES_SCHEMA = f"""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount TEXT NOT NULL,
        price TEXT NOT NULL,
        total TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        buyer_address TEXT,
        seller_address TEXT,
        fee_ait TEXT,
        buy_order_id INTEGER,
        sell_order_id INTEGER,
        settlement_state TEXT CHECK(settlement_state IN ({_SETTLEMENT_STATES_SQL})),
        settlement_eth_tx_hash TEXT,
        settlement_ait_tx_hash TEXT,
        settlement_fee_tx_hash TEXT
    )
"""

# Phase-2 order state (ETH-8 design): 'expired' joins the CHECK via a table
# rebuild migration below — a CHECK constraint cannot be ALTERed in place.
_ORDERS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),
        amount TEXT NOT NULL,
        price TEXT NOT NULL,
        total TEXT NOT NULL,
        filled TEXT DEFAULT '0',
        remaining TEXT NOT NULL,
        status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled', 'expired')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_address TEXT,
        tx_hash TEXT,
        amount_ticks INTEGER CHECK(amount_ticks >= 0),
        price_ticks INTEGER CHECK(price_ticks >= 0),
        filled_ticks INTEGER DEFAULT 0 CHECK(filled_ticks >= 0),
        remaining_ticks INTEGER CHECK(remaining_ticks >= 0),
        signature TEXT,
        envelope_hash TEXT,
        account_nonce INTEGER,
        expiry_height INTEGER,
        funded_state TEXT NOT NULL DEFAULT 'unfunded'
            CHECK(funded_state IN ('unfunded', 'funded', 'backing_expired')),
        cancelled_at TIMESTAMP,
        backing_tx_hash TEXT,
        locked_ticks INTEGER CHECK(locked_ticks >= 0),
        seller_eth_address TEXT,
        funded_at TIMESTAMP
    )
"""

# ETH-8 phase 2: the participants board. Fleet addresses are seeded from the
# CLI's DEFAULT_WALLETS table (the label table is the single source of truth);
# a seeded row becomes 'registered' when the node claims it with a signed
# registration envelope. registered_tx stores the claim envelope's keccak
# hash — phase 2 registration is application-layer, not a chain tx.
_NODE_REGISTRY_SCHEMA = """
    CREATE TABLE IF NOT EXISTS node_registry (
        address TEXT PRIMARY KEY,
        label TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'seeded' CHECK(status IN ('seeded', 'registered', 'suspended')),
        registered_tx TEXT,
        registered_at TIMESTAMP,
        eth_address TEXT,
        eth_address_set_at TIMESTAMP
    )
"""

# Per-address exchange-scoped counter (ETH-8 design section 1: explicitly NOT
# the chain nonce — an order is not a chain tx). Every signed envelope
# (register, place, cancel) must carry account_nonce equal to next_nonce;
# a successful request advances it inside the same transaction.
_ORDER_NONCES_SCHEMA = """
    CREATE TABLE IF NOT EXISTS order_nonces (
        address TEXT PRIMARY KEY,
        next_nonce INTEGER NOT NULL DEFAULT 0 CHECK(next_nonce >= 0)
    )
"""

_MARKET_OFFERS_SCHEMA = """
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

_MARKET_ORDERS_SCHEMA = """
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

# ── ETH-8 phase 3 (dark): funded settlement ──────────────────────────────
# The prepaid ledger is a pair of tables so invariants are structural, not
# conventional: a deposit can never be credited twice (tx_hash UNIQUE) and an
# order can never carry two debits (order_id UNIQUE). Balance =
# Σdeposits − Σ(debits where state != 'refunded'); reserved = debits 'open'.
# 'consume' is a state transition on the debit row, not a new money row.
_PREPAID_DEPOSITS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS prepaid_deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_address TEXT NOT NULL,
        amount_eth TEXT NOT NULL,
        eth_tx_hash TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

_PREPAID_DEBITS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS prepaid_debits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_address TEXT NOT NULL,
        order_id INTEGER UNIQUE NOT NULL,
        amount_eth TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'open' CHECK(state IN ('open', 'consumed', 'refunded')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        closed_at TIMESTAMP
    )
"""

# Every exchange_set_payout claim is appended here — the registry row keeps
# only the current address; this table is the change history (old address +
# when it was replaced + the signed envelope hash that authorized it).
_PAYOUT_AUDIT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS payout_address_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address TEXT NOT NULL,
        old_eth_address TEXT,
        new_eth_address TEXT NOT NULL,
        envelope_hash TEXT NOT NULL,
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


# TEXT monetary column -> INTEGER tick column, per table. Only `orders` is
# listed: it is the sole table whose money values appear in SQL predicates or
# ORDER BY (matching + order book). trades/market_* are append/read
# records ordered by created_at and keep exact TEXT only. `total` keeps no
# tick column either: amount*price can legitimately exceed 8 decimals.
_TICK_COLUMNS: dict[str, dict[str, str]] = {
    "orders": {
        "amount": "amount_ticks",
        "price": "price_ticks",
        "filled": "filled_ticks",
        "remaining": "remaining_ticks",
    },
}


def _migrate_add_tick_columns(cursor) -> None:
    """Add and backfill INTEGER tick columns for the orders TEXT columns.

    Two properties matter here:

    - The backfill is NULL-driven, not column-presence-driven. sqlite3
      autocommits DDL when no transaction is open, so a migration that fails
      after ALTER TABLE leaves the columns present but empty; checking column
      presence alone would then skip the backfill forever. Selecting rows with
      a NULL tick cell makes re-runs resume correctly.
    - Values are converted in Python — never SQL CAST, which silently
      truncates — and any value not exactly representable at
      TICK_DECIMAL_PLACES decimals aborts the migration via
      TickMigrationError. The caller wraps this in a transaction and rolls
      back on failure.
    """
    for table, columns in _TICK_COLUMNS.items():
        if table not in _ALLOWED_TABLES:
            raise ValueError(f"Table '{table}' not in allowed list for migration")
        existing = _get_column_types(cursor, table)
        if not existing:
            continue
        _add_missing_tick_columns(cursor, table, columns, existing)
        _backfill_tick_columns(cursor, table, columns)


def _add_missing_tick_columns(cursor, table: str, columns: dict, existing: dict) -> None:
    for tick_col in (tick for tick in columns.values() if tick not in existing):
        if not _is_valid_identifier(tick_col):
            raise ValueError(f"Invalid column name: {tick_col}")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {tick_col} INTEGER CHECK({tick_col} >= 0)")


def _backfill_tick_columns(cursor, table: str, columns: dict) -> None:
    """Convert rows with a NULL tick cell to fixed-point integers.

    Fail-closed: any value not representable at TICK_DECIMAL_PLACES aborts the
    migration via TickMigrationError before a single UPDATE is issued.
    """
    tick_cols = list(columns.values())
    null_filter = " OR ".join(f"{tick} IS NULL" for tick in tick_cols)
    src_cols = list(columns)
    # all identifiers come from the hardcoded _TICK_COLUMNS map, not input
    cursor.execute(f"SELECT id, {', '.join(src_cols)} FROM {table} WHERE {null_filter}")  # nosec B608
    failures: list[tuple[str, object, str, str]] = []
    backfill: list[tuple[object, dict[str, int]]] = []
    for row in cursor.fetchall():
        row_id = row[0]
        values: dict[str, int] = {}
        for i, src in enumerate(src_cols):
            raw = row[1 + i]
            try:
                values[columns[src]] = to_ticks(Decimal(str(raw)))
            except (InvalidOperation, ValueError):
                failures.append((table, row_id, src, str(raw)))
        backfill.append((row_id, values))
    if failures:
        raise TickMigrationError(failures)
    for row_id, values in backfill:
        assignments = ", ".join(f"{tick_col} = ?" for tick_col in values)
        # table/tick columns come from _TICK_COLUMNS; only values are bound
        cursor.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*values.values(), row_id))  # nosec B608


def _orders_check_allows_expired(cursor) -> bool:
    """Whether the live orders table's status CHECK already accepts 'expired'."""
    row = cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'").fetchone()
    return bool(row and row[0] and "'expired'" in row[0])


def _migrate_orders_status_check(cursor) -> bool:
    """Widen ``orders.status`` CHECK to include 'expired' via table rebuild.

    SQLite cannot ALTER a CHECK constraint, so this follows the same
    rename-recreate-copy pattern as ``_migrate_real_to_text``. Every existing
    row is copied verbatim — the migration only widens what *new* rows may
    say; no stored value changes. Caller wraps this in BEGIN IMMEDIATE.
    """
    row = cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'").fetchone()
    if row is None or _orders_check_allows_expired(cursor):
        return False

    old_name = "orders_old_check"
    cursor.execute(f"DROP TABLE IF EXISTS {old_name}")
    cursor.execute(f"ALTER TABLE orders RENAME TO {old_name}")
    cursor.execute(_ORDERS_SCHEMA)

    # Copy only columns present in both schemas (the new schema is a superset;
    # columns absent from the old table take their declared defaults).
    old_cols = [r[1] for r in cursor.execute(f"PRAGMA table_info({old_name})").fetchall()]
    new_cols = {r[1] for r in cursor.execute("PRAGMA table_info(orders)").fetchall()}
    shared = [c for c in old_cols if c in new_cols]
    col_list = ", ".join(shared)
    cursor.execute(f"INSERT INTO orders ({col_list}) SELECT {col_list} FROM {old_name}")  # nosec B608 - identifiers come from PRAGMA on the fixed 'orders' table
    cursor.execute(f"DROP TABLE {old_name}")
    return True


def _seed_node_registry(cursor) -> int:
    """Seed node_registry with the fleet wallets from DEFAULT_WALLETS.

    The CLI's label table (``cli/aitbc_cli/commands/eth.py``) is the single
    source of truth for fleet name -> AIT address (ETH-8 design section 4).
    Seeded rows are claims waiting to happen: a node becomes 'registered'
    only by signing a registration envelope for its seeded address+label.

    Best-effort: a deployment without the CLI tree on sys.path skips seeding
    (registration then starts from an empty board) rather than failing init.
    """
    try:
        import sys
        from pathlib import Path

        repo_root = str(Path(__file__).resolve().parents[3])
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from cli.aitbc_cli.commands.eth import DEFAULT_WALLETS
    except (ImportError, AttributeError) as e:
        import logging

        logging.getLogger(__name__).warning("node_registry seed skipped (DEFAULT_WALLETS unavailable): %s", e)
        return 0

    seeded = 0
    for label, address in DEFAULT_WALLETS:
        cursor.execute(
            "INSERT OR IGNORE INTO node_registry (address, label, status) VALUES (?, ?, 'seeded')",
            (address, label),
        )
        seeded += cursor.rowcount
    return seeded


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
    cursor.execute(_MARKET_OFFERS_SCHEMA)
    cursor.execute(_MARKET_ORDERS_SCHEMA)
    cursor.execute(_NODE_REGISTRY_SCHEMA)
    cursor.execute(_ORDER_NONCES_SCHEMA)
    cursor.execute(_PREPAID_DEPOSITS_SCHEMA)
    cursor.execute(_PREPAID_DEBITS_SCHEMA)
    cursor.execute(_PAYOUT_AUDIT_SCHEMA)

    # Add columns if they don't exist (for existing databases)
    _order_columns = [
        "user_address TEXT",
        "tx_hash TEXT",
        "signature TEXT",
        "envelope_hash TEXT",
        "account_nonce INTEGER",
        "expiry_height INTEGER",
        "funded_state TEXT NOT NULL DEFAULT 'unfunded' CHECK(funded_state IN ('unfunded', 'funded', 'backing_expired'))",
        "cancelled_at TIMESTAMP",
        # ETH-8 phase 3 (dark): funding proof + payout snapshot. NULL on all
        # phase-2 rows; written only when EXCHANGE_SETTLEMENT_ENABLED is on.
        "backing_tx_hash TEXT",
        "locked_ticks INTEGER CHECK(locked_ticks >= 0)",
        "seller_eth_address TEXT",
        "funded_at TIMESTAMP",
    ]
    for column_def in _order_columns:
        try:
            cursor.execute(f"ALTER TABLE orders ADD COLUMN {column_def}")  # nosec B608 - column definitions are the hardcoded list above
        except Exception:
            pass

    _trade_columns = [
        "buyer_address TEXT",
        "seller_address TEXT",
        "fee_ait TEXT",
        # ETH-8 phase 3 (dark): order linkage + mirrored settlement state.
        "buy_order_id INTEGER",
        "sell_order_id INTEGER",
        f"settlement_state TEXT CHECK(settlement_state IN ({_SETTLEMENT_STATES_SQL}))",
        "settlement_eth_tx_hash TEXT",
        "settlement_ait_tx_hash TEXT",
        "settlement_fee_tx_hash TEXT",
    ]
    for column_def in _trade_columns:
        try:
            cursor.execute(f"ALTER TABLE trades ADD COLUMN {column_def}")  # nosec B608 - hardcoded list
        except Exception:
            pass

    # ETH-8 phase 3 (dark): the node's signed payout address (set via the
    # exchange_set_payout verb) and when it was claimed. History lives in
    # payout_address_audit; NULL means the node never set one.
    _registry_columns = [
        "eth_address TEXT",
        "eth_address_set_at TIMESTAMP",
    ]
    for column_def in _registry_columns:
        try:
            cursor.execute(f"ALTER TABLE node_registry ADD COLUMN {column_def}")  # nosec B608 - hardcoded list
        except Exception:
            pass

    # B2 migration: convert REAL columns to TEXT for exact decimal storage
    # Only runs if existing tables have REAL columns (pre-v0.10.3 databases)
    migrations = [
        ("trades", _TRADES_SCHEMA, ["amount", "price", "total"]),
        ("orders", _ORDERS_SCHEMA, ["amount", "price", "total", "filled", "remaining"]),
        ("marketplace_offers", _MARKET_OFFERS_SCHEMA, ["price"]),
        ("marketplace_orders", _MARKET_ORDERS_SCHEMA, ["price"]),
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

    # Tick columns: added/backfilled fail-closed inside an explicit
    # transaction so ALTER + backfill commit or roll back together. A value
    # that cannot be represented exactly at 8 decimals aborts startup —
    # serving a book that matches lexically is worse than not serving one.
    # Run the read-only preflight script
    # (scripts/ops/exchange-ticks-preflight.py) before deploy.
    conn.commit()  # settle whatever implicit txn the migrations above opened
    try:
        conn.execute("BEGIN IMMEDIATE")
        # 'expired' joins orders.status: CHECK rebuild copies rows verbatim.
        if _migrate_orders_status_check(cursor):
            import logging

            logging.getLogger(__name__).info("Rebuilt orders table with 'expired' status")
        _migrate_add_tick_columns(cursor)
        # Byte-identical resubmits of a signed order dedupe on (signer,
        # envelope hash); legacy unsigned rows carry NULL hashes and never
        # collide. Created after the CHECK rebuild because a table rename
        # would have carried the index onto the old name and dropped it.
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_signer_envelope "
            "ON orders (user_address, envelope_hash) WHERE envelope_hash IS NOT NULL"
        )
        _seed_node_registry(cursor)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    conn.close()
