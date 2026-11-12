"""SQLite storage for bridge deposit tracking.

Writes into ``eth_deposits`` — the same table the wallet service reads for
/v1/bridge/* routes and the public website. Column names differ between the
two services' vocabularies, so every query aliases the wallet schema back to
the monitor's field names; callers see one consistent dict shape.
"""

import logging
import os
import sqlite3
import uuid
from collections.abc import Collection
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

# AITBC_DATA_DIR wins over the operator-facing DATA_DIR override (admin.py
# documents bare DATA_DIR for pointing admin commands at a copied DB): the
# namespaced var is what test isolation and service env files set, so a suite
# must bind the scratch dir, not the live deposits file.
DATA_DIR = os.getenv("AITBC_DATA_DIR", os.getenv("DATA_DIR", "/var/lib/aitbc"))
DB_PATH = (os.getenv("BRIDGE_DEPOSITS_DB") or "").strip() or os.path.join(DATA_DIR, "data", "bridge_deposits.db")


def try_admin_lock() -> int | None:
    """Exclusive non-blocking flock on ``<ledger>.admin.lock``.

    The payout slot's one-envelope-in-flight rule is check-then-act: the
    in-flight probe and the SUBMITTED row write must not interleave with
    another writer's. Admin mutations (``admin.py``) hold this lock for
    their whole command; the monitor sweep takes it around its own
    payout decision+submit so a ``manual-payout`` cannot race a sweep
    payout onto the same nonce. The lock file derives from ``DB_PATH``
    at call time, so ``BRIDGE_DEPOSITS_DB``/``DATA_DIR`` overrides (and
    test monkeypatching) relocate it with the ledger.

    Returns the lock fd (close to release) or None when another holder
    has it — the sweep treats that as "skip this payout pass, retry next
    cycle"; one-shot admin commands refuse outright.
    """
    import fcntl

    fd = os.open(f"{DB_PATH}.admin.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


class BridgeDepositStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PENDING_RETRY = "pending_retry"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"
    # Terminal write-off: funds received but deliberately unsettled
    # (e.g. deposit to a keyless wallet on testnet). error_message is
    # mandatory — a write-off without a written reason is rejected.
    WRITTEN_OFF = "written_off"
    # Terminal funding: ETH sent to the bridge wallet from a whitelisted
    # operator funding source (BRIDGE_FUNDING_SOURCES). Recorded in the
    # ledger for the audit trail but owed no payout.
    FUNDING = "funding"
    # Terminal prepay: ETH carrying an EXCHANGE_DEPOSIT:<addr> tag — routed
    # to the buyer's prepaid exchange balance by the wallet-side settlement
    # monitor (ETH-8 phase 3), never minted as AIT. Only written under
    # EXCHANGE_SETTLEMENT_ENABLED; outside the payout vocabulary so no
    # poll can pick it up.
    EXCHANGE_PREPAY = "exchange_prepay"


# eth_deposits status vocabulary map (#1919 ETH-DEPOSITS-VOCAB-1) — this
# table is shared with wallet_app.bridge.bridge_db, whose
# _ETH_DEPOSIT_STATUSES vocabulary is
# {pending, verified, completed, exchange_prepay, rejected, failed}.
# The two vocabularies overlap only partially:
#   shared:        pending, completed, failed, exchange_prepay
#   monitor-only:  processing, pending_retry, submitted, written_off, funding
#   wallet-only:   verified, rejected
# 'verified' means the wallet auto-mint verify CAS already won — its
# TRANSFER may be in flight or may already have landed, so the monitor
# must NEVER pay or retry these rows (double-mint). 'rejected' is the
# wallet's operator-terminal state. Neither belongs to a monitor
# worklist; the stranded-row detector below is the visibility net.
#
# Terminal for every worklist — settled, or deliberately unresolved
# (includes the wallet side's 'rejected').
DEPOSIT_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        BridgeDepositStatus.COMPLETED.value,
        BridgeDepositStatus.FAILED.value,
        BridgeDepositStatus.WRITTEN_OFF.value,
        BridgeDepositStatus.FUNDING.value,
        BridgeDepositStatus.EXCHANGE_PREPAY.value,
        "rejected",
    }
)
# Owned by an active monitor worklist — the retry queue reads
# PENDING_RETRY and the seal sweep reads SUBMITTED. Old rows in these
# statuses are covered by the queue-depth / stuck-payout alerts, not the
# stranded detector.
DEPOSIT_WORKLIST_STATUSES: frozenset[str] = frozenset(
    {
        BridgeDepositStatus.PENDING_RETRY.value,
        BridgeDepositStatus.SUBMITTED.value,
    }
)
# Wallet-side lifecycle states: outside BridgeDepositStatus entirely.
# 'verified' is a mint-in-flight intermediate (possibly already paid
# wallet-side); 'rejected' is operator-terminal. The monitor treats both
# as foreign-owned — never pays, never retries — and the stranded
# detector alerts when one outlives its horizon.
WALLET_LIFECYCLE_STATUSES: frozenset[str] = frozenset({"verified", "rejected"})


def _coerce_deposit_status(status: object) -> BridgeDepositStatus:
    """Normalize a status write to the enum (#1919).

    Accepts a BridgeDepositStatus member or its ``.value`` string;
    rejects anything outside the monitor vocabulary — including the
    wallet-side states 'verified'/'rejected', which would park the row
    outside every worklist with no owner. Lookup is by value, not
    isinstance, so a member of a reloaded module generation still
    coerces (StrEnum members compare as their value string).
    """
    try:
        return BridgeDepositStatus(status)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        raise ValueError(f"monitor writes only BridgeDepositStatus values, got {status!r}") from None


def valid_ait_recipient(addr: object) -> bool:
    """True when the value is a syntactically valid AIT recipient address."""
    return (
        isinstance(addr, str)
        and addr.startswith("0x")
        and len(addr) == 42
        and all(c in "0123456789abcdefABCDEF" for c in addr[2:])
    )


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
           envelope_hash,
           signed_tx,
           submitted_height,
           rebroadcast_count,
           status,
           created_at,
           completed_at   AS processed_at,
           verified_at,
           error_message,
           retry_count,
           next_retry_at,
           deposit_address
    FROM eth_deposits
"""


def init_db() -> None:
    """Initialize bridge deposits database."""
    canonical_dir = os.path.realpath(os.path.join(DATA_DIR, "data"))
    if not os.path.realpath(DB_PATH).startswith(canonical_dir + os.sep):
        logging.getLogger(__name__).warning(
            "bridge ledger path %s is outside %s — expected under DATA_DIR/data; check BRIDGE_DEPOSITS_DB",
            DB_PATH,
            canonical_dir,
        )
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with closing(_connect_db()) as conn:
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

        # PRAGMA-first migration: "database is locked" is also an
        # OperationalError, so swallowing ALTER errors wholesale can leave a
        # column missing — after which every deposit read fails until restart.
        # Check columns up front, and on failure re-check before forgiving.
        cursor.execute("PRAGMA table_info(eth_deposits)")
        columns = {row[1] for row in cursor.fetchall()}
        for column, col_type in [
            ("eth_usd_price", "TEXT"),
            ("ait_usd_price", "TEXT"),
            ("error_message", "TEXT"),
            ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
            ("next_retry_at", "TEXT"),
            # SUBMITTED-era lifecycle columns: the signed payout envelope is
            # stored before it is broadcast so a crash can never orphan it.
            ("signed_tx", "TEXT"),
            # envelope_hash is the payout hash derived from the stored
            # signed envelope; ait_tx_hash is what the chain knows (server
            # canonical if the RPC reported a different normalization).
            ("envelope_hash", "TEXT"),
            ("submitted_height", "INTEGER"),
            ("rebroadcast_count", "INTEGER NOT NULL DEFAULT 0"),
            # B13: the bridge wallet that received the deposit. NULL on
            # pre-column rows — reported "address unknown" by the reconcile
            # and treated as the configured current wallet. No backfill.
            ("deposit_address", "TEXT"),
        ]:
            if column in columns:
                continue
            try:
                cursor.execute(f"ALTER TABLE eth_deposits ADD COLUMN {column} {col_type}")
            except sqlite3.OperationalError:
                cursor.execute("PRAGMA table_info(eth_deposits)")
                if column not in {row[1] for row in cursor.fetchall()}:
                    raise

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bridge_cursor (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            )
        """)

        # B13/BR-6: outbound ETH legs (refunds, withdrawals, gas) — additive
        # table written at the ``from == bridge_eth_address`` scan branch so
        # the reconcile can close the books from the ledger alone instead of
        # an operator-supplied --onchain document. See
        # docs/ops/bridge-outbound-ledger-migration-runbook.md.
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


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """WAL + busy_timeout parity with the wallet's bridge_db._connect_db and
    aitbc_chain.database._set_sqlite_pragmas — this file has two writer
    services and previously ran rollback-journal mode (#1559).
    busy_timeout is per-connection; journal_mode is persistent but
    re-asserting it on an already-WAL file is a no-op read."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")


def _connect_db() -> sqlite3.Connection:
    """Open a bridge deposits connection with the shared WAL pragmas."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    _apply_pragmas(conn)
    return conn


def _db_connection() -> sqlite3.Connection:
    """Get a fresh database connection with row factory enabled."""
    conn = _connect_db()
    conn.row_factory = sqlite3.Row
    return conn


def create_deposit(
    eth_tx_hash: str,
    eth_from_address: str,
    eth_amount: str,
    ait_recipient: str,
    status: BridgeDepositStatus = BridgeDepositStatus.PENDING,
    deposit_address: str | None = None,
) -> str | None:
    """Create a new bridge deposit record.

    amount_ait starts at '0' — the oracle-priced value lands via
    update_deposit once crediting is attempted. Returns the generated id,
    or None when the tx hash is already recorded.

    ``eth_tx_hash`` is stored canonicalized — both deposit writers (this
    monitor's unprefixed ``tx.hash.hex()`` and the wallet-side monitor's
    ``0x``-prefixed RPC hash) must land on one key or the UNIQUE dedupe
    lets the same deposit pay twice (issue #668). ``status`` must be a
    BridgeDepositStatus — the monitor never writes wallet-vocabulary
    states ('verified', 'rejected'); a stray string would park the row
    outside every worklist with no owner (#1919).
    """
    status = _coerce_deposit_status(status)
    eth_tx_hash = canon_tx_hash(eth_tx_hash)
    deposit_id = f"deposit_{uuid.uuid4().hex[:8]}"
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO eth_deposits
                (id, tx_hash, from_address, recipient, amount_eth, amount_ait, status, created_at, deposit_address)
                VALUES (?, ?, ?, ?, ?, '0', ?, ?, ?)
                """,
                (
                    deposit_id,
                    eth_tx_hash,
                    eth_from_address,
                    ait_recipient,
                    eth_amount,
                    status,
                    datetime.now(UTC).isoformat(),
                    deposit_address,
                ),
            )
            conn.commit()
            return deposit_id
        except sqlite3.IntegrityError:
            # Transaction already exists
            return None


# Fields a caller may explicitly reset to NULL via update_deposit(clear_fields=).
# Passing None as a value never clears a column — it means "no change".
_CLEARABLE_COLUMNS: dict[str, str] = {
    "ait_amount": "amount_ait",
    "eth_usd_price": "eth_usd_price",
    "ait_usd_price": "ait_usd_price",
    "ait_tx_hash": "ait_tx_hash",
    "error_message": "error_message",
    "next_retry_at": "next_retry_at",
    "signed_tx": "signed_tx",
    "envelope_hash": "envelope_hash",
    "submitted_height": "submitted_height",
}


def _validate_update_args(
    status: BridgeDepositStatus | None, error_message: str | None, clear_fields: list[str] | None
) -> None:
    """Reject invalid update combinations before touching the DB."""
    if status == BridgeDepositStatus.WRITTEN_OFF and not error_message:
        raise ValueError("WRITTEN_OFF requires a written reason (error_message)")
    for f in clear_fields or []:
        if f not in _CLEARABLE_COLUMNS:
            raise ValueError(f"cannot clear unknown field {f!r}")


def _build_update_query(
    updates: list[str], expected_statuses: Collection[BridgeDepositStatus | str] | None
) -> tuple[str, list[Any]] | None:
    """Assemble the UPDATE ... WHERE clause. Returns (query, extra_params)
    or None when there is nothing to update."""
    if expected_statuses:
        expected = tuple(s.value if isinstance(s, BridgeDepositStatus) else str(s) for s in expected_statuses)
        query = (
            f"UPDATE eth_deposits SET {', '.join(updates)} "  # nosec
            f"WHERE lower(tx_hash) IN (?, ?) AND status IN ({', '.join('?' for _ in expected)})"
        )
        return query, list(expected)
    if not updates:
        return None
    # every `updates` entry is a hardcoded "column = ?" literal above; values are bound via params
    # lower() + both spellings: legacy rows may hold a bare or mixed-case hash (#668)
    query = f"UPDATE eth_deposits SET {', '.join(updates)} WHERE lower(tx_hash) IN (?, ?)"  # nosec
    return query, []


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
    signed_tx: str | None = None,
    envelope_hash: str | None = None,
    submitted_height: int | None = None,
    rebroadcast_count: int | None = None,
    clear_fields: list[str] | None = None,
    expected_statuses: Collection[BridgeDepositStatus | str] | None = None,
) -> bool:
    """Update bridge deposit record.

    ``expected_statuses`` is the CAS predicate (#1839): when given, the
    UPDATE only lands while the row still sits in one of those statuses,
    so a stale writer cannot resurrect a row another writer already moved
    terminal (e.g. flip a written-off deposit back to SUBMITTED). rowcount
    0 -> False. Status values may be passed as the enum or its ``.value``.
    """
    if status is not None:
        # #1919: wallet-vocabulary states ('verified', 'rejected') are not
        # monitor writes — a stray string must fail loudly here, not land
        # a row no worklist owns. Coerce by value so a valid .value string
        # and a reloaded-generation member both normalize to the enum.
        status = _coerce_deposit_status(status)
    _validate_update_args(status, error_message, clear_fields)
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()

        updates = []
        params: list[Any] = []

        for f in clear_fields or []:
            updates.append(f"{_CLEARABLE_COLUMNS[f]} = NULL")

        for column, value in (
            ("amount_ait", ait_amount),
            ("eth_usd_price", eth_usd_price),
            ("ait_usd_price", ait_usd_price),
            ("ait_tx_hash", ait_tx_hash),
            ("envelope_hash", envelope_hash),
            ("signed_tx", signed_tx),
            ("submitted_height", submitted_height),
            ("rebroadcast_count", rebroadcast_count),
            ("error_message", error_message),
            ("retry_count", retry_count),
            ("next_retry_at", next_retry_at),
        ):
            if value is not None:
                updates.append(f"{column} = ?")
                params.append(value)
        if status is not None:
            updates.append("status = ?")
            params.append(status.value)

        if status is not None and status in (
            BridgeDepositStatus.COMPLETED,
            BridgeDepositStatus.FAILED,
            BridgeDepositStatus.WRITTEN_OFF,
        ):
            updates.append("completed_at = ?")
            params.append(datetime.now(UTC).isoformat())

        params.extend(_tx_hash_keys(eth_tx_hash))

        built = _build_update_query(updates, expected_statuses)
        if built is None:
            return False
        query, extra_params = built
        params.extend(extra_params)

        if updates:
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

        return False


def get_deposit(eth_tx_hash: str) -> dict[str, Any] | None:
    """Get deposit by transaction hash — any spelling (issue #668: callers
    pass web3-bare or RPC ``0x`` forms; legacy rows may carry either)."""
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()

        cursor.execute(f"{_DEPOSIT_SELECT} WHERE lower(tx_hash) IN (?, ?)", _tx_hash_keys(eth_tx_hash))
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


def count_pending_retry() -> int:
    """PENDING_RETRY rows including those whose next_retry_at is still ahead."""
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM eth_deposits WHERE status = ?",
            (BridgeDepositStatus.PENDING_RETRY.value,),
        )
        return int(cursor.fetchone()[0])


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


def sum_committed_ait() -> Decimal:
    """AIT still owed by every non-terminal row.

    pending/processing/pending_retry/submitted rows all carry an amount
    the float is committed to pay (a submitted envelope may still seal;
    a queued row will attempt payout). The balance alone overstates what
    is free — the float check and the payout cap need the committed sum.
    """
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT amount_ait FROM eth_deposits WHERE status IN (?, ?, ?, ?)",
            (
                BridgeDepositStatus.PENDING.value,
                BridgeDepositStatus.PROCESSING.value,
                BridgeDepositStatus.PENDING_RETRY.value,
                BridgeDepositStatus.SUBMITTED.value,
            ),
        )
        total = Decimal(0)
        for (amt,) in cursor.fetchall():
            try:
                total += Decimal(str(amt or "0"))
            except ArithmeticError:
                continue  # unparseable amount — count nothing rather than die
        return total


def get_submitted_deposits() -> list[dict[str, Any]]:
    """Get deposits whose payout was broadcast but not yet confirmed sealed.

    These rows own a signed payout envelope; the confirmation sweep checks
    them each poll — they are never re-signed.
    """
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"{_DEPOSIT_SELECT} WHERE status = ? ORDER BY created_at ASC",
            (BridgeDepositStatus.SUBMITTED.value,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_stranded_deposits(cutoff_iso: str) -> list[dict[str, Any]]:
    """Non-terminal rows older than ``cutoff_iso`` that no worklist owns (#1919).

    The block scan never revisits old txs, the retry queue reads only
    ``pending_retry`` and the seal sweep only ``submitted`` — so a row
    left in ``pending``/``processing`` by a crash, flipped to a
    wallet-vocabulary state (``verified`` by the wallet admin route), or
    carrying an unrecognized status is invisible to every scan: funds
    received, payout owed or deliberately unresolved, and no alert.
    Terminal statuses and worklist-owned statuses are excluded — the
    latter have their own health alerts. Resolution is always an operator
    decision (write-off / manual-payout / wallet-side completion), never
    an automatic pay: a ``verified`` row's wallet-side TRANSFER may
    already have landed.
    """
    excluded = sorted(DEPOSIT_TERMINAL_STATUSES | DEPOSIT_WORKLIST_STATUSES)
    placeholders = ", ".join("?" for _ in excluded)
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            # excluded values are hardcoded literals bound as parameters;
            # identifiers come from the fixed _DEPOSIT_SELECT projection.
            f"{_DEPOSIT_SELECT} WHERE (created_at IS NULL OR created_at < ?) "  # nosec
            f"AND status NOT IN ({placeholders}) ORDER BY created_at ASC",
            (cutoff_iso, *excluded),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def fail_stale_manual_pending(cutoff_iso: str) -> int:
    """Terminally fail stale ``manual-*`` rows stuck in PENDING (#1433).

    ``admin.py manual-payout`` mints synthetic rows (``manual-<ts>``) that
    only the admin command itself advances to SUBMITTED. A crash between
    ``create_deposit`` and the SUBMITTED write leaves a PENDING row no
    sweep owns: the retry queue reads only ``pending_retry`` and would
    reprice ``eth_amount='0'`` forever, and nothing else selects PENDING.
    Rows younger than ``cutoff_iso`` may be mid-command — only stale ones
    are failed. The ``manual-%`` prefix is the only safe selector: the
    wallet side shares this table and owns every other 'pending' row.
    """
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE eth_deposits
            SET status = ?, error_message = ?, completed_at = ?
            WHERE status = ? AND tx_hash LIKE 'manual-%' AND created_at < ?
            """,
            (
                BridgeDepositStatus.FAILED.value,
                "orphaned manual payout row — process died before submit; re-issue manual-payout",
                datetime.now(UTC).isoformat(),
                BridgeDepositStatus.PENDING.value,
                cutoff_iso,
            ),
        )
        conn.commit()
        return cursor.rowcount


def record_outbound(
    tx_hash: str,
    to_address: str,
    value_wei: int,
    block_height: int,
    kind: str,
    gas_wei: int | None = None,
    matched_deposit_tx: str | None = None,
    note: str | None = None,
) -> bool:
    """Ledger one outbound ETH leg sent from the bridge wallet (B13).

    ``kind`` is ``refund`` | ``withdrawal`` | ``unidentified``; ``value_eth``
    is stored as a decimal ETH string like ``eth_deposits.amount_eth``.
    INSERT OR IGNORE on the tx-hash PRIMARY KEY makes a re-scan of the same
    block harmless. Returns True when a row was written. The hash is
    stored canonicalized — a re-scan through a differently-spelled source
    must dedupe, not double-ledger (issue #668).
    """
    tx_hash = canon_tx_hash(tx_hash)
    if matched_deposit_tx is not None:
        matched_deposit_tx = canon_tx_hash(matched_deposit_tx)
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO bridge_outbound
            (tx_hash, to_address, value_eth, gas_wei, block_height, kind, matched_deposit_tx, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx_hash,
                to_address,
                str(Decimal(value_wei) / Decimal(10**18)),
                gas_wei,
                block_height,
                kind,
                matched_deposit_tx,
                note,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0


def depositor_tx_hashes() -> dict[str, str]:
    """Lowercased ``from_address`` -> ``tx_hash`` of every recorded deposit.

    The refund-recipient set for outbound classification: a send from the
    bridge wallet back to a recorded depositor is a refund, and the deposit
    tx hash is the match evidence.
    """
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT from_address, tx_hash FROM eth_deposits")
        return {str(addr).lower(): canon_tx_hash(str(tx)) for addr, tx in cursor.fetchall()}


# Fixed literals only — never user input — so the identifier interpolation
# in release_sources() below is safe and carries its nosec for B608.
_RELEASE_SOURCES = (
    ("eth_withdrawals", ""),
    ("bridge_sell_locks", "bridge_sell_locks release"),
    ("exchange_settlements", "exchange_settlements release"),
)


_HEX_CHARS = frozenset("0123456789abcdef")


def canon_tx_hash(value: str) -> str:
    """Canonical ``0x``-prefixed lowercase form for tx-hash joins.

    web3's ``tx.hash.hex()`` is unprefixed while the wallet side writes
    ``eth_tx_hash`` rows ``0x``-prefixed — joins between them must
    normalize both sides or release-leg sends fall through to
    ``unidentified`` (issue #652) and the two deposit writers produce
    distinct spellings of the same key, defeating the UNIQUE dedupe
    (issue #668). Non-hex synthetic ids (``manual-…`` payout rows) are
    not hashes and pass through unchanged.
    """
    s = str(value)
    body = s[2:] if s[:2].lower() == "0x" else s
    lowered = body.lower()
    if not lowered or any(c not in _HEX_CHARS for c in lowered):
        return s
    return "0x" + lowered


def _tx_hash_keys(value: str) -> tuple[str, str]:
    """Stored spellings a ``tx_hash`` lookup must cover: the canonical
    ``0x``-lower form plus the legacy unprefixed form written before the
    #668 storage-boundary normalization. Pair with ``lower(tx_hash)`` in
    the WHERE clause so mixed-case legacy rows also match."""
    canon = canon_tx_hash(value)
    bare = canon[2:] if canon.startswith("0x") else canon
    # The WHERE clause compares lower(tx_hash), so the bound parameters must
    # be lowercase as well — a mixed-case synthetic id like manual-…T…
    # otherwise matches its own row in INSERT but never in UPDATE/SELECT,
    # orphaning the payout envelope updates silently (rowcount is unchecked).
    return (canon.lower(), bare.lower())


def release_sources() -> dict[str, str]:
    """Lowercased ``eth_tx_hash`` -> source label for each release-leg table.

    Sell locks and exchange settlements drive payouts too; a send whose hash
    appears there is a ``withdrawal`` with the source named, not unidentified.
    Each table may be absent (the wallet side bootstraps them) — missing is
    just fewer rows, never an error.
    """
    out: dict[str, str] = {}
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        for table, label in _RELEASE_SOURCES:
            try:
                cursor.execute(f"SELECT eth_tx_hash FROM {table} WHERE eth_tx_hash IS NOT NULL")  # nosec
            except sqlite3.OperationalError:
                continue
            for (h,) in cursor.fetchall():
                out.setdefault(canon_tx_hash(h), label)
    return out


def release_tx_hashes() -> set[str]:
    """Lowercased ``eth_tx_hash`` values across all release-leg tables
    (``eth_withdrawals``, ``bridge_sell_locks``, ``exchange_settlements``).
    Empty where the wallet side has not bootstrapped a table yet.
    """
    return set(release_sources())


def outbound_totals_wei() -> dict[str, int]:
    """Ledger-derived outbound terms for the reconcile (design section 5)."""
    with closing(_db_connection()) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT kind, SUM(CAST(value_eth AS REAL)), SUM(gas_wei) FROM bridge_outbound GROUP BY kind")
        except sqlite3.OperationalError:
            return {"refund": 0, "withdrawal": 0, "unidentified": 0, "gas_wei": 0}
        terms: dict[str, int] = {"refund": 0, "withdrawal": 0, "unidentified": 0}
        gas_total = 0
        for kind, value_eth, gas_wei in cursor.fetchall():
            kind = str(kind)
            # self_send rows return their value to the same wallet — only
            # their gas is outbound. Unknown kinds still count (a hand-written
            # kind must not be silently dropped from the books).
            if kind != "self_send":
                terms[kind] = int(Decimal(str(value_eth or 0)) * Decimal(10**18))
            gas_total += int(gas_wei or 0)
        terms["gas_wei"] = gas_total
        return terms


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
