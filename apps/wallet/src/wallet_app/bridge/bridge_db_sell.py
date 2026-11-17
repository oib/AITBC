"""ETH-10 escrowed AIT->ETH sell flow — quote and lock tables.

Split out of ``bridge_db.py`` (pure code motion): ``bridge_sell_quotes`` and
``bridge_sell_locks`` CRUD, status vocabularies and the float reserve /
committed-since sums. Connection handling, ``DB_PATH`` and the schema live in
``bridge_db`` — helpers are imported back from that module so a monkeypatched
``bridge_db.DB_PATH`` keeps applying here.
"""

from collections.abc import Collection
from decimal import Decimal
from typing import Any

from wallet_app.utc_time import utc_now_iso

from .bridge_db import _connect_db, _money_str


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
            _money_str(eth_amount),
            feed_age_seconds,
            expires_at,
            utc_now_iso(),
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
        # _SELL_QUOTE_KEYS is a module constant; every value is bound via ?
        "SELECT " + ", ".join(_SELL_QUOTE_KEYS) + " FROM bridge_sell_quotes WHERE id = ?",  # nosec
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
        # _SELL_QUOTE_KEYS is a module constant; every value is bound via ?
        "SELECT " + ", ".join(_SELL_QUOTE_KEYS) + " FROM bridge_sell_quotes ORDER BY created_at DESC LIMIT ? OFFSET ?",  # nosec
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
        # _SELL_QUOTE_KEYS is a module constant; every value is bound via ?
        "SELECT "  # nosec
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
            None if eth_amount is None else _money_str(eth_amount),
            status,
            locked_height,
            utc_now_iso(),
            error,
            utc_now_iso(),
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
        # _SELL_LOCK_KEYS is a module constant; every value is bound via ?
        "SELECT " + ", ".join(_SELL_LOCK_KEYS) + " FROM bridge_sell_locks WHERE ait_tx_hash = ?",  # nosec
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
        # _SELL_LOCK_KEYS is a module constant; every value is bound via ?
        "SELECT " + ", ".join(_SELL_LOCK_KEYS) + " FROM bridge_sell_locks WHERE id = ?",  # nosec
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
    # _SELL_LOCK_KEYS is a module constant; every value is bound via ?
    query = "SELECT " + ", ".join(_SELL_LOCK_KEYS) + " FROM bridge_sell_locks WHERE quote_id = ?"  # nosec
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
        # _SELL_LOCK_KEYS is a module constant; every value is bound via ?
        "SELECT " + ", ".join(_SELL_LOCK_KEYS) + " FROM bridge_sell_locks ORDER BY created_at DESC LIMIT ? OFFSET ?",  # nosec
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
    expected_statuses: Collection[str] | None = None,
) -> bool:
    """Update a sell lock's status and optional lifecycle fields.

    ``expected_statuses`` is the CAS predicate (#1918), same shape as
    update_deposit_status (#1796): when given, the UPDATE only lands while
    the row still sits in one of those statuses, so a stale writer cannot
    overwrite a state that has already moved on. rowcount 0 -> False.
    """
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
        # timestamp_field is a hardcoded literal above, never caller input
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
        """  # nosec
        params: tuple = (
            status,
            utc_now_iso(),
            quote_id,
            shop_eth_address,
            None if eth_amount is None else _money_str(eth_amount),
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
            None if eth_amount is None else _money_str(eth_amount),
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
    if expected_statuses:
        # Both query variants end `WHERE ait_tx_hash = ?`; the CAS clause
        # appends after it. Placeholders are literal '?' per expected value.
        expected = tuple(expected_statuses)
        query += f" AND status IN ({', '.join('?' for _ in expected)})"
        params = (*params, *expected)
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
        # placeholders are literal '?' generated from _SELL_RESERVE_STATUSES; all values bound
        f"SELECT COALESCE(SUM(eth_amount), 0) FROM bridge_sell_locks WHERE status IN ({placeholders})",  # nosec
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
    # placeholders are literal '?' generated from _SELL_ETH_COMMITTED_STATUSES; all values bound
    cursor.execute(
        f"""SELECT COALESCE(SUM(eth_amount), 0) FROM bridge_sell_locks
            WHERE (status IN ({placeholders})
                   OR (status = 'written_off' AND eth_tx_hash IS NOT NULL))
              AND released_at >= ?""",  # nosec
        (*_SELL_ETH_COMMITTED_STATUSES, since_iso),
    )
    total = cursor.fetchone()[0]
    conn.close()
    return Decimal(str(total)) if total is not None else Decimal("0")
