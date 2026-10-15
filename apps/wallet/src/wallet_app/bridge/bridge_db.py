"""
ETH-AIT Bridge Database
SQLite database for tracking ETH deposits and AIT minting operations.
"""

import os
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Any

DB_PATH = os.path.join(
    os.getenv("AITBC_DATA_DIR", os.getenv("DATA_DIR", "/var/lib/aitbc")),
    "bridge_deposits.db",
)


# Preserve exact Decimal values through SQLite NUMERIC columns.  SQLite itself
# stores NUMERIC values as integer or real, but by round-tripping through
# Decimal(str(value)) on the way out we keep the textual (not binary-float)
# representation that downstream code needs for the no-float-money rule.
sqlite3.register_adapter(Decimal, lambda d: str(d))
sqlite3.register_converter("NUMERIC", lambda b: Decimal(b.decode()))
# The schema uses TIMESTAMP columns but stores ISO-8601 strings (with a "T").
# Override the deprecated default timestamp converter so it returns the raw
# string and does not split on the old "YYYY-MM-DD HH:MM:SS" format.
sqlite3.register_converter("TIMESTAMP", lambda b: b.decode())


def _connect_db(path: str | None = None) -> sqlite3.Connection:
    """Open a bridge DB connection with Decimal conversion enabled."""
    return sqlite3.connect(
        path or DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
    )


def _add_column_if_not_exists(conn, table, column, col_type):
    """Add a column to a table if it does not already exist."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(" + table + ")")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        cursor.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + col_type)


def init_db() -> None:
    """Initialize the bridge database with required tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = _connect_db()
    cursor = conn.cursor()

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eth_withdrawals (
            id TEXT PRIMARY KEY,
            ait_tx_hash TEXT UNIQUE NOT NULL,
            from_address TEXT NOT NULL,
            eth_address TEXT NOT NULL,
            amount_ait NUMERIC NOT NULL,
            fee_ait NUMERIC NOT NULL,
            net_ait NUMERIC NOT NULL,
            amount_eth NUMERIC NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            eth_tx_hash TEXT,
            refund_tx_hash TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            released_at TIMESTAMP,
            completed_at TIMESTAMP,
            refunded_at TIMESTAMP
        )
    """)

    # Migrate existing tables from REAL to NUMERIC column affinity.
    # SQLite doesn't support ALTER COLUMN TYPE, so we recreate the table
    # (standard SQLite migration pattern). Only runs if columns are REAL.
    _migrate_real_to_numeric(conn)
    _add_column_if_not_exists(conn, "eth_deposits", "recipient", "TEXT")
    _add_column_if_not_exists(conn, "eth_deposits", "ait_tx_hash", "TEXT")
    # Lifecycle columns the standalone aitbc-bridge-monitor writes — the
    # monitor and the wallet share eth_deposits as the single deposit table.
    _add_column_if_not_exists(conn, "eth_deposits", "eth_usd_price", "TEXT")
    _add_column_if_not_exists(conn, "eth_deposits", "ait_usd_price", "TEXT")
    _add_column_if_not_exists(conn, "eth_deposits", "error_message", "TEXT")
    _add_column_if_not_exists(conn, "eth_deposits", "retry_count", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_not_exists(conn, "eth_deposits", "next_retry_at", "TEXT")
    # SUBMITTED-era lifecycle columns (standalone monitor writes these;
    # keep the shared table's shape identical from either side).
    _add_column_if_not_exists(conn, "eth_deposits", "signed_tx", "TEXT")
    _add_column_if_not_exists(conn, "eth_deposits", "envelope_hash", "TEXT")
    _add_column_if_not_exists(conn, "eth_deposits", "submitted_height", "INTEGER")
    _add_column_if_not_exists(conn, "eth_deposits", "rebroadcast_count", "INTEGER NOT NULL DEFAULT 0")
    # B13: which bridge wallet actually received the deposit. NULL on rows
    # that predate the column — the reconcile reports them "address unknown"
    # and treats them as the configured current wallet. No backfill.
    _add_column_if_not_exists(conn, "eth_deposits", "deposit_address", "TEXT")
    # ETH-9: nonce recorded before an ETH release is broadcast, so a crash or
    # restart can prove from the chain whether the send consumed the nonce.
    _add_column_if_not_exists(conn, "eth_withdrawals", "release_nonce", "INTEGER")
    # ETH-14: operator release-retry bookkeeping. retry_count on the row is
    # bumped per attempt; every attempt is recorded in
    # eth_withdrawal_release_attempts with operator + note + outcome.
    _add_column_if_not_exists(conn, "eth_withdrawals", "retry_count", "INTEGER NOT NULL DEFAULT 0")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eth_withdrawal_release_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ait_tx_hash TEXT NOT NULL,
            eth_tx_hash TEXT,
            release_nonce INTEGER,
            resolved_by TEXT,
            resolved_at TIMESTAMP,
            operator_note TEXT,
            outcome TEXT NOT NULL DEFAULT 'attempted'
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_withdrawal_release_attempts_tx ON eth_withdrawal_release_attempts(ait_tx_hash)"
    )

    # ETH-10: escrowed AIT->ETH sell flow. Quotes are hub-issued price
    # promises; locks are the shop-signed TRANSFERs to AIT_SELL_ESCROW.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bridge_sell_quotes (
            id TEXT PRIMARY KEY,
            shop_ait_address TEXT NOT NULL,
            shop_eth_address TEXT NOT NULL,
            ait_amount NUMERIC NOT NULL,
            rate_eth_usd TEXT NOT NULL,
            ait_usd TEXT NOT NULL,
            fee_ait NUMERIC NOT NULL,
            eth_amount NUMERIC NOT NULL,
            feed_age_seconds NUMERIC,
            status TEXT NOT NULL DEFAULT 'quoted',
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bridge_sell_locks (
            id TEXT PRIMARY KEY,
            quote_id TEXT,
            ait_tx_hash TEXT UNIQUE NOT NULL,
            shop_ait_address TEXT NOT NULL,
            shop_eth_address TEXT,
            amount_ait NUMERIC NOT NULL,
            eth_amount NUMERIC,
            requoted INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'locked',
            eth_tx_hash TEXT,
            release_nonce INTEGER,
            settle_tx_hash TEXT,
            refund_tx_hash TEXT,
            escrow_out_nonce INTEGER,
            escrow_out_tx TEXT,
            locked_height INTEGER,
            locked_at TIMESTAMP,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            released_at TIMESTAMP,
            settled_at TIMESTAMP,
            refunded_at TIMESTAMP,
            resolved_by TEXT,
            resolved_at TIMESTAMP,
            operator_note TEXT
        )
    """)

    # Sell tables are new in ETH-10; these ALTERs keep any early dev DB whole.
    _add_column_if_not_exists(conn, "bridge_sell_locks", "escrow_out_nonce", "INTEGER")
    _add_column_if_not_exists(conn, "bridge_sell_locks", "escrow_out_tx", "TEXT")
    # ETH-13: operator-resolution audit columns (sell_admin writes them on
    # every resolution — confirm-swept/requeue/write-off/sweep-now).
    _add_column_if_not_exists(conn, "bridge_sell_locks", "resolved_by", "TEXT")
    _add_column_if_not_exists(conn, "bridge_sell_locks", "resolved_at", "TIMESTAMP")
    _add_column_if_not_exists(conn, "bridge_sell_locks", "operator_note", "TEXT")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_bridge_sell_locks_status ON bridge_sell_locks(status)")

    # ETH-8 phase 3 (dark): trade settlement ledger. The authoritative state
    # machine for exchange trades — the exchange service only ever *mirrors*
    # the outcome onto its trades row through the internal endpoint. One row
    # per (kind, ref_id): 'trade' rows are keyed by the exchange.db trade id,
    # 'order_refund' rows by the order id whose escrow lock is being returned —
    # +order_id is the order's own lock-remainder refund, −order_id a refund
    # of an inbound lock the order could not take, so a stray lock can never
    # block the owner's remainder refund. Owner-sender inbound refunds whose
    # −order_id slot is already held fall back to a lock-hash-derived ref_id
    # below −2**59 (ETH-JOIN-2): deterministic per lock, disjoint from every
    # order/trade id, and read as an order id by nothing.
    # escrow_out_nonce/escrow_out_tx persist the sweep intent before broadcast
    # (ETH-9 discipline); a broadcast hash is never terminal proof.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exchange_settlements (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK(kind IN ('trade', 'order_refund')),
            ref_id INTEGER NOT NULL,
            buy_order_id INTEGER,
            sell_order_id INTEGER,
            buyer_address TEXT,
            seller_address TEXT,
            seller_eth_address TEXT,
            amount_ait NUMERIC,
            eth_amount NUMERIC,
            fee_ait NUMERIC,
            status TEXT NOT NULL DEFAULT 'locked',
            eth_tx_hash TEXT,
            release_nonce INTEGER,
            settle_ait_tx_hash TEXT,
            settle_fee_tx_hash TEXT,
            refund_tx_hash TEXT,
            escrow_out_nonce INTEGER,
            escrow_out_tx TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            released_at TIMESTAMP,
            settled_at TIMESTAMP,
            refunded_at TIMESTAMP,
            UNIQUE(kind, ref_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exchange_settlements_status ON exchange_settlements(status)")

    # Monitor-private dedupe/audit marks — one row per processed chain
    # artifact (lock:<ait_tx_hash>, credit:<eth_tx_hash>) so the full-history
    # escrow/deposit scans stay cheap across restarts and an unattributable
    # deposit is recorded exactly once.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exchange_monitor_marks (
            mark TEXT PRIMARY KEY,
            detail TEXT,
            outcome TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Expression index keeps the public by-recipient lookup off a full table
    # scan; the query stays LOWER() = LOWER() so either service's stored
    # casing matches.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eth_deposits_recipient_lower ON eth_deposits(LOWER(recipient))")

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


def insert_deposit(
    tx_hash: str,
    from_address: str,
    amount_eth: Decimal,
    amount_ait: Decimal,
    recipient: str | None = None,
    deposit_address: str | None = None,
) -> str:
    """Insert a new deposit record."""
    import uuid

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
                datetime.now().isoformat(),
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
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return deposit_id
    except sqlite3.IntegrityError:
        raise ValueError(f"Deposit with tx_hash {tx_hash} already exists") from None
    finally:
        conn.close()


def get_pending_deposits() -> list[dict[str, Any]]:
    """Get all pending deposits."""
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at, recipient, ait_tx_hash
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
            "verified_at": row[7],
            "completed_at": row[8],
            "recipient": row[9],
            "ait_tx_hash": row[10],
        }
        for row in rows
    ]


def update_deposit_status(deposit_id: str, status: str) -> bool:
    """Update deposit status."""
    conn = _connect_db()
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


def update_deposit_tx_hash(deposit_id: str, ait_tx_hash: str) -> bool:
    """Record the AIT transaction hash for a completed deposit."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE eth_deposits SET ait_tx_hash = ? WHERE id = ?",
        (ait_tx_hash, deposit_id),
    )
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


def insert_price_history(eth_usd: Decimal, eth_eur: Decimal, exchange_rate_usd: Decimal, exchange_rate_eur: Decimal) -> None:
    """Insert a new price history record."""
    conn = _connect_db()
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
    conn = _connect_db()
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
            "eth_usd_avg": Decimal(str(result[0])) if result[0] is not None else None,
            "eth_eur_avg": Decimal(str(result[1])) if result[1] is not None else None,
            "exchange_rate_usd_avg": Decimal(str(result[2])) if result[2] is not None else None,
            "exchange_rate_eur_avg": Decimal(str(result[3])) if result[3] is not None else None,
            "count": result[4],
        }

    return None


def cleanup_old_prices(days: int = 30) -> int:
    """Clean up price history older than specified days."""
    conn = _connect_db()
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
                amount_eth, status, error, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                datetime.now().isoformat(),
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
            released_at, completed_at, refunded_at, release_nonce, retry_count
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
            released_at, completed_at, refunded_at, release_nonce
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
            released_at, completed_at, refunded_at, release_nonce
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
    ]
    return [dict(zip(keys, row, strict=False)) for row in rows]


def get_all_withdrawals(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Get all withdrawals with pagination."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id, ait_tx_hash, from_address, eth_address, amount_ait, fee_ait, net_ait,
            amount_eth, status, eth_tx_hash, refund_tx_hash, error, created_at,
            released_at, completed_at, refunded_at, release_nonce
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
    ]
    return [dict(zip(keys, row, strict=False)) for row in rows]


def update_withdrawal_status(
    ait_tx_hash: str,
    status: str,
    eth_tx_hash: str | None = None,
    refund_tx_hash: str | None = None,
    error: str | None = None,
    release_nonce: int | None = None,
) -> bool:
    """Update withdrawal status and optional hashes."""
    conn = _connect_db()
    cursor = conn.cursor()

    timestamp_field = "released_at"
    if status == "completed":
        timestamp_field = "completed_at"
    elif status == "refunded":
        timestamp_field = "refunded_at"

    query = f"""
        UPDATE eth_withdrawals
        SET status = ?, {timestamp_field} = ?, eth_tx_hash = COALESCE(?, eth_tx_hash),
            refund_tx_hash = COALESCE(?, refund_tx_hash), error = COALESCE(?, error),
            release_nonce = COALESCE(?, release_nonce)
        WHERE ait_tx_hash = ?
    """  # nosec B608 - timestamp_field is a hardcoded literal above, never caller input
    cursor.execute(
        query,
        (status, datetime.now().isoformat(), eth_tx_hash, refund_tx_hash, error, release_nonce, ait_tx_hash),
    )
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
    cursor.execute(
        f"""SELECT amount_eth FROM eth_withdrawals
            WHERE status IN ({placeholders})
              AND released_at >= ?""",  # nosec B608 - placeholders are literal '?' generated from _WITHDRAWAL_ETH_COMMITTED_STATUSES; all values bound
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
        (ait_tx_hash, resolved_by, datetime.now().isoformat(), operator_note),
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


# ---------------------------------------------------------------------------
# ETH-10 escrowed sell flow — quote and lock tables
# ---------------------------------------------------------------------------

_SELL_QUOTE_KEYS = [
    "id",
    "shop_ait_address",
    "shop_eth_address",
    "ait_amount",
    "rate_eth_usd",
    "ait_usd",
    "fee_ait",
    "eth_amount",
    "feed_age_seconds",
    "status",
    "expires_at",
    "created_at",
]

_SELL_LOCK_KEYS = [
    "id",
    "quote_id",
    "ait_tx_hash",
    "shop_ait_address",
    "shop_eth_address",
    "amount_ait",
    "eth_amount",
    "requoted",
    "status",
    "eth_tx_hash",
    "release_nonce",
    "settle_tx_hash",
    "refund_tx_hash",
    "escrow_out_nonce",
    "escrow_out_tx",
    "locked_height",
    "locked_at",
    "error",
    "created_at",
    "released_at",
    "settled_at",
    "refunded_at",
    "resolved_by",
    "resolved_at",
    "operator_note",
]

# Lock statuses whose ETH release is still possible — they reserve float.
# `failed`, `refunded` and `settled` are terminal and never counted; `released`
# already sent its ETH so it reserves nothing further. `orphaned` rows are
# refund-bound and never send ETH. `needs_review_sweep` is excluded on the
# same grounds: it is only reached after the ETH leg is already decided.
_SELL_RESERVE_STATUSES = ("locked", "releasing", "needs_review", "queued_reserve", "stale_price")

# Statuses that count ETH as already committed for the daily cap: the send
# either happened or is in an ambiguous state where it may have happened.
# `queued_fee_settle` released its ETH already and only owes the AIT settle;
# `refund_pending`/`queued_fee_refund` proved no ETH left and reserve nothing.
# `needs_review_sweep` is counted conservatively — the released_at filter
# excludes sweep-parked refund rows automatically.
_SELL_ETH_COMMITTED_STATUSES = (
    "releasing",
    "released",
    "settling",
    "settled",
    "needs_review",
    "needs_review_sweep",
    "queued_fee_settle",
)

# Every non-terminal lock status — the poll loop's worklist.
# `refund_pending` = release provably unsent, refund owed but not yet in
# flight; `queued_fee_*` = sweep parked on escrow fee-float deficit.
# `needs_review_sweep` stays on the worklist (still an open, unresolved lock)
# but the router never auto-processes it — operator action only.
_SELL_OPEN_STATUSES = (
    "locked",
    "releasing",
    "released",
    "settling",
    "refunding",
    "refund_pending",
    "stale_price",
    "queued_reserve",
    "queued_fee_settle",
    "queued_fee_refund",
    "needs_review",
    "needs_review_sweep",
    "orphaned",
)


def insert_sell_quote(
    shop_ait_address: str,
    shop_eth_address: str,
    ait_amount: Decimal,
    rate_eth_usd: Decimal,
    ait_usd: Decimal,
    fee_ait: Decimal,
    eth_amount: Decimal,
    expires_at: str,
    feed_age_seconds: Decimal | None = None,
) -> str:
    """Record a new sell quote and return its id."""
    import uuid

    quote_id = f"sellq_{uuid.uuid4().hex[:12]}"
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO bridge_sell_quotes (
            id, shop_ait_address, shop_eth_address, ait_amount, rate_eth_usd,
            ait_usd, fee_ait, eth_amount, feed_age_seconds, status, expires_at, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'quoted', ?, ?)
        """,
        (
            quote_id,
            shop_ait_address,
            shop_eth_address,
            ait_amount,
            str(rate_eth_usd),
            str(ait_usd),
            fee_ait,
            eth_amount,
            feed_age_seconds,
            expires_at,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return quote_id


def get_sell_quote(quote_id: str) -> dict[str, Any] | None:
    """Get a sell quote by id."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT " + ", ".join(_SELL_QUOTE_KEYS) + " FROM bridge_sell_quotes WHERE id = ?",  # nosec B608 - _SELL_QUOTE_KEYS is a module constant; every value is bound via ?
        (quote_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(_SELL_QUOTE_KEYS, row, strict=False))


def get_all_sell_quotes(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Get all sell quotes, newest first."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT " + ", ".join(_SELL_QUOTE_KEYS) + " FROM bridge_sell_quotes ORDER BY created_at DESC LIMIT ? OFFSET ?",  # nosec B608 - _SELL_QUOTE_KEYS is a module constant; every value is bound via ?
        (limit, offset),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(_SELL_QUOTE_KEYS, row, strict=False)) for row in rows]


def count_open_sell_quotes(shop_ait_address: str) -> int:
    """Live ('quoted'/'expired') quotes a shop holds — the per-shop cap input."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM bridge_sell_quotes WHERE LOWER(shop_ait_address) = LOWER(?) AND status IN ('quoted', 'expired')",
        (shop_ait_address,),
    )
    count = int(cursor.fetchone()[0])
    conn.close()
    return count


def get_latest_sell_quote_by_shop(shop_ait_address: str) -> dict[str, Any] | None:
    """Newest quote a shop requested — the per-shop rate-limit input."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT "  # nosec B608 - _SELL_QUOTE_KEYS is a module constant; every value is bound via ?
        + ", ".join(_SELL_QUOTE_KEYS)
        + " FROM bridge_sell_quotes WHERE LOWER(shop_ait_address) = LOWER(?) ORDER BY created_at DESC LIMIT 1",
        (shop_ait_address,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(_SELL_QUOTE_KEYS, row, strict=False))


def update_sell_quote_status(quote_id: str, status: str) -> bool:
    """Update a sell quote's status."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE bridge_sell_quotes SET status = ? WHERE id = ?", (status, quote_id))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def insert_sell_lock(
    ait_tx_hash: str,
    shop_ait_address: str,
    amount_ait: Decimal,
    quote_id: str | None = None,
    shop_eth_address: str | None = None,
    eth_amount: Decimal | None = None,
    status: str = "locked",
    locked_height: int | None = None,
    error: str | None = None,
) -> str | None:
    """Record a new escrow lock. Returns the lock id, or None when the
    ait_tx_hash was already recorded (dedupe — INSERT OR IGNORE)."""
    import uuid

    lock_id = f"sell_{uuid.uuid4().hex[:8]}"
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO bridge_sell_locks (
            id, quote_id, ait_tx_hash, shop_ait_address, shop_eth_address,
            amount_ait, eth_amount, status, locked_height, locked_at, error, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lock_id,
            quote_id,
            ait_tx_hash,
            shop_ait_address,
            shop_eth_address,
            amount_ait,
            eth_amount,
            status,
            locked_height,
            datetime.now().isoformat(),
            error,
            datetime.now().isoformat(),
        ),
    )
    inserted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return lock_id if inserted else None


def get_sell_lock_by_ait_tx_hash(ait_tx_hash: str) -> dict[str, Any] | None:
    """Get a sell lock by its lock transaction hash."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT " + ", ".join(_SELL_LOCK_KEYS) + " FROM bridge_sell_locks WHERE ait_tx_hash = ?",  # nosec B608 - _SELL_LOCK_KEYS is a module constant; every value is bound via ?
        (ait_tx_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(_SELL_LOCK_KEYS, row, strict=False))


def get_sell_lock_by_id(lock_id: str) -> dict[str, Any] | None:
    """Get a sell lock by its local id."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT " + ", ".join(_SELL_LOCK_KEYS) + " FROM bridge_sell_locks WHERE id = ?",  # nosec B608 - _SELL_LOCK_KEYS is a module constant; every value is bound via ?
        (lock_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(_SELL_LOCK_KEYS, row, strict=False))


def get_sell_lock_by_quote_id(
    quote_id: str,
    exclude_ait_tx_hash: str | None = None,
    statuses: tuple[str, ...] | None = None,
    before_created_at: str | None = None,
) -> dict[str, Any] | None:
    """The lock bound to a quote, if any — a quote admits exactly one lock.
    ``statuses`` narrows which sibling rows count (terminal siblings do not
    consume the quote); ``before_created_at`` restricts to siblings recorded
    before a timestamp, so the earliest lock wins the quote."""
    conn = _connect_db()
    cursor = conn.cursor()
    query = "SELECT " + ", ".join(_SELL_LOCK_KEYS) + " FROM bridge_sell_locks WHERE quote_id = ?"  # nosec B608 - _SELL_LOCK_KEYS is a module constant; every value is bound via ?
    params: list[Any] = [quote_id]
    if exclude_ait_tx_hash:
        query += " AND ait_tx_hash != ?"
        params.append(exclude_ait_tx_hash)
    if statuses:
        query += f" AND status IN ({', '.join('?' for _ in statuses)})"
        params.extend(statuses)
    if before_created_at:
        query += " AND created_at < ?"
        params.append(before_created_at)
    cursor.execute(query + " ORDER BY created_at ASC LIMIT 1", params)
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(_SELL_LOCK_KEYS, row, strict=False))


def get_sell_quotes_by_status(statuses: tuple[str, ...]) -> list[dict[str, Any]]:
    """Get sell quotes in any of the given statuses, oldest first."""
    conn = _connect_db()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in statuses)
    cursor.execute(
        "SELECT "
        + ", ".join(_SELL_QUOTE_KEYS)
        + f" FROM bridge_sell_quotes WHERE status IN ({placeholders}) ORDER BY created_at ASC",
        statuses,
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(_SELL_QUOTE_KEYS, row, strict=False)) for row in rows]


def get_sell_locks_by_status(statuses: tuple[str, ...]) -> list[dict[str, Any]]:
    """Get sell locks in any of the given statuses, oldest first."""
    conn = _connect_db()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in statuses)
    cursor.execute(
        "SELECT "
        + ", ".join(_SELL_LOCK_KEYS)
        + f" FROM bridge_sell_locks WHERE status IN ({placeholders}) ORDER BY created_at ASC",
        statuses,
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(_SELL_LOCK_KEYS, row, strict=False)) for row in rows]


def get_open_sell_locks() -> list[dict[str, Any]]:
    """All non-terminal sell locks — the monitor's worklist."""
    return get_sell_locks_by_status(_SELL_OPEN_STATUSES)


def get_sell_inflight_sweep() -> dict[str, Any] | None:
    """The in-flight escrow sweep, if any — 'settling'/'refunding' rows hold a
    persisted intent (nonce + signed blob). Sweep serialization: a new sweep
    must not start while one is in flight."""
    rows = get_sell_locks_by_status(("settling", "refunding"))
    return rows[0] if rows else None


def get_all_sell_locks(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Get all sell locks, newest first."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT " + ", ".join(_SELL_LOCK_KEYS) + " FROM bridge_sell_locks ORDER BY created_at DESC LIMIT ? OFFSET ?",  # nosec B608 - _SELL_LOCK_KEYS is a module constant; every value is bound via ?
        (limit, offset),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(_SELL_LOCK_KEYS, row, strict=False)) for row in rows]


def update_sell_lock_status(
    ait_tx_hash: str,
    status: str,
    *,
    quote_id: str | None = None,
    shop_eth_address: str | None = None,
    eth_amount: Decimal | None = None,
    requoted: int | None = None,
    eth_tx_hash: str | None = None,
    release_nonce: int | None = None,
    settle_tx_hash: str | None = None,
    refund_tx_hash: str | None = None,
    escrow_out_nonce: int | None = None,
    escrow_out_tx: str | None = None,
    resolved_by: str | None = None,
    resolved_at: str | None = None,
    operator_note: str | None = None,
    error: str | None = None,
) -> bool:
    """Update a sell lock's status and optional lifecycle fields."""
    conn = _connect_db()
    cursor = conn.cursor()

    timestamp_field = None
    if status in ("releasing", "released"):
        timestamp_field = "released_at"
    elif status == "settled":
        timestamp_field = "settled_at"
    elif status == "refunded":
        timestamp_field = "refunded_at"

    if timestamp_field:
        query = f"""
            UPDATE bridge_sell_locks
            SET status = ?, {timestamp_field} = ?,
                quote_id = COALESCE(?, quote_id),
                shop_eth_address = COALESCE(?, shop_eth_address),
                eth_amount = COALESCE(?, eth_amount),
                requoted = COALESCE(?, requoted),
                eth_tx_hash = COALESCE(?, eth_tx_hash),
                release_nonce = COALESCE(?, release_nonce),
                settle_tx_hash = COALESCE(?, settle_tx_hash),
                refund_tx_hash = COALESCE(?, refund_tx_hash),
                escrow_out_nonce = COALESCE(?, escrow_out_nonce),
                escrow_out_tx = COALESCE(?, escrow_out_tx),
                resolved_by = COALESCE(?, resolved_by),
                resolved_at = COALESCE(?, resolved_at),
                operator_note = COALESCE(?, operator_note),
                error = COALESCE(?, error)
            WHERE ait_tx_hash = ?
        """  # nosec B608 - timestamp_field is a hardcoded literal above, never caller input
        params: tuple = (
            status,
            datetime.now().isoformat(),
            quote_id,
            shop_eth_address,
            eth_amount,
            requoted,
            eth_tx_hash,
            release_nonce,
            settle_tx_hash,
            refund_tx_hash,
            escrow_out_nonce,
            escrow_out_tx,
            resolved_by,
            resolved_at,
            operator_note,
            error,
            ait_tx_hash,
        )
    else:
        query = """
            UPDATE bridge_sell_locks
            SET status = ?,
                quote_id = COALESCE(?, quote_id),
                shop_eth_address = COALESCE(?, shop_eth_address),
                eth_amount = COALESCE(?, eth_amount),
                requoted = COALESCE(?, requoted),
                eth_tx_hash = COALESCE(?, eth_tx_hash),
                release_nonce = COALESCE(?, release_nonce),
                settle_tx_hash = COALESCE(?, settle_tx_hash),
                refund_tx_hash = COALESCE(?, refund_tx_hash),
                escrow_out_nonce = COALESCE(?, escrow_out_nonce),
                escrow_out_tx = COALESCE(?, escrow_out_tx),
                resolved_by = COALESCE(?, resolved_by),
                resolved_at = COALESCE(?, resolved_at),
                operator_note = COALESCE(?, operator_note),
                error = COALESCE(?, error)
            WHERE ait_tx_hash = ?
        """
        params = (
            status,
            quote_id,
            shop_eth_address,
            eth_amount,
            requoted,
            eth_tx_hash,
            release_nonce,
            settle_tx_hash,
            refund_tx_hash,
            escrow_out_nonce,
            escrow_out_tx,
            resolved_by,
            resolved_at,
            operator_note,
            error,
            ait_tx_hash,
        )
    cursor.execute(query, params)
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def get_sell_pending_eth_reserve() -> Decimal:
    """ETH committed to sell locks that may still release — reserves float.

    Excludes `failed` rows: a failed lock's refund moves AIT, not ETH, so
    counting it would park float forever (the wart ETH-7 §4 flagged in
    get_pending_withdrawals does not repeat here).
    """
    conn = _connect_db()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in _SELL_RESERVE_STATUSES)
    cursor.execute(
        f"SELECT COALESCE(SUM(eth_amount), 0) FROM bridge_sell_locks WHERE status IN ({placeholders})",  # nosec B608 - placeholders are literal '?' generated from _SELL_RESERVE_STATUSES; all values bound
        _SELL_RESERVE_STATUSES,
    )
    total = cursor.fetchone()[0]
    conn.close()
    return Decimal(str(total)) if total is not None else Decimal("0")


def get_sell_eth_committed_since(since_iso: str) -> Decimal:
    """Sum of ETH released (or possibly released) by sell locks since a
    timestamp — the persisted basis for the daily release cap.

    `written_off` stays out of `_SELL_ETH_COMMITTED_STATUSES` itself, but
    a written-off row that *recorded a release tx* still counts here:
    the cap measures ETH that left the wallet and operator bookkeeping
    does not undo a payment (ETH-13, decided 14 Oct). A row written off
    before any release spent nothing — the `eth_tx_hash IS NOT NULL`
    check is what tells the two apart. The pending-ETH reserve is the
    opposite semantic (ETH not yet paid), so `written_off` remains fully
    excluded from `_SELL_RESERVE_STATUSES`."""
    conn = _connect_db()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in _SELL_ETH_COMMITTED_STATUSES)
    cursor.execute(
        f"""SELECT COALESCE(SUM(eth_amount), 0) FROM bridge_sell_locks
            WHERE (status IN ({placeholders})
                   OR (status = 'written_off' AND eth_tx_hash IS NOT NULL))
              AND released_at >= ?""",  # nosec B608 - placeholders are literal '?' generated from _SELL_ETH_COMMITTED_STATUSES; all values bound
        (*_SELL_ETH_COMMITTED_STATUSES, since_iso),
    )
    total = cursor.fetchone()[0]
    conn.close()
    return Decimal(str(total)) if total is not None else Decimal("0")


# ---------------------------------------------------------------------------
# ETH-8 phase 3 (dark): exchange trade settlement ledger
#
# Mirror of the sell-lock discipline for exchange trades: every state change
# goes through update_exchange_settlement (no raw UPDATEs elsewhere), sweep
# intents (escrow_out_nonce + escrow_out_tx) persist before broadcast, and a
# broadcast hash is never terminal proof — sealed chain state decides.
# ---------------------------------------------------------------------------

# Full settlement vocabulary — kept identical to _SETTLEMENT_STATES in
# apps/exchange/simple_exchange/db.py; a parity test in
# apps/wallet/tests/test_exchange_settlement_db.py pins the two together.
_EXCHANGE_SETTLEMENT_STATUSES = frozenset(
    {
        "locked",
        "releasing",
        "released",
        "settling",
        "refunding",
        "refund_pending",
        "queued_reserve",
        "queued_fee_settle",
        "queued_fee_refund",
        "needs_review",
        "needs_review_release",
        "needs_review_sweep",
        "settled",
        "refunded",
        "failed",
    }
)

# Statuses still in motion — the settlement monitor's worklist. Mirrors
# _SELL_OPEN_STATUSES; needs_review_sweep stays listed (unresolved) but the
# router never auto-processes it.
_EXCHANGE_SETTLEMENT_OPEN_STATUSES = (
    "locked",
    "releasing",
    "released",
    "settling",
    "refunding",
    "refund_pending",
    "queued_reserve",
    "queued_fee_settle",
    "queued_fee_refund",
    "needs_review",
    "needs_review_release",
    "needs_review_sweep",
)

# At most one escrow sweep is in flight per escrow account, across sell
# locks AND exchange settlements — they share one nonce space. Both sides
# must union these statuses with the other table's before any broadcast.
_EXCHANGE_SETTLEMENT_INFLIGHT_SWEEP_STATUSES = ("settling", "refunding")

# Settlement statuses whose ETH release is still owed or undecidable — they
# reserve bridge float so withdrawals/sells cannot spend it underneath.
_EXCHANGE_SETTLEMENT_RESERVE_STATUSES = (
    "locked",
    "releasing",
    "needs_review",
    "needs_review_release",
    "queued_reserve",
)


def insert_exchange_settlement(
    kind: str,
    ref_id: int,
    *,
    buy_order_id: int | None = None,
    sell_order_id: int | None = None,
    buyer_address: str | None = None,
    seller_address: str | None = None,
    seller_eth_address: str | None = None,
    amount_ait: Decimal | None = None,
    eth_amount: Decimal | None = None,
    fee_ait: Decimal | None = None,
) -> str | None:
    """Record a settlement for a trade (or an order refund). Returns the new
    row id, or None when (kind, ref_id) already exists — the UNIQUE pair
    makes a second settlement row for one trade structurally impossible.
    kind is validated in Python: INSERT OR IGNORE would otherwise swallow a
    CHECK violation and make a caller bug look like a dedupe."""
    if kind not in ("trade", "order_refund"):
        raise ValueError(f"unknown settlement kind: {kind!r}")
    import uuid

    settlement_id = f"exs_{uuid.uuid4().hex[:8]}"
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO exchange_settlements (
            id, kind, ref_id, buy_order_id, sell_order_id,
            buyer_address, seller_address, seller_eth_address,
            amount_ait, eth_amount, fee_ait, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'locked', ?)
        """,
        (
            settlement_id,
            kind,
            ref_id,
            buy_order_id,
            sell_order_id,
            buyer_address,
            seller_address,
            seller_eth_address,
            amount_ait,
            eth_amount,
            fee_ait,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    inserted = cursor.rowcount > 0
    conn.close()
    return settlement_id if inserted else None


def _row_to_settlement(row: tuple | None, columns: list[str]) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(zip(columns, row, strict=True))


_SETTLEMENT_SELECT_COLS = [
    "id",
    "kind",
    "ref_id",
    "buy_order_id",
    "sell_order_id",
    "buyer_address",
    "seller_address",
    "seller_eth_address",
    "amount_ait",
    "eth_amount",
    "fee_ait",
    "status",
    "eth_tx_hash",
    "release_nonce",
    "settle_ait_tx_hash",
    "settle_fee_tx_hash",
    "refund_tx_hash",
    "escrow_out_nonce",
    "escrow_out_tx",
    "error",
    "created_at",
    "released_at",
    "settled_at",
    "refunded_at",
]


def get_exchange_settlement(kind: str, ref_id: int) -> dict[str, Any] | None:
    """One settlement row by its (kind, ref_id) key."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {', '.join(_SETTLEMENT_SELECT_COLS)} FROM exchange_settlements WHERE kind = ? AND ref_id = ?",  # nosec B608 - column list is a hardcoded constant
        (kind, ref_id),
    )
    row = cursor.fetchone()
    conn.close()
    return _row_to_settlement(row, _SETTLEMENT_SELECT_COLS)


def get_open_exchange_settlements() -> list[dict[str, Any]]:
    """All settlement rows the monitor still has to drive."""
    conn = _connect_db()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in _EXCHANGE_SETTLEMENT_OPEN_STATUSES)
    cursor.execute(
        f"SELECT {', '.join(_SETTLEMENT_SELECT_COLS)} FROM exchange_settlements WHERE status IN ({placeholders}) ORDER BY created_at",  # nosec B608 - placeholders are literal '?' generated from the constant; values bound
        _EXCHANGE_SETTLEMENT_OPEN_STATUSES,
    )
    rows = cursor.fetchall()
    conn.close()
    return [s for r in rows if (s := _row_to_settlement(r, _SETTLEMENT_SELECT_COLS)) is not None]


def get_exchange_inflight_sweep() -> dict[str, Any] | None:
    """The single in-flight exchange escrow sweep (settling/refunding), if any."""
    conn = _connect_db()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in _EXCHANGE_SETTLEMENT_INFLIGHT_SWEEP_STATUSES)
    cursor.execute(
        f"SELECT {', '.join(_SETTLEMENT_SELECT_COLS)} FROM exchange_settlements WHERE status IN ({placeholders}) LIMIT 1",  # nosec B608 - same literal-placeholder pattern
        _EXCHANGE_SETTLEMENT_INFLIGHT_SWEEP_STATUSES,
    )
    row = cursor.fetchone()
    conn.close()
    return _row_to_settlement(row, _SETTLEMENT_SELECT_COLS)


def get_exchange_pending_eth_reserve() -> Decimal:
    """ETH owed by open exchange settlements — counted against the shared
    bridge float alongside withdrawals and sell locks. Rows are summed as
    Decimal in Python: SQL SUM() would run the NUMERIC column through float
    arithmetic before the Decimal converter ever saw it."""
    conn = _connect_db()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in _EXCHANGE_SETTLEMENT_RESERVE_STATUSES)
    cursor.execute(
        f"SELECT eth_amount FROM exchange_settlements WHERE status IN ({placeholders})",  # nosec B608 - same literal-placeholder pattern
        _EXCHANGE_SETTLEMENT_RESERVE_STATUSES,
    )
    total = Decimal(0)
    for (amount,) in cursor.fetchall():
        if amount is not None:
            total += amount if isinstance(amount, Decimal) else Decimal(str(amount))
    conn.close()
    return total


# Settlement statuses where the ETH release happened or may have happened —
# mirrors _SELL_ETH_COMMITTED_STATUSES with the settlement-only
# `needs_review_release` added. `refund_pending`/`queued_fee_refund` proved
# no ETH left; `refunded`/`failed` are terminal-unpaid.
_EXCHANGE_ETH_COMMITTED_STATUSES = (
    "releasing",
    "released",
    "settling",
    "settled",
    "needs_review",
    "needs_review_release",
    "needs_review_sweep",
    "queued_fee_settle",
)


def get_exchange_eth_committed_since(since_iso: str) -> Decimal:
    """Sum of ETH released (or possibly released) by exchange settlements
    since a timestamp — the settlement lane's contribution to the release
    windows surfaced by GET /v1/bridge/float (CLI-5)."""
    conn = _connect_db()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in _EXCHANGE_ETH_COMMITTED_STATUSES)
    cursor.execute(
        f"""SELECT eth_amount FROM exchange_settlements
            WHERE status IN ({placeholders})
              AND released_at >= ?""",  # nosec B608 - same literal-placeholder pattern
        (*_EXCHANGE_ETH_COMMITTED_STATUSES, since_iso),
    )
    total = Decimal(0)
    for (amount,) in cursor.fetchall():
        if amount is not None:
            total += amount if isinstance(amount, Decimal) else Decimal(str(amount))
    conn.close()
    return total


def list_exchange_settlements(
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Exchange-settlement rows for the /v1/bridge/settlements read route
    (CLI-1) — newest first, optionally filtered by kind and status."""
    clauses = []
    params: list[Any] = []
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {', '.join(_SETTLEMENT_SELECT_COLS)} FROM exchange_settlements{where}"  # nosec B608 - column list/keywords are literals; every value is bound
        " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )
    rows = cursor.fetchall()
    conn.close()
    return [s for r in rows if (s := _row_to_settlement(r, _SETTLEMENT_SELECT_COLS)) is not None]


def update_exchange_settlement(
    settlement_id: str,
    status: str,
    *,
    eth_tx_hash: str | None = None,
    release_nonce: int | None = None,
    settle_ait_tx_hash: str | None = None,
    settle_fee_tx_hash: str | None = None,
    refund_tx_hash: str | None = None,
    escrow_out_nonce: int | None = None,
    escrow_out_tx: str | None = None,
    error: str | None = None,
) -> bool:
    """Update a settlement row's status and optional lifecycle fields.

    The only permitted write path for exchange_settlements — mirrors
    update_sell_lock_status: the status drives the lifecycle timestamp and
    every field writes via COALESCE so a NULL argument never blanks a
    recorded hash or nonce. Forward-only/no-rewrite discipline is enforced
    by the monitor and the mirror endpoint above this layer, like sell locks.
    status is validated against the full vocabulary in Python: the table
    carries no CHECK on this column, so a typo'd status would otherwise
    silently park the row outside every worklist.
    """
    if status not in _EXCHANGE_SETTLEMENT_STATUSES:
        raise ValueError(f"unknown settlement status: {status!r}")
    conn = _connect_db()
    cursor = conn.cursor()

    timestamp_field = None
    if status in ("releasing", "released"):
        timestamp_field = "released_at"
    elif status == "settled":
        timestamp_field = "settled_at"
    elif status == "refunded":
        timestamp_field = "refunded_at"

    if timestamp_field:
        query = f"""
            UPDATE exchange_settlements
            SET status = ?, {timestamp_field} = ?,
                eth_tx_hash = COALESCE(?, eth_tx_hash),
                release_nonce = COALESCE(?, release_nonce),
                settle_ait_tx_hash = COALESCE(?, settle_ait_tx_hash),
                settle_fee_tx_hash = COALESCE(?, settle_fee_tx_hash),
                refund_tx_hash = COALESCE(?, refund_tx_hash),
                escrow_out_nonce = COALESCE(?, escrow_out_nonce),
                escrow_out_tx = COALESCE(?, escrow_out_tx),
                error = COALESCE(?, error)
            WHERE id = ?
        """  # nosec B608 - timestamp_field is a hardcoded literal above, never caller input
        params: tuple = (
            status,
            datetime.now().isoformat(),
            eth_tx_hash,
            release_nonce,
            settle_ait_tx_hash,
            settle_fee_tx_hash,
            refund_tx_hash,
            escrow_out_nonce,
            escrow_out_tx,
            error,
            settlement_id,
        )
    else:
        query = """
            UPDATE exchange_settlements
            SET status = ?,
                eth_tx_hash = COALESCE(?, eth_tx_hash),
                release_nonce = COALESCE(?, release_nonce),
                settle_ait_tx_hash = COALESCE(?, settle_ait_tx_hash),
                settle_fee_tx_hash = COALESCE(?, settle_fee_tx_hash),
                refund_tx_hash = COALESCE(?, refund_tx_hash),
                escrow_out_nonce = COALESCE(?, escrow_out_nonce),
                escrow_out_tx = COALESCE(?, escrow_out_tx),
                error = COALESCE(?, error)
            WHERE id = ?
        """
        params = (
            status,
            eth_tx_hash,
            release_nonce,
            settle_ait_tx_hash,
            settle_fee_tx_hash,
            refund_tx_hash,
            escrow_out_nonce,
            escrow_out_tx,
            error,
            settlement_id,
        )
    cursor.execute(query, params)
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def insert_monitor_mark(mark: str, detail: str | None = None, outcome: str | None = None) -> bool:
    """Record a processed chain artifact (``lock:<ait_tx_hash>`` /
    ``credit:<eth_tx_hash>``). Returns False when the mark already exists —
    the PK dedupe is the monitor's whole restart-safe "have I seen this"
    test."""
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO exchange_monitor_marks (mark, detail, outcome) VALUES (?, ?, ?)",
        (mark, detail, outcome),
    )
    conn.commit()
    inserted = cursor.rowcount > 0
    conn.close()
    return inserted


def update_monitor_mark(mark: str, outcome: str) -> None:
    conn = _connect_db()
    conn.execute("UPDATE exchange_monitor_marks SET outcome = ? WHERE mark = ?", (outcome, mark))
    conn.commit()
    conn.close()


def monitor_mark(mark: str) -> dict[str, Any] | None:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT mark, detail, outcome, created_at FROM exchange_monitor_marks WHERE mark = ?", (mark,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return {"mark": row[0], "detail": row[1], "outcome": row[2], "created_at": row[3]}
