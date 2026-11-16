"""ETH-8 exchange trade settlement ledger and monitor marks.

Split out of ``bridge_db.py`` (pure code motion): ``exchange_settlements``
(the authoritative exchange-trade state machine), its float reserve /
committed-since sums, and the monitor-private ``exchange_monitor_marks``
dedupe table. Connection handling, ``DB_PATH`` and the schema live in
``bridge_db`` — helpers are imported back from that module so a monkeypatched
``bridge_db.DB_PATH`` keeps applying here.
"""

from collections.abc import Collection
from decimal import Decimal
from typing import Any

from wallet_app.utc_time import utc_now_iso

from .bridge_db import _connect_db


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
            utc_now_iso(),
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
        # column list is a hardcoded constant
        f"SELECT {', '.join(_SETTLEMENT_SELECT_COLS)} FROM exchange_settlements WHERE kind = ? AND ref_id = ?",  # nosec
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
        # placeholders are literal '?' generated from the constant; values bound
        f"SELECT {', '.join(_SETTLEMENT_SELECT_COLS)} FROM exchange_settlements WHERE status IN ({placeholders}) ORDER BY created_at",  # nosec
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
        # same literal-placeholder pattern
        f"SELECT {', '.join(_SETTLEMENT_SELECT_COLS)} FROM exchange_settlements WHERE status IN ({placeholders}) LIMIT 1",  # nosec
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
        # same literal-placeholder pattern
        f"SELECT eth_amount FROM exchange_settlements WHERE status IN ({placeholders})",  # nosec
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
    # same literal-placeholder pattern
    cursor.execute(
        f"""SELECT eth_amount FROM exchange_settlements
            WHERE status IN ({placeholders})
              AND released_at >= ?""",  # nosec
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
        # column list/keywords are literals; every value is bound
        f"SELECT {', '.join(_SETTLEMENT_SELECT_COLS)} FROM exchange_settlements{where}"  # nosec
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
    expected_statuses: Collection[str] | None = None,
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

    ``expected_statuses`` is the CAS predicate (#1918), same shape as
    update_deposit_status (#1796): when given, the UPDATE only lands while
    the row still sits in one of those statuses. rowcount 0 -> False.
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
        # timestamp_field is a hardcoded literal above, never caller input
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
        """  # nosec
        params: tuple = (
            status,
            utc_now_iso(),
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
    if expected_statuses:
        # Both query variants end `WHERE id = ?`; the CAS clause appends
        # after it. Placeholders are literal '?' per expected value.
        expected = tuple(expected_statuses)
        query += f" AND status IN ({', '.join('?' for _ in expected)})"  # nosec
        params = (*params, *expected)
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
