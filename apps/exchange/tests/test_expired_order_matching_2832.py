"""#2832: expired orders must not stay matchable.

The lazy expiry sweep only ran when the match call site supplied a
``head_height`` — the unsigned/legacy path passed none, so orders past
their ``expiry_height`` stayed matchable forever, and read paths never
swept or filtered them at all. The match path now resolves the chain
head itself when the caller has none, ``_match_candidates`` carries an
expiry predicate as defense in depth, and the order book hides
expired-but-unswept rows.
"""

import sqlite3
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_db(tmp_path):
    """Temporary exchange DB built from the real schema constants."""
    from apps.exchange.simple_exchange import db as exchange_db

    db_path = str(tmp_path / "exchange.db")
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
    return db_path


def _insert_order(db_path, order_type, amount, price, *, expiry_height=None, status="open", user="0xuser"):
    """Insert an order with TEXT + tick columns the way the handler does."""
    from apps.exchange.simple_exchange.db import to_ticks

    amount_d, price_d = Decimal(amount), Decimal(price)
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO orders (order_type, amount, price, total, filled, remaining, status, user_address,"
        " amount_ticks, price_ticks, filled_ticks, remaining_ticks, expiry_height)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            order_type,
            str(amount_d),
            str(price_d),
            str(amount_d * price_d),
            "0",
            str(amount_d),
            status,
            user,
            to_ticks(amount_d),
            to_ticks(price_d),
            0,
            to_ticks(amount_d),
            expiry_height,
        ),
    )
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def _match(db_path, order, *, head=None):
    """Run the real _match_orders_in_txn inside BEGIN IMMEDIATE, headless
    by default — the unsigned-path shape that used to skip expiry."""
    from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin
    from apps.exchange.simple_exchange.handlers.exchange_orders import ExchangeOrdersMixin

    handler = MagicMock(spec=ExchangeMixin)
    handler._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(handler, ExchangeMixin)
    # Real sweep — spec'd mocks would no-op it and hide the flip.
    handler._expire_open_orders = ExchangeOrdersMixin._expire_open_orders
    handler._chain_head_height = MagicMock(return_value=head)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("BEGIN IMMEDIATE")
    cursor = conn.cursor()
    handler._match_orders_in_txn(cursor, order)
    conn.commit()
    conn.close()


def _new_order(order_type, amount, price):
    return {
        "order_type": order_type,
        "amount": amount,
        "price": price,
        "total": str(Decimal(amount) * Decimal(price)),
        "filled": "0",
        "remaining": amount,
        "status": "open",
    }


def _trades(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT amount, price, total FROM trades").fetchall()
    conn.close()
    return rows


def _order_status(db_path, order_id):
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return row[0]


class TestExpiredOrdersNotMatchable:
    def test_headless_match_expires_past_expiry_height(self, temp_db):
        """The unsigned path passes no head — the match must resolve one
        itself. An expired SELL at a compatible price must not fill."""
        sell_id = _insert_order(temp_db, "SELL", "10", "5", expiry_height=50)
        _match(temp_db, _new_order("BUY", "5", "10"), head=100)
        assert _trades(temp_db) == []
        assert _order_status(temp_db, sell_id) == "expired"

    def test_unexpired_order_still_matches(self, temp_db):
        """Guard against over-filtering: expiry_height above head matches."""
        _insert_order(temp_db, "SELL", "10", "5", expiry_height=500)
        _match(temp_db, _new_order("BUY", "5", "10"), head=100)
        assert len(_trades(temp_db)) == 1

    def test_explicit_head_still_expires(self, temp_db):
        """The signed path's explicit head keeps working identically."""
        sell_id = _insert_order(temp_db, "SELL", "10", "5", expiry_height=50)
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin
        from apps.exchange.simple_exchange.handlers.exchange_orders import ExchangeOrdersMixin

        handler = MagicMock(spec=ExchangeMixin)
        handler._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(handler, ExchangeMixin)
        handler._expire_open_orders = ExchangeOrdersMixin._expire_open_orders
        handler._chain_head_height = MagicMock(return_value=None)
        conn = sqlite3.connect(temp_db, timeout=30)
        conn.execute("BEGIN IMMEDIATE")
        handler._match_orders_in_txn(conn.cursor(), _new_order("BUY", "5", "10"), head_height=100)
        conn.commit()
        conn.close()
        assert _trades(temp_db) == []
        assert _order_status(temp_db, sell_id) == "expired"

    def test_null_expiry_never_expires(self, temp_db):
        """#1554 residual: NULL expiry_height orders are exempt by design."""
        _insert_order(temp_db, "SELL", "10", "5", expiry_height=None)
        _match(temp_db, _new_order("BUY", "5", "10"), head=100)
        assert len(_trades(temp_db)) == 1


class TestOrderbookHidesExpired:
    def _book(self, temp_db, head):
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

        handler = MagicMock(spec=ExchangeMixin)
        handler.send_json_response = MagicMock()
        handler._orderbook_row = ExchangeMixin._orderbook_row.__get__(handler, ExchangeMixin)
        handler._registry_labels = MagicMock(return_value={})
        handler._ait_eth_band = MagicMock(return_value=None)
        handler._chain_head_height = MagicMock(return_value=head)
        handler.get_orderbook = ExchangeMixin.get_orderbook.__get__(handler, ExchangeMixin)
        with patch("apps.exchange.simple_exchange.handlers.exchange_queries.get_db_path", return_value=temp_db):
            handler.get_orderbook()
        return handler.send_json_response.call_args[0][0]

    def test_expired_rows_hidden_from_depth(self, temp_db):
        _insert_order(temp_db, "SELL", "10", "5", expiry_height=50, user="0x" + "a" * 40)
        _insert_order(temp_db, "BUY", "10", "5", expiry_height=500, user="0x" + "b" * 40)
        book = self._book(temp_db, head=100)
        assert book["sells"] == []
        assert len(book["buys"]) == 1

    def test_dead_rpc_shows_book_unfiltered(self, temp_db):
        _insert_order(temp_db, "SELL", "10", "5", expiry_height=50, user="0x" + "a" * 40)
        book = self._book(temp_db, head=None)
        assert len(book["sells"]) == 1
