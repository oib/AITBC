"""Order-book invariant stress tests (#v11 item 15).

Drives ``ExchangeMixin._match_orders_in_txn`` directly — the same code path
``handle_place_order``/``_commit_signed_order`` run inside BEGIN IMMEDIATE —
through randomized order flow and a threaded double-match race, asserting
the book's conservation invariants after every step:

* ``filled + remaining == amount`` and ``remaining >= 0`` for every order;
* ``status == 'filled'`` iff ``remaining == 0`` (open orders always have
  positive remaining);
* every trade row has positive amount/price and ``total == amount * price``;
* with the signed-path self-match guard, no trade pairs an address with
  itself;
* two concurrent crossing orders can never over-fill a resting order —
  BEGIN IMMEDIATE serializes the read+update (the B1 invariant).
"""

from __future__ import annotations

import random
import sqlite3
import threading
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.exchange.simple_exchange import db as exchange_db
from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin, _row_to_order
from apps.exchange.simple_exchange.handlers.exchange import connect_db


@pytest.fixture
def book_db(tmp_path, monkeypatch):
    """Real exchange schema on a temp file; settlement flag stays off."""
    monkeypatch.delenv("EXCHANGE_SETTLEMENT_ENABLED", raising=False)
    db_path = str(tmp_path / "exchange_invariants.db")
    conn = sqlite3.connect(db_path)
    for stmt in (
        exchange_db._TRADES_SCHEMA,
        exchange_db._ORDERS_SCHEMA,
        exchange_db._NODE_REGISTRY_SCHEMA,
        exchange_db._ORDER_NONCES_SCHEMA,
        exchange_db._MARKET_OFFERS_SCHEMA,
        exchange_db._MARKET_ORDERS_SCHEMA,
    ):
        conn.execute(stmt)
    conn.commit()
    conn.close()
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _place(db_path: str, order_type: str, amount: str, price: str, address: str | None) -> int:
    """Insert + match exactly like the place-order handlers do."""
    amount_d, price_d = Decimal(amount), Decimal(price)
    conn = connect_db(db_path, timeout=30)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (order_type, amount, price, total, remaining, user_address, tx_hash,
                                amount_ticks, price_ticks, filled_ticks, remaining_ticks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_type,
                str(amount_d),
                str(price_d),
                str(amount_d * price_d),
                str(amount_d),
                address,
                "",
                exchange_db.to_ticks(amount_d),
                exchange_db.to_ticks(price_d),
                0,
                exchange_db.to_ticks(amount_d),
            ),
        )
        order_id = cursor.lastrowid
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = _row_to_order(cursor.fetchone())
        # head_height=None keeps the legacy no-expiry sweep; guard_address is
        # the signed-path self-match guard.
        ExchangeMixin._match_orders_in_txn(MagicMock(), cursor, order, guard_address=address)
        conn.commit()
        return int(order_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _check_invariants(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        orders = conn.execute(
            "SELECT id, order_type, amount, price, total, filled, remaining, status, user_address FROM orders"
        ).fetchall()
        for oid, _otype, amount, _price, _total, filled, remaining, status, _addr in orders:
            amount_d, filled_d, remaining_d = Decimal(amount), Decimal(filled), Decimal(remaining)
            assert filled_d + remaining_d == amount_d, f"order {oid}: filled+remaining != amount"
            assert remaining_d >= 0, f"order {oid}: negative remaining {remaining_d}"
            if status == "filled":
                assert remaining_d == 0, f"order {oid}: filled but remaining={remaining_d}"
            elif status == "open":
                assert remaining_d > 0, f"order {oid}: open with remaining={remaining_d}"
        trades = conn.execute("SELECT amount, price, total, buyer_address, seller_address FROM trades").fetchall()
        for amount, price, total, buyer, seller in trades:
            amount_d, price_d, total_d = Decimal(amount), Decimal(price), Decimal(total)
            assert amount_d > 0 and price_d > 0 and total_d > 0, f"non-positive trade {amount}x{price}"
            assert total_d == amount_d * price_d, f"trade total {total_d} != {amount_d}*{price_d}"
            if buyer and seller:
                assert buyer.lower() != seller.lower(), f"self-trade {buyer} == {seller}"
    finally:
        conn.close()


def test_random_order_flow_preserves_invariants(book_db):
    """300 randomized placements across 4 addresses; invariants hold after
    every single placement, not just at the end."""
    rng = random.Random(20261110)
    addrs = [f"0x{i:040x}" for i in range(4)]
    prices = ["1", "2", "3", "5", "10", "100"]
    amounts = ["1", "2", "5", "10"]
    for _ in range(300):
        _place(
            book_db,
            rng.choice(["BUY", "SELL"]),
            rng.choice(amounts),
            rng.choice(prices),
            rng.choice(addrs),
        )
        _check_invariants(book_db)


def test_concurrent_crossing_orders_never_overfill(book_db):
    """B1 invariant: a resting SELL of 10 @ 5 meets two concurrent BUYs of
    6 @ 5 — the write lock serializes matching so total fills are exactly 10,
    never 12."""
    seller = "0x" + "aa" * 20
    resting_id = _place(book_db, "SELL", "10", "5", seller)

    buyers = ["0x" + "b1" * 10, "0x" + "b2" * 10]
    results: dict[str, int] = {}
    barrier = threading.Barrier(2)

    def buy(i: int) -> None:
        barrier.wait(timeout=10)
        results[buyers[i]] = _place(book_db, "BUY", "6", "5", buyers[i])

    threads = [threading.Thread(target=buy, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    _check_invariants(book_db)
    conn = sqlite3.connect(book_db)
    try:
        row = conn.execute("SELECT filled, remaining, status FROM orders WHERE id = ?", (resting_id,)).fetchone()
        assert row is not None
        filled, remaining, status = Decimal(row[0]), Decimal(row[1]), row[2]
        assert filled == Decimal("10"), f"resting order over/under-filled: {filled}"
        assert remaining == 0 and status == "filled"
        # Both buys together bought exactly the resting 10 — 4 units of buy
        # volume must rest open, proving no phantom fill.
        buy_filled_d = sum(Decimal(r[0]) for r in conn.execute("SELECT filled FROM orders WHERE order_type='BUY'"))
        assert buy_filled_d == Decimal("10"), f"buy side filled {buy_filled_d}, expected 10"
    finally:
        conn.close()
