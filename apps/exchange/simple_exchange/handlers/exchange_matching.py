"""Order matching — ``match_orders``/``_match_orders_in_txn`` plus the
module-level match helpers (candidate scan, fill math, trade insert,
persist).

Split out of ``exchange.py`` verbatim; ``ExchangeMixin`` in the facade
inherits this mixin and re-exports the module-level helpers.
"""

from datetime import UTC, datetime
from decimal import Decimal

from aitbc.utils.decimal import to_decimal as _to_decimal

from ..db import connect_db, to_ticks
from .exchange_helpers import (
    _apply_exchange_fee,
    _close_buy_debit,
    _commit_trade_cost,
    _settlement_enabled,
    get_db_path,
)


class ExchangeMatchingMixin:
    """In-transaction order matching against the open book."""

    def _match_orders_in_txn(
        self, cursor, order: dict, head_height: int | None = None, guard_address: str | None = None
    ) -> None:
        """Match a new order against existing open orders within an existing transaction.

        B1 fix: This runs within the caller's transaction (which holds the
        write lock via ``BEGIN IMMEDIATE``). The matching read+update is
        atomic with the order insert, preventing concurrent double-matching.

        B2 fix: All monetary arithmetic uses Decimal. Values are stored as
        TEXT (Decimal-as-string) in the database.

        ETH-11 phase 2: when ``head_height`` is given, open orders whose
        ``expiry_height`` has passed are flipped to ``expired`` first (the
        lazy expiry from design section 6). When ``guard_address`` is given,
        rows belonging to the same address are never matched (self-match
        prevention — design sections 6/9). When no explicit guard is passed,
        the order's own ``user_address`` guards the match — the unsigned
        legacy path gets the same string-equality self-match protection
        (#1695); distinct addresses are unaffected either way.

        Args:
            cursor: SQLite cursor within an active transaction.
            order: The new order dict (mutated in place with updated filled/remaining/status).
            head_height: current chain height for the lazy expiry sweep.
            guard_address: canonical address that must not be its own counterparty.
        """
        if not order or "order_type" not in order:
            return
        if guard_address is None:
            guard_address = order.get("user_address") or None

        # ETH-8 phase 3 (dark): under settlement, unfunded orders never
        # enter the matchable set and candidates must be 'funded' too.
        settlement = _settlement_enabled()
        if settlement and order.get("funded_state") != "funded":
            return

        new_type = order["order_type"]
        new_price = _to_decimal(order["price"])
        new_price_ticks = to_ticks(new_price)
        new_remaining = _to_decimal(order["remaining"])
        new_id = order.get("id")

        if head_height is not None:
            self._expire_open_orders(cursor, head_height)

        # Find matching orders (opposite side, price-compatible). Comparisons
        # and ordering run on the integer tick columns — the TEXT price column
        # compares lexically ('10' < '2') and must never appear in a predicate.
        # id ASC is the deterministic tiebreak; created_at is second-granularity
        # and ties on orders placed within the same second. The self-match
        # guard compares case-insensitively: stored addresses may be legacy
        # free-text, signed orders write the canonical EIP-55 form.
        self_guard = "AND (user_address IS NULL OR LOWER(user_address) != LOWER(?))" if guard_address else ""
        # Flag-off must run the phase-2 query byte-for-byte: the lock column
        # and the funded predicate only exist in the statement when the
        # settlement flag is on.
        lock_col = ", locked_ticks" if settlement else ""
        funded_pred = "AND funded_state = 'funded'" if settlement else ""
        matching_orders = _match_candidates(
            cursor, new_type, new_price_ticks, self_guard, guard_address, lock_col, funded_pred
        )

        for match_row in matching_orders:
            if new_remaining <= 0:
                break

            trade_qty = _fill_from_match(cursor, order, match_row, new_remaining, new_type, new_id, settlement)
            if trade_qty is None:
                continue

            # Update the new order (in-memory)
            new_remaining -= trade_qty
            order["filled"] = str(_to_decimal(order.get("filled", 0)) + trade_qty)
            order["remaining"] = str(new_remaining)

            if new_remaining <= 0:
                order["status"] = "filled"

        # Update the new order in the database (B2: store as TEXT)
        _persist_new_order(cursor, order, new_id, new_type, settlement)

    def match_orders(self, order: dict) -> None:
        """Match a new order against existing open orders (standalone transaction).

        This is a backward-compatible wrapper that opens its own transaction
        with ``BEGIN IMMEDIATE``. Prefer ``_match_orders_in_txn`` when the
        caller already holds a transaction (e.g., ``handle_place_order``).

        B1 fix: Uses ``BEGIN IMMEDIATE`` to acquire the write lock before
        reading open orders, preventing concurrent double-matching.

        B3 fix: Connection is closed via try/finally.
        """
        if not order or "order_type" not in order:
            return

        conn = connect_db(get_db_path(), timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            self._match_orders_in_txn(cursor, order)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _match_candidates(cursor, new_type, new_price_ticks, self_guard, guard_address, lock_col, funded_pred):
    """Opposite-side open orders at compatible tick prices, within the
    caller's transaction. The flag-off query is byte-for-byte the phase-2
    statement — lock_col/funded_pred only exist when settlement is on."""
    if new_type == "BUY":
        # Match against SELL orders with price <= our buy price
        # lock_col/self_guard/funded_pred are fixed literal fragments, never input
        cursor.execute(
            f"""
            SELECT id, order_type, amount, price, total, filled, remaining, status, created_at, user_address, tx_hash{lock_col}
            FROM orders
            WHERE order_type = 'SELL' AND status = 'open' AND price_ticks <= ? {self_guard} {funded_pred}
            ORDER BY price_ticks ASC, id ASC
            """,  # nosec
            (new_price_ticks, guard_address) if guard_address else (new_price_ticks,),
        )
    else:
        # Match against BUY orders with price >= our sell price
        # same fixed fragments
        cursor.execute(
            f"""
            SELECT id, order_type, amount, price, total, filled, remaining, status, created_at, user_address, tx_hash{lock_col}
            FROM orders
            WHERE order_type = 'BUY' AND status = 'open' AND price_ticks >= ? {self_guard} {funded_pred}
            ORDER BY price_ticks DESC, id ASC
            """,  # nosec
            (new_price_ticks, guard_address) if guard_address else (new_price_ticks,),
        )
    return cursor.fetchall()


def _match_fee_ait(order: dict, match_filled: Decimal, trade_qty: Decimal, new_type: str, settlement: bool) -> Decimal:
    """Per-fill fee: the DIFFERENCE of the seller's cumulative fee at its
    running filled total — independently quantized fills could sum to more
    than fee(amount) and outrun the escrow lock; the cumulative form can
    never exceed fee(sell_amount). Flag-off: plain per-trade fee."""
    if settlement:
        sell_filled_before = _to_decimal(order.get("filled", 0)) if new_type == "SELL" else match_filled
        return _apply_exchange_fee(sell_filled_before + trade_qty)[0] - _apply_exchange_fee(sell_filled_before)[0]
    fee_ait, _net_ait = _apply_exchange_fee(trade_qty)
    return fee_ait


def _sell_lock_covers(match_row, match_remaining: Decimal) -> bool:
    """A candidate SELL's remaining fills must stay inside its recorded
    escrow lock (amount + fee). Funding enforces the cover at lock time;
    this is the in-scan safety net — a row that fails it awaits the
    monitor's backing_expired event."""
    locked = match_row[11]
    required_ticks = to_ticks(match_remaining + _apply_exchange_fee(match_remaining)[0])
    return locked is not None and locked >= required_ticks


def _insert_matched_trade(
    cursor,
    settlement: bool,
    trade_qty: Decimal,
    match_price: Decimal,
    trade_total: Decimal,
    fee_ait: Decimal,
    buyer_addr,
    seller_addr,
    new_id,
    new_type: str,
    match_id,
) -> None:
    """Buyer/seller attribution (phase 2): the tape row names the two sides
    so the page can print node labels. fee_ait records the EXCHANGE_FEE_PCT
    knob's value at match time (default 0 on testnet, DECIDED 14 Oct) —
    phase 2 moves no funds, this is the ledger column only. Phase 3: the
    trade row names its parent orders and enters the settlement machine at
    'locked'; the buyer's cost commits to the prepaid debit in the same
    transaction."""
    if settlement:
        buy_order = new_id if new_type == "BUY" else match_id
        sell_order = new_id if new_type == "SELL" else match_id
        cursor.execute(
            """
            INSERT INTO trades (amount, price, total, created_at, buyer_address, seller_address,
                                fee_ait, buy_order_id, sell_order_id, settlement_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'locked')
            """,
            (
                str(trade_qty),
                str(match_price),
                str(trade_total),
                datetime.now(UTC).isoformat(),
                buyer_addr,
                seller_addr,
                str(fee_ait),
                buy_order,
                sell_order,
            ),
        )
        _commit_trade_cost(cursor, buy_order, trade_total)
    else:
        cursor.execute(
            """
            INSERT INTO trades (amount, price, total, created_at, buyer_address, seller_address, fee_ait)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(trade_qty),
                str(match_price),
                str(trade_total),
                datetime.now(UTC).isoformat(),
                buyer_addr,
                seller_addr,
                str(fee_ait),
            ),
        )


def _fill_from_match(
    cursor, order: dict, match_row, new_remaining: Decimal, new_type: str, new_id, settlement: bool
) -> Decimal | None:
    """One fill against a matching row, inside the caller's transaction.
    Returns the traded quantity, or None when the row can't fill."""
    match_id = match_row[0]
    match_remaining = _to_decimal(match_row[6])
    match_price = _to_decimal(match_row[3])
    match_filled = _to_decimal(match_row[5])

    if match_remaining <= 0:
        return None

    if settlement and match_row[1] == "SELL" and not _sell_lock_covers(match_row, match_remaining):
        return None

    # B2: Calculate trade quantity with Decimal (exact arithmetic)
    trade_qty = min(new_remaining, match_remaining)
    trade_total = trade_qty * match_price
    fee_ait = _match_fee_ait(order, match_filled, trade_qty, new_type, settlement)
    buyer_addr = order.get("user_address") if new_type == "BUY" else match_row[9]
    seller_addr = match_row[9] if new_type == "BUY" else order.get("user_address")
    _insert_matched_trade(
        cursor,
        settlement,
        trade_qty,
        match_price,
        trade_total,
        fee_ait,
        buyer_addr,
        seller_addr,
        new_id,
        new_type,
        match_id,
    )

    # Update the matching order (B2: Decimal arithmetic, store as TEXT)
    new_match_filled = match_filled + trade_qty
    new_match_remaining = match_remaining - trade_qty
    new_match_status = "filled" if new_match_remaining <= 0 else "open"

    cursor.execute(
        """
        UPDATE orders SET filled = ?, remaining = ?, status = ?,
            filled_ticks = ?, remaining_ticks = ?
        WHERE id = ?
        """,
        (
            str(new_match_filled),
            str(new_match_remaining),
            new_match_status,
            to_ticks(new_match_filled),
            to_ticks(new_match_remaining),
            match_id,
        ),
    )

    # A candidate BUY that just filled releases the uncommitted
    # residual of its prepaid debit in the same transaction.
    if settlement and match_row[1] == "BUY" and new_match_status == "filled":
        _close_buy_debit(cursor, match_id)
    return trade_qty


def _persist_new_order(cursor, order: dict, new_id, new_type: str, settlement: bool) -> None:
    """Write back the inbound order's filled/remaining after matching; an
    inbound BUY that filled releases its uncommitted debit residual."""
    if not new_id:
        return
    cursor.execute(
        """
        UPDATE orders SET filled = ?, remaining = ?, status = ?,
            filled_ticks = ?, remaining_ticks = ?
        WHERE id = ?
        """,
        (
            str(order.get("filled", 0)),
            str(order.get("remaining", 0)),
            order.get("status", "open"),
            to_ticks(_to_decimal(order.get("filled", 0))),
            to_ticks(_to_decimal(order.get("remaining", 0))),
            new_id,
        ),
    )
    if settlement and new_type == "BUY" and order.get("status") == "filled":
        _close_buy_debit(cursor, new_id)
