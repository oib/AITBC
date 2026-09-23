"""Regression tests for integer-tick order matching.

The exchange stores money as TEXT (Decimal-as-string) for exact arithmetic, but
matching and the order book used to compare those strings directly in SQL —
and '10' < '2' lexically. A buy limited to 2 could fill a sell priced 10, and
a buy limited to 10 never saw a sell priced 2. Comparisons and ordering now run
on INTEGER tick columns (value * 10**8) written alongside the TEXT columns.
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
        exchange_db._MARKETPLACE_OFFERS_SCHEMA,
        exchange_db._MARKETPLACE_ORDERS_SCHEMA,
    ):
        conn.execute(stmt)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def legacy_db(tmp_path):
    """Temporary exchange DB with the pre-tick schema (TEXT money, no tick cols)."""
    db_path = str(tmp_path / "exchange_legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE orders (
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
    """)
    conn.commit()
    conn.close()
    return db_path


def _insert_order(db_path, order_type, amount, price, *, filled="0", status="open"):
    """Insert an order writing TEXT + tick columns the way the handler does."""
    from apps.exchange.simple_exchange.db import to_ticks

    amount_d, price_d, filled_d = Decimal(amount), Decimal(price), Decimal(filled)
    total_d = amount_d * price_d
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO orders (order_type, amount, price, total, filled, remaining, status, user_address,"
        " amount_ticks, price_ticks, filled_ticks, remaining_ticks)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            order_type,
            str(amount_d),
            str(price_d),
            str(total_d),
            str(filled_d),
            str(amount_d),
            status,
            "0xuser",
            to_ticks(amount_d),
            to_ticks(price_d),
            to_ticks(filled_d),
            to_ticks(amount_d),
        ),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def _run_match(db_path, order):
    """Run the real _match_orders_in_txn inside its own BEGIN IMMEDIATE txn."""
    from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

    handler = MagicMock(spec=ExchangeMixin)
    handler._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(handler, ExchangeMixin)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("BEGIN IMMEDIATE")
    cursor = conn.cursor()
    handler._match_orders_in_txn(cursor, order)
    conn.commit()
    conn.close()


def _trades(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT amount, price, total FROM trades").fetchall()
    conn.close()
    return rows


def _new_order(order_type, amount, price, order_id=None):
    return {
        "id": order_id,
        "order_type": order_type,
        "amount": amount,
        "price": price,
        "total": str(Decimal(amount) * Decimal(price)),
        "filled": "0",
        "remaining": amount,
        "status": "open",
    }


class TestToTicks:
    """Fail-closed Decimal -> tick conversion."""

    def test_exact_values(self):
        from apps.exchange.simple_exchange.db import TICKS_PER_UNIT, to_ticks

        assert to_ticks(Decimal("2")) == 2 * TICKS_PER_UNIT
        assert to_ticks(Decimal("0.00000001")) == 1
        assert to_ticks(Decimal("2.00000000")) == 2 * TICKS_PER_UNIT
        assert to_ticks(Decimal("0")) == 0

    @pytest.mark.parametrize("bad", ["1.000000001", "0.000000005", "123.456789012", "1e-9"])
    def test_rejects_unrepresentable(self, bad):
        from apps.exchange.simple_exchange.db import to_ticks

        with pytest.raises(ValueError):
            to_ticks(Decimal(bad))

    @pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
    def test_rejects_non_finite(self, bad):
        from apps.exchange.simple_exchange.db import to_ticks

        with pytest.raises(ValueError):
            to_ticks(Decimal(bad))

    def test_rejects_int64_overflow(self):
        from apps.exchange.simple_exchange.db import to_ticks

        with pytest.raises(ValueError):
            to_ticks(Decimal("1e20"))


class TestLexicalMatchingRegression:
    """The two reproduced defects: TEXT comparison put '10' below '2'."""

    def test_buy_two_does_not_match_sell_ten(self, temp_db):
        """A buy limited to 2 must not fill a sell priced 10."""
        _insert_order(temp_db, "SELL", "5", "10")
        _run_match(temp_db, _new_order("BUY", "3", "2"))
        assert _trades(temp_db) == []

    def test_buy_ten_matches_sell_two(self, temp_db):
        """A buy limited to 10 must fill a sell priced 2."""
        _insert_order(temp_db, "SELL", "5", "2")
        _run_match(temp_db, _new_order("BUY", "3", "10"))
        trades = _trades(temp_db)
        assert len(trades) == 1
        assert Decimal(trades[0][1]) == Decimal("2")  # fills at the sell price
        assert Decimal(trades[0][0]) == Decimal("3")

    def test_cheapest_sell_matches_first(self, temp_db):
        """Price-time priority: buy 10 meets sells at 10, 2, 9 -> takes 2 first."""
        _insert_order(temp_db, "SELL", "5", "10")
        _insert_order(temp_db, "SELL", "5", "2")
        _insert_order(temp_db, "SELL", "5", "9")
        _run_match(temp_db, _new_order("BUY", "4", "10"))
        trades = _trades(temp_db)
        assert [Decimal(t[1]) for t in trades] == [Decimal("2")]

    def test_highest_buy_matches_first(self, temp_db):
        """Sell side: a sell at 5 meets buys at 10, 2, 9 -> takes 10 first."""
        _insert_order(temp_db, "BUY", "5", "10")
        _insert_order(temp_db, "BUY", "5", "2")
        _insert_order(temp_db, "BUY", "5", "9")
        _run_match(temp_db, _new_order("SELL", "4", "5"))
        trades = _trades(temp_db)
        assert [Decimal(t[1]) for t in trades] == [Decimal("10")]

    def test_equivalent_decimal_representations_match(self, temp_db):
        """'2' and '2.00000000' are the same price and must match."""
        _insert_order(temp_db, "SELL", "5", "2.00000000")
        _run_match(temp_db, _new_order("BUY", "3", "2"))
        assert len(_trades(temp_db)) == 1

    def test_multi_digit_ordering(self, temp_db):
        """Order book ordering across digit lengths: 2 < 9 < 10 < 100."""
        for price in ("10", "2", "100", "9"):
            _insert_order(temp_db, "SELL", "1", price)
        buy = _new_order("BUY", "4", "100")
        _run_match(temp_db, buy)
        trades = _trades(temp_db)
        assert [Decimal(t[1]) for t in trades] == [Decimal("2"), Decimal("9"), Decimal("10"), Decimal("100")]


class TestPlaceOrderBoundary:
    """The API boundary rejects values the tick columns cannot represent."""

    def _handler(self, body):
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

        handler = MagicMock(spec=ExchangeMixin)
        handler._require_api_key = MagicMock(return_value=True)
        handler._read_json_body = MagicMock(return_value=body)
        handler.send_error = MagicMock()
        handler.send_json_response = MagicMock()
        handler.handle_place_order = ExchangeMixin.handle_place_order.__get__(handler, ExchangeMixin)
        handler._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(handler, ExchangeMixin)
        return handler

    def test_subtick_amount_rejected(self, temp_db):
        handler = self._handler({"order_type": "BUY", "amount": "1.000000001", "price": "2", "user_address": "0xuser"})
        with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=temp_db):
            handler.handle_place_order()
        handler.send_error.assert_called_once()
        assert handler.send_error.call_args[0][0] == 400

    def test_subtick_product_accepted(self, temp_db):
        """amount*price with >8dp is fine: total stays exact TEXT, never SQL-compared."""
        handler = self._handler({"order_type": "BUY", "amount": "0.00000003", "price": "0.00000001", "user_address": "0xuser"})
        with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=temp_db):
            handler.handle_place_order()
        handler.send_error.assert_not_called()
        conn = sqlite3.connect(temp_db)
        row = conn.execute("SELECT total, amount_ticks, price_ticks FROM orders").fetchone()
        conn.close()
        assert row[0] == "3E-16"  # exact product, kept as TEXT
        assert row[1:] == (3, 1)

    def test_valid_order_persists_ticks(self, temp_db):
        handler = self._handler({"order_type": "BUY", "amount": "5", "price": "1.5", "user_address": "0xuser"})
        with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=temp_db):
            handler.handle_place_order()
        assert handler.send_json_response.called
        conn = sqlite3.connect(temp_db)
        row = conn.execute("SELECT amount_ticks, price_ticks, remaining_ticks, total FROM orders").fetchone()
        conn.close()
        assert row == (500_000_000, 150_000_000, 500_000_000, "7.5")


class TestTickMigration:
    """init_db adds and backfills tick columns fail-closed."""

    def test_backfills_existing_rows(self, legacy_db):
        from apps.exchange.simple_exchange.db import TICKS_PER_UNIT, init_db

        conn = sqlite3.connect(legacy_db)
        conn.execute(
            "INSERT INTO orders (order_type, amount, price, total, filled, remaining) VALUES (?, ?, ?, ?, ?, ?)",
            ("SELL", "10", "1.5", "15", "0", "10"),
        )
        conn.execute(
            "INSERT INTO orders (order_type, amount, price, total, filled, remaining) VALUES (?, ?, ?, ?, ?, ?)",
            ("BUY", "3", "0.00000001", "0.00000003", "0", "3"),
        )
        conn.commit()
        conn.close()

        with patch("apps.exchange.simple_exchange.db.get_db_path", return_value=legacy_db):
            init_db()

        conn = sqlite3.connect(legacy_db)
        rows = conn.execute("SELECT price_ticks, amount_ticks, remaining_ticks FROM orders ORDER BY id").fetchall()
        conn.close()
        assert rows[0] == (int(Decimal("1.5") * TICKS_PER_UNIT), 10 * TICKS_PER_UNIT, 10 * TICKS_PER_UNIT)
        assert rows[1] == (1, 3 * TICKS_PER_UNIT, 3 * TICKS_PER_UNIT)

    def test_fail_closed_on_unrepresentable(self, legacy_db):
        from apps.exchange.simple_exchange.db import TickMigrationError, init_db

        conn = sqlite3.connect(legacy_db)
        conn.execute(
            "INSERT INTO orders (order_type, amount, price, total, filled, remaining) VALUES (?, ?, ?, ?, ?, ?)",
            ("SELL", "1", "1.000000001", "1.000000001", "0", "1"),
        )
        conn.commit()
        conn.close()

        with (
            patch("apps.exchange.simple_exchange.db.get_db_path", return_value=legacy_db),
            pytest.raises(TickMigrationError),
        ):
            init_db()

        # Rollback left the schema and data untouched: no tick columns, row intact.
        conn = sqlite3.connect(legacy_db)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
        row = conn.execute("SELECT price FROM orders").fetchone()
        conn.close()
        assert "price_ticks" not in cols
        assert row[0] == "1.000000001"

    def test_resumes_after_interrupted_migration(self, legacy_db):
        """Columns present but unbackfilled (interrupted run) get filled."""
        from apps.exchange.simple_exchange.db import init_db

        conn = sqlite3.connect(legacy_db)
        conn.execute("ALTER TABLE orders ADD COLUMN price_ticks INTEGER")
        conn.execute("ALTER TABLE orders ADD COLUMN amount_ticks INTEGER")
        conn.execute("ALTER TABLE orders ADD COLUMN filled_ticks INTEGER")
        conn.execute("ALTER TABLE orders ADD COLUMN remaining_ticks INTEGER")
        conn.execute(
            "INSERT INTO orders (order_type, amount, price, total, filled, remaining) VALUES (?, ?, ?, ?, ?, ?)",
            ("SELL", "4", "2", "8", "0", "4"),
        )
        conn.commit()
        conn.close()

        with patch("apps.exchange.simple_exchange.db.get_db_path", return_value=legacy_db):
            init_db()

        conn = sqlite3.connect(legacy_db)
        row = conn.execute("SELECT price_ticks, remaining_ticks FROM orders").fetchone()
        conn.close()
        assert row == (200_000_000, 400_000_000)


class TestOrderbookOrdering:
    """get_orderbook orders by ticks, not by the TEXT price."""

    def test_sells_sorted_numerically(self, temp_db):
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

        for price in ("10", "2", "100"):
            _insert_order(temp_db, "SELL", "1", price)
        for price in ("10", "2", "100"):
            _insert_order(temp_db, "BUY", "1", price)

        handler = MagicMock(spec=ExchangeMixin)
        handler.send_json_response = MagicMock()
        handler.get_orderbook = ExchangeMixin.get_orderbook.__get__(handler, ExchangeMixin)
        with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=temp_db):
            handler.get_orderbook()

        payload = handler.send_json_response.call_args[0][0]
        assert [Decimal(o["price"]) for o in payload["sells"]] == [Decimal("2"), Decimal("10"), Decimal("100")]
        assert [Decimal(o["price"]) for o in payload["buys"]] == [Decimal("100"), Decimal("10"), Decimal("2")]
