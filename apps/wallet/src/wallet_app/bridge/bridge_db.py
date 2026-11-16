"""
ETH-AIT Bridge Database
SQLite database for tracking ETH deposits and AIT minting operations.
"""

import logging
import os
import sqlite3
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Static-only re-exports: gives mypy/ruff the real signatures of every
    # name the bridge_db_<domain> modules own, while runtime resolution stays
    # lazy through __getattr__ below (the submodules import _connect_db and
    # DB_PATH back from this module, so they cannot be imported eagerly —
    # see the facade comment at the bottom of this file).
    from .bridge_db_deposits import (
        _ETH_DEPOSIT_STATUSES as _ETH_DEPOSIT_STATUSES,
        get_all_deposits,
        get_deposit_by_id,
        get_deposit_by_tx_hash,
        get_deposits_by_recipient,
        get_pending_deposits,
        insert_deposit,
        insert_exchange_prepay_deposit,
        update_deposit_status,
        update_deposit_tx_hash,
    )
    from .bridge_db_prices import (
        cleanup_old_prices,
        get_all_time_average,
        insert_price_history,
    )
    from .bridge_db_sell import (
        _SELL_ETH_COMMITTED_STATUSES as _SELL_ETH_COMMITTED_STATUSES,
        _SELL_LOCK_KEYS as _SELL_LOCK_KEYS,
        _SELL_OPEN_STATUSES as _SELL_OPEN_STATUSES,
        _SELL_QUOTE_KEYS as _SELL_QUOTE_KEYS,
        _SELL_RESERVE_STATUSES as _SELL_RESERVE_STATUSES,
        count_open_sell_quotes,
        get_all_sell_locks,
        get_all_sell_quotes,
        get_latest_sell_quote_by_shop,
        get_open_sell_locks,
        get_sell_eth_committed_since,
        get_sell_inflight_sweep,
        get_sell_lock_by_ait_tx_hash,
        get_sell_lock_by_id,
        get_sell_lock_by_quote_id,
        get_sell_locks_by_status,
        get_sell_pending_eth_reserve,
        get_sell_quote,
        get_sell_quotes_by_status,
        insert_sell_lock,
        insert_sell_quote,
        update_sell_lock_status,
        update_sell_quote_status,
    )
    from .bridge_db_settlement import (
        _EXCHANGE_ETH_COMMITTED_STATUSES as _EXCHANGE_ETH_COMMITTED_STATUSES,
        _EXCHANGE_SETTLEMENT_INFLIGHT_SWEEP_STATUSES as _EXCHANGE_SETTLEMENT_INFLIGHT_SWEEP_STATUSES,
        _EXCHANGE_SETTLEMENT_OPEN_STATUSES as _EXCHANGE_SETTLEMENT_OPEN_STATUSES,
        _EXCHANGE_SETTLEMENT_RESERVE_STATUSES as _EXCHANGE_SETTLEMENT_RESERVE_STATUSES,
        _EXCHANGE_SETTLEMENT_STATUSES as _EXCHANGE_SETTLEMENT_STATUSES,
        _SETTLEMENT_SELECT_COLS as _SETTLEMENT_SELECT_COLS,
        _row_to_settlement as _row_to_settlement,
        get_exchange_eth_committed_since,
        get_exchange_inflight_sweep,
        get_exchange_pending_eth_reserve,
        get_exchange_settlement,
        get_open_exchange_settlements,
        insert_exchange_settlement,
        insert_monitor_mark,
        list_exchange_settlements,
        monitor_mark,
        update_exchange_settlement,
        update_monitor_mark,
    )
    from .bridge_db_withdrawals import (
        _WITHDRAWAL_ETH_COMMITTED_STATUSES as _WITHDRAWAL_ETH_COMMITTED_STATUSES,
        get_all_withdrawals,
        get_awaiting_depth_withdrawals,
        get_pending_withdrawals,
        get_release_attempts,
        get_resumable_withdrawals,
        get_withdrawal_by_ait_tx_hash,
        get_withdrawal_eth_committed_since,
        insert_withdrawal,
        record_release_attempt,
        update_release_attempt,
        update_withdrawal_block,
        update_withdrawal_pricing,
        update_withdrawal_status,
    )

DB_PATH = (os.getenv("BRIDGE_DEPOSITS_DB") or "").strip() or os.path.join(
    os.getenv("AITBC_DATA_DIR", os.getenv("DATA_DIR", "/var/lib/aitbc")),
    "data",
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


# Keep in sync with bridge_monitor.storage.canon_tx_hash — this app shares
# the eth_deposits table with aitbc-bridge-monitor (BRIDGE_DEPOSITS_DB), so
# both writers must land the same key spelling or the UNIQUE dedupe fails
# and one ETH deposit can be paid out twice (issue #668). The RPC JSON
# hash is 0x-prefixed while web3's tx.hash.hex() is bare.
_HEX_CHARS = frozenset("0123456789abcdef")


def _canon_tx_hash(value: str) -> str:
    """Canonical ``0x``-prefixed lowercase ETH tx hash; non-hex synthetic
    ids pass through unchanged."""
    s = str(value)
    body = s[2:] if s[:2].lower() == "0x" else s
    lowered = body.lower()
    if not lowered or any(c not in _HEX_CHARS for c in lowered):
        return s
    return "0x" + lowered


def _tx_hash_keys(value: str) -> tuple[str, str]:
    """Stored spellings a tx_hash lookup must cover: canonical plus the
    legacy unprefixed form written by the other writer. Pair with
    ``lower(tx_hash)`` so mixed-case legacy rows also match."""
    canon = _canon_tx_hash(value)
    return (canon, canon[2:] if canon.startswith("0x") else canon)


def _money_str(value: Decimal | float | str | None) -> str:
    """Return a fixed-point, no-exponent decimal string for money amounts."""
    if value is None:
        return ""
    d = Decimal(str(value))
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


# WAL + busy_timeout parity with aitbc_chain.database._set_sqlite_pragmas.
# This DB has two writer services (wallet + bridge-monitor) and previously
# ran rollback-journal mode with sqlite3's 5s default busy wait — lock
# contention surfaced as "database is locked" far earlier than intended
# (#1559). busy_timeout is per-connection; journal_mode is persistent but
# re-asserting it on an already-WAL file is a no-op read.
def _connect_db(path: str | None = None) -> sqlite3.Connection:
    """Open a bridge DB connection with Decimal conversion enabled."""
    conn = sqlite3.connect(
        path or DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        timeout=30,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


# ---------------------------------------------------------------------------
# Cross-process ETH-release flock (WITHDRAW-RETRY-LOCK-1 / #1921)
# ---------------------------------------------------------------------------
#
# Every ETH-release lane — the withdraw monitor's _release_eth_for_withdrawal,
# the sell-escrow and exchange-settlement release sections, and the
# withdraw_admin release-retry CLI — signs from ETH_WALLET_ADDRESS: ONE nonce
# space shared by every process that can release. ETH_RELEASE_NONCE_LOCK is
# asyncio-only and cannot serialize the CLI against the wallet service, so
# the nonce→sign→record→broadcast section is additionally guarded by this
# flock. The path derives from DB_PATH at call time so BRIDGE_DEPOSITS_DB /
# DATA_DIR overrides (and test monkeypatching) relocate it with the ledger —
# the same convention as the bridge-monitor admin flock on <db>.admin.lock.
#
# _RELEASE_LOCK_STATE is this process's hold registry: lock path ->
# [fd, depth]. It makes the lock re-entrant: withdraw_admin holds it around
# the whole retry command while _release_eth_for_withdrawal takes it again
# inside — without the registry the second flock on a fresh fd would
# self-deadlock.

_RELEASE_LOCK_STATE: dict[str, list[int]] = {}


def _eth_release_lock_path() -> str:
    return f"{DB_PATH}.eth_release.lock"


def _eth_release_lock_reacquire() -> int | None:
    """Depth-counted re-acquire when this process already holds the flock."""
    state = _RELEASE_LOCK_STATE.get(_eth_release_lock_path())
    if state is None:
        return None
    state[1] += 1
    return state[0]


def try_eth_release_lock() -> int | None:
    """Take the ETH-release flock without blocking.

    Returns the lock fd (release via :func:`release_eth_release_lock`) or
    None when another process holds it — monitor lanes poll this inside an
    asyncio sleep loop, one-shot admin commands refuse outright (the
    bridge-monitor ``try_admin_lock`` convention). Re-entrant within this
    process via the hold registry.
    """
    held = _eth_release_lock_reacquire()
    if held is not None:
        return held
    import fcntl

    path = _eth_release_lock_path()
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    _RELEASE_LOCK_STATE[path] = [fd, 1]
    return fd


def release_eth_release_lock(fd: int) -> None:
    """Drop one hold on the ETH-release flock; unlocks and closes at depth 0."""
    import fcntl

    for path, state in list(_RELEASE_LOCK_STATE.items()):
        if state[0] != fd:
            continue
        state[1] -= 1
        if state[1] > 0:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
            del _RELEASE_LOCK_STATE[path]
        return


def _add_column_if_not_exists(conn, table, column, col_type):
    """Add a column to a table if it does not already exist."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(" + table + ")")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        cursor.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + col_type)


def init_db() -> None:
    """Initialize the bridge database with required tables."""
    canonical_dir = os.path.realpath(
        os.path.join(os.getenv("AITBC_DATA_DIR", os.getenv("DATA_DIR", "/var/lib/aitbc")), "data")
    )
    if not os.path.realpath(DB_PATH).startswith(canonical_dir + os.sep):
        logging.getLogger(__name__).warning(
            "bridge ledger path %s is outside %s — expected under DATA_DIR/data; check BRIDGE_DEPOSITS_DB",
            DB_PATH,
            canonical_dir,
        )
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
    # F3: the AIT-side block the withdraw sealed in, recorded when the row is
    # created so the monitor can demand BRIDGE_WITHDRAW_SEAL_DEPTH before
    # paying and detect a reorg that moved the tx to a different block.
    _add_column_if_not_exists(conn, "eth_withdrawals", "ait_block_height", "INTEGER")
    _add_column_if_not_exists(conn, "eth_withdrawals", "ait_block_hash", "TEXT")
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
            eth_amount TEXT NOT NULL,
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
            eth_amount TEXT,
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

    # B13/BR-6: the outbound-ETH ledger lives in this shared file too — the
    # monitor writes it, either service may bootstrap it first. Same DDL as
    # bridge_monitor/storage.py.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bridge_outbound (
            tx_hash       TEXT PRIMARY KEY,
            to_address    TEXT NOT NULL,
            value_eth     NUMERIC NOT NULL,
            gas_wei       INTEGER,
            block_height  INTEGER NOT NULL,
            kind          TEXT NOT NULL,
            matched_deposit_tx TEXT,
            note          TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            # temp_name is a hardcoded literal table name from this function's own migration list (`table` above), never external input
            query = f"INSERT INTO eth_deposits SELECT id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, verified_at, completed_at FROM {temp_name}"  # nosec B608
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
            # temp_name is a hardcoded literal table name from this function's own migration list (`table` above), never external input
            query = f"INSERT INTO price_history SELECT id, timestamp, eth_usd_price, eth_eur_price, exchange_rate_usd, exchange_rate_eur FROM {temp_name}"  # nosec
            cursor.execute(query)
        cursor.execute(f"DROP TABLE {temp_name}")  # temp_name is a hardcoded literal (see above)


# ---------------------------------------------------------------------------
# Compatibility facade — the per-table modules below
# ---------------------------------------------------------------------------
#
# This module stays the single import target every caller (and every test)
# already uses: ``DB_PATH``, ``_connect_db`` and the schema (``init_db``) live
# here, and the domain modules import those helpers back from this module —
# which is why they can only be pulled in lazily, after this module is fully
# initialized (PEP 562 ``__getattr__``; same pattern as
# coordinator_api.services). ``patch("...bridge_db.DB_PATH")`` keeps working
# because ``_connect_db`` resolves ``DB_PATH`` in *this* module's globals.
#
# tests/ops/test_bridge_deposits_db_env.py also execs this file standalone
# via importlib — keep top-level imports light and never import the
# submodules eagerly.

_NAME_TO_MODULE = {
    # eth_deposits rows + status vocabulary
    "insert_deposit": "bridge_db_deposits",
    "insert_exchange_prepay_deposit": "bridge_db_deposits",
    "get_pending_deposits": "bridge_db_deposits",
    "_ETH_DEPOSIT_STATUSES": "bridge_db_deposits",
    "update_deposit_status": "bridge_db_deposits",
    "update_deposit_tx_hash": "bridge_db_deposits",
    "get_deposit_by_tx_hash": "bridge_db_deposits",
    "get_deposit_by_id": "bridge_db_deposits",
    "get_all_deposits": "bridge_db_deposits",
    "get_deposits_by_recipient": "bridge_db_deposits",
    # price_history
    "insert_price_history": "bridge_db_prices",
    "get_all_time_average": "bridge_db_prices",
    "cleanup_old_prices": "bridge_db_prices",
    # eth_withdrawals + release-attempt audit
    "insert_withdrawal": "bridge_db_withdrawals",
    "get_withdrawal_by_ait_tx_hash": "bridge_db_withdrawals",
    "get_pending_withdrawals": "bridge_db_withdrawals",
    "get_resumable_withdrawals": "bridge_db_withdrawals",
    "get_awaiting_depth_withdrawals": "bridge_db_withdrawals",
    "update_withdrawal_block": "bridge_db_withdrawals",
    "update_withdrawal_pricing": "bridge_db_withdrawals",
    "get_all_withdrawals": "bridge_db_withdrawals",
    "update_withdrawal_status": "bridge_db_withdrawals",
    "_WITHDRAWAL_ETH_COMMITTED_STATUSES": "bridge_db_withdrawals",
    "get_withdrawal_eth_committed_since": "bridge_db_withdrawals",
    "record_release_attempt": "bridge_db_withdrawals",
    "update_release_attempt": "bridge_db_withdrawals",
    "get_release_attempts": "bridge_db_withdrawals",
    # bridge_sell_quotes / bridge_sell_locks
    "_SELL_QUOTE_KEYS": "bridge_db_sell",
    "_SELL_LOCK_KEYS": "bridge_db_sell",
    "_SELL_RESERVE_STATUSES": "bridge_db_sell",
    "_SELL_ETH_COMMITTED_STATUSES": "bridge_db_sell",
    "_SELL_OPEN_STATUSES": "bridge_db_sell",
    "insert_sell_quote": "bridge_db_sell",
    "get_sell_quote": "bridge_db_sell",
    "get_all_sell_quotes": "bridge_db_sell",
    "count_open_sell_quotes": "bridge_db_sell",
    "get_latest_sell_quote_by_shop": "bridge_db_sell",
    "update_sell_quote_status": "bridge_db_sell",
    "insert_sell_lock": "bridge_db_sell",
    "get_sell_lock_by_ait_tx_hash": "bridge_db_sell",
    "get_sell_lock_by_id": "bridge_db_sell",
    "get_sell_lock_by_quote_id": "bridge_db_sell",
    "get_sell_quotes_by_status": "bridge_db_sell",
    "get_sell_locks_by_status": "bridge_db_sell",
    "get_open_sell_locks": "bridge_db_sell",
    "get_sell_inflight_sweep": "bridge_db_sell",
    "get_all_sell_locks": "bridge_db_sell",
    "update_sell_lock_status": "bridge_db_sell",
    "get_sell_pending_eth_reserve": "bridge_db_sell",
    "get_sell_eth_committed_since": "bridge_db_sell",
    # exchange_settlements + exchange_monitor_marks
    "_EXCHANGE_SETTLEMENT_STATUSES": "bridge_db_settlement",
    "_EXCHANGE_SETTLEMENT_OPEN_STATUSES": "bridge_db_settlement",
    "_EXCHANGE_SETTLEMENT_INFLIGHT_SWEEP_STATUSES": "bridge_db_settlement",
    "_EXCHANGE_SETTLEMENT_RESERVE_STATUSES": "bridge_db_settlement",
    "insert_exchange_settlement": "bridge_db_settlement",
    "_row_to_settlement": "bridge_db_settlement",
    "_SETTLEMENT_SELECT_COLS": "bridge_db_settlement",
    "get_exchange_settlement": "bridge_db_settlement",
    "get_open_exchange_settlements": "bridge_db_settlement",
    "get_exchange_inflight_sweep": "bridge_db_settlement",
    "get_exchange_pending_eth_reserve": "bridge_db_settlement",
    "_EXCHANGE_ETH_COMMITTED_STATUSES": "bridge_db_settlement",
    "get_exchange_eth_committed_since": "bridge_db_settlement",
    "list_exchange_settlements": "bridge_db_settlement",
    "update_exchange_settlement": "bridge_db_settlement",
    "insert_monitor_mark": "bridge_db_settlement",
    "update_monitor_mark": "bridge_db_settlement",
    "monitor_mark": "bridge_db_settlement",
}

# Public surface for ``from wallet_app.bridge.bridge_db import *`` — core
# names plus every public name the submodules moved out (the names are
# statically bound under TYPE_CHECKING above, so this literal is checkable).
__all__ = [
    "DB_PATH",
    "init_db",
    "try_eth_release_lock",
    "release_eth_release_lock",
    "insert_deposit",
    "insert_exchange_prepay_deposit",
    "get_pending_deposits",
    "update_deposit_status",
    "update_deposit_tx_hash",
    "get_deposit_by_tx_hash",
    "get_deposit_by_id",
    "get_all_deposits",
    "get_deposits_by_recipient",
    "insert_price_history",
    "get_all_time_average",
    "cleanup_old_prices",
    "insert_withdrawal",
    "get_withdrawal_by_ait_tx_hash",
    "get_pending_withdrawals",
    "get_resumable_withdrawals",
    "get_awaiting_depth_withdrawals",
    "update_withdrawal_block",
    "update_withdrawal_pricing",
    "get_all_withdrawals",
    "update_withdrawal_status",
    "get_withdrawal_eth_committed_since",
    "record_release_attempt",
    "update_release_attempt",
    "get_release_attempts",
    "insert_sell_quote",
    "get_sell_quote",
    "get_all_sell_quotes",
    "count_open_sell_quotes",
    "get_latest_sell_quote_by_shop",
    "update_sell_quote_status",
    "insert_sell_lock",
    "get_sell_lock_by_ait_tx_hash",
    "get_sell_lock_by_id",
    "get_sell_lock_by_quote_id",
    "get_sell_quotes_by_status",
    "get_sell_locks_by_status",
    "get_open_sell_locks",
    "get_sell_inflight_sweep",
    "get_all_sell_locks",
    "update_sell_lock_status",
    "get_sell_pending_eth_reserve",
    "get_sell_eth_committed_since",
    "insert_exchange_settlement",
    "get_exchange_settlement",
    "get_open_exchange_settlements",
    "get_exchange_inflight_sweep",
    "get_exchange_pending_eth_reserve",
    "get_exchange_eth_committed_since",
    "list_exchange_settlements",
    "update_exchange_settlement",
    "insert_monitor_mark",
    "update_monitor_mark",
    "monitor_mark",
]

_PACKAGE = __name__.rpartition(".")[0] or "wallet_app.bridge"


def __getattr__(name: str) -> Any:
    """Lazily re-export a name that lives in a ``bridge_db_<domain>`` module."""
    from importlib import import_module

    module = _NAME_TO_MODULE.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", _PACKAGE), name)
    globals()[name] = value
    return value
