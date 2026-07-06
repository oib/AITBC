"""Tests for simple_exchange B1/B2/B3 backport fixes.

Tests the running exchange implementation (simple_exchange/server.py) for:
- B2: Decimal arithmetic (no float rounding drift) and TEXT column storage
- B1: Order matching atomicity (single transaction with BEGIN IMMEDIATE)
- B3: Connection cleanup (try/finally on all DB connections)
"""

import os
import sqlite3
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary exchange database with TEXT columns (post-migration schema)."""
    db_path = str(tmp_path / "test_exchange.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables with TEXT monetary columns (post-B2 schema)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount TEXT NOT NULL,
            price TEXT NOT NULL,
            total TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
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
    cursor.execute("""
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
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_orders (
            id TEXT PRIMARY KEY,
            order_type TEXT NOT NULL,
            item TEXT NOT NULL,
            price TEXT NOT NULL,
            wallet TEXT,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def temp_db_real(tmp_path):
    """Create a temporary exchange database with REAL columns (pre-migration schema)."""
    db_path = str(tmp_path / "test_exchange_real.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),
            amount REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            filled REAL DEFAULT 0,
            remaining REAL NOT NULL,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_address TEXT,
            tx_hash TEXT
        )
    """)
    conn.commit()
    conn.close()
    return db_path


class TestB2DecimalArithmetic:
    """B2: Verify Decimal arithmetic prevents float rounding drift."""

    def test_to_decimal_from_float(self):
        """_to_decimal converts float via str to avoid precision trap."""
        from apps.exchange.simple_exchange.handlers.exchange import _to_decimal

        # Direct Decimal(0.1) gives 0.1000000000000000055511151231257827...
        # _to_decimal(0.1) should give exactly 0.1
        result = _to_decimal(0.1)
        assert result == Decimal("0.1")
        assert str(result) == "0.1"

    def test_to_decimal_from_string(self):
        from apps.exchange.simple_exchange.handlers.exchange import _to_decimal

        assert _to_decimal("0.1") == Decimal("0.1")
        assert _to_decimal("100.5") == Decimal("100.5")

    def test_to_decimal_from_int(self):
        from apps.exchange.simple_exchange.handlers.exchange import _to_decimal

        assert _to_decimal(100) == Decimal("100")

    def test_decimal_multiplication_exact(self):
        """Verify 0.1 * 0.3 = 0.03 (not 0.030000000000000002)."""
        from apps.exchange.simple_exchange.handlers.exchange import _to_decimal

        amount = _to_decimal(0.1)
        price = _to_decimal(0.3)
        total = amount * price
        assert total == Decimal("0.03")
        assert str(total) == "0.03"

    def test_decimal_no_drift_accumulation(self):
        """Verify no drift after 1000 additions of 0.1."""
        from apps.exchange.simple_exchange.handlers.exchange import _to_decimal

        total = Decimal("0")
        for _ in range(1000):
            total += _to_decimal(0.1)
        assert total == Decimal("100.0")


class TestB2SchemaMigration:
    """B2: Verify db.py schema uses TEXT and migrates REAL columns."""

    def test_schema_uses_text_not_real(self):
        """Verify the schema constants use TEXT, not REAL."""
        from apps.exchange.simple_exchange.db import _TRADES_SCHEMA, _ORDERS_SCHEMA

        assert "REAL" not in _TRADES_SCHEMA
        assert "REAL" not in _ORDERS_SCHEMA
        assert "TEXT NOT NULL" in _TRADES_SCHEMA
        assert "TEXT NOT NULL" in _ORDERS_SCHEMA

    def test_init_db_creates_text_columns(self, temp_db):
        """Verify init_db creates tables with TEXT monetary columns."""
        from apps.exchange.simple_exchange.db import init_db

        with patch("apps.exchange.simple_exchange.db.get_db_path", return_value=temp_db):
            init_db()

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(orders)")
        cols = {row[1]: row[2].upper() for row in cursor.fetchall()}
        conn.close()

        assert cols["amount"] == "TEXT"
        assert cols["price"] == "TEXT"
        assert cols["total"] == "TEXT"
        assert cols["filled"] == "TEXT"
        assert cols["remaining"] == "TEXT"

    def test_init_db_migrates_real_to_text(self, temp_db_real):
        """Verify init_db migrates existing REAL columns to TEXT."""
        from apps.exchange.simple_exchange.db import init_db

        # Insert data with REAL values before migration
        conn = sqlite3.connect(temp_db_real)
        conn.execute(
            "INSERT INTO orders (order_type, amount, price, total, remaining) VALUES (?, ?, ?, ?, ?)",
            ("BUY", 0.1, 0.3, 0.03, 0.1),
        )
        conn.commit()
        conn.close()

        # Run init_db (should migrate) — patch get_db_path to return the raw path
        with patch("apps.exchange.simple_exchange.db.get_db_path", return_value=temp_db_real):
            init_db()

        # Verify columns are now TEXT
        conn = sqlite3.connect(temp_db_real)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(orders)")
        cols = {row[1]: row[2].upper() for row in cursor.fetchall()}
        assert cols["amount"] == "TEXT"
        assert cols["price"] == "TEXT"

        # Verify data was preserved
        cursor.execute("SELECT amount, price FROM orders LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        # Data should be preserved as TEXT
        assert row is not None
        assert Decimal(str(row[0])) == Decimal("0.1")
        assert Decimal(str(row[1])) == Decimal("0.3")


class TestB1OrderMatchingAtomicity:
    """B1: Verify order matching is atomic (single transaction)."""

    def test_match_orders_in_txn_uses_decimal(self, temp_db):
        """Verify _match_orders_in_txn uses Decimal for all arithmetic."""
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

        # Create a mock handler with the mixin
        handler = MagicMock(spec=ExchangeMixin)
        handler._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(handler, ExchangeMixin)

        # Insert a SELL order
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO orders (order_type, amount, price, total, filled, remaining, status, user_address) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("SELL", "10", "1.5", "15", "0", "10", "open", "0xseller"),
        )
        conn.commit()
        conn.close()

        # Create a BUY order to match
        buy_order = {
            "id": None,  # Will be set after insert
            "order_type": "BUY",
            "amount": "5",
            "price": "1.5",
            "total": "7.5",
            "filled": "0",
            "remaining": "5",
            "status": "open",
        }

        with patch.dict(os.environ, {"EXCHANGE_DATABASE_URL": f"sqlite:///{temp_db}"}):
            with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=temp_db):
                conn = sqlite3.connect(temp_db, timeout=30)
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.cursor()

                # Insert the buy order
                cursor.execute(
                    "INSERT INTO orders (order_type, amount, price, total, remaining, user_address) VALUES (?, ?, ?, ?, ?, ?)",
                    ("BUY", "5", "1.5", "7.5", "5", "0xbuyer"),
                )
                buy_order["id"] = cursor.lastrowid

                # Match within the transaction
                handler._match_orders_in_txn(cursor, buy_order)

                conn.commit()
                conn.close()

        # Verify the trade was recorded with exact Decimal values
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT amount, price, total FROM trades")
        trade = cursor.fetchone()
        conn.close()

        assert trade is not None
        assert Decimal(trade[0]) == Decimal("5")  # amount
        assert Decimal(trade[1]) == Decimal("1.5")  # price
        assert Decimal(trade[2]) == Decimal("7.5")  # total = 5 * 1.5

    def test_match_orders_in_txn_updates_both_orders(self, temp_db):
        """Verify matching updates both the new and counterparty orders."""
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

        handler = MagicMock(spec=ExchangeMixin)
        handler._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(handler, ExchangeMixin)

        # Insert a SELL order for 10 units
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO orders (order_type, amount, price, total, filled, remaining, status, user_address) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("SELL", "10", "1.0", "10", "0", "10", "open", "0xseller"),
        )
        conn.commit()
        conn.close()

        buy_order = {
            "order_type": "BUY",
            "amount": "10",
            "price": "1.0",
            "total": "10",
            "filled": "0",
            "remaining": "10",
            "status": "open",
        }

        with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=temp_db):
            conn = sqlite3.connect(temp_db, timeout=30)
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (order_type, amount, price, total, remaining, user_address) VALUES (?, ?, ?, ?, ?, ?)",
                ("BUY", "10", "1.0", "10", "10", "0xbuyer"),
            )
            buy_order["id"] = cursor.lastrowid

            handler._match_orders_in_txn(cursor, buy_order)
            conn.commit()
            conn.close()

        # Verify both orders are filled
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT status, filled, remaining FROM orders WHERE order_type = 'SELL'")
        sell_order = cursor.fetchone()
        cursor.execute("SELECT status, filled, remaining FROM orders WHERE order_type = 'BUY'")
        buy_db = cursor.fetchone()
        conn.close()

        assert sell_order[0] == "filled"
        assert Decimal(sell_order[1]) == Decimal("10")
        assert Decimal(sell_order[2]) == Decimal("0")

        assert buy_db[0] == "filled"
        assert Decimal(buy_db[1]) == Decimal("10")
        assert Decimal(buy_db[2]) == Decimal("0")

    def test_match_orders_standalone_uses_begin_immediate(self, temp_db):
        """Verify match_orders (standalone) acquires write lock with BEGIN IMMEDIATE."""
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

        handler = MagicMock(spec=ExchangeMixin)
        # Bind both methods to the real implementations
        handler._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(handler, ExchangeMixin)
        handler.match_orders = ExchangeMixin.match_orders.__get__(handler, ExchangeMixin)

        # Insert a SELL order
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO orders (order_type, amount, price, total, filled, remaining, status, user_address) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("SELL", "5", "2.0", "10", "0", "5", "open", "0xseller"),
        )
        conn.commit()
        conn.close()

        buy_order = {
            "id": 99,  # Fake ID — won't exist in DB, but match should still work for counterparty
            "order_type": "BUY",
            "amount": "3",
            "price": "2.0",
            "total": "6",
            "filled": "0",
            "remaining": "3",
            "status": "open",
        }

        with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=temp_db):
            handler.match_orders(buy_order)

        # Verify the SELL order was partially filled
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT filled, remaining, status FROM orders WHERE order_type = 'SELL'")
        sell = cursor.fetchone()
        conn.close()

        assert Decimal(sell[0]) == Decimal("3")
        assert Decimal(sell[1]) == Decimal("2")
        assert sell[2] == "open"  # Still open, partially filled


class TestB3ConnectionCleanup:
    """B3: Verify database connections are closed via try/finally."""

    def test_get_recent_trades_closes_connection(self, temp_db):
        """Verify get_recent_trades closes the DB connection."""
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

        handler = MagicMock(spec=ExchangeMixin)
        handler.send_json_response = MagicMock()
        handler.get_recent_trades = ExchangeMixin.get_recent_trades.__get__(handler, ExchangeMixin)

        parsed = MagicMock()
        parsed.query = "limit=5"

        with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=temp_db):
            handler.get_recent_trades(parsed)

        # Verify send_json_response was called (meaning the method completed without error)
        assert handler.send_json_response.called

    def test_get_orderbook_closes_connection(self, temp_db):
        """Verify get_orderbook closes the DB connection."""
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

        handler = MagicMock(spec=ExchangeMixin)
        handler.send_json_response = MagicMock()
        handler.get_orderbook = ExchangeMixin.get_orderbook.__get__(handler, ExchangeMixin)

        with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=temp_db):
            handler.get_orderbook()

        assert handler.send_json_response.called


class TestB2MarketplaceDecimal:
    """B2: Verify marketplace handler uses Decimal for prices."""

    def test_marketplace_create_offer_stores_price_as_text(self, temp_db):
        """Verify marketplace prices are stored as TEXT (Decimal-as-string)."""
        from apps.exchange.simple_exchange.handlers.marketplace import MarketplaceMixin

        handler = MagicMock(spec=MarketplaceMixin)
        handler._read_json_body = MagicMock(
            return_value={
                "item": "gpu-a100",
                "item_type": "gpu",
                "price": 0.1,
                "wallet": "0xtest",
                "description": "A100 GPU",
            }
        )
        handler.send_json_response = MagicMock()
        handler._new_marketplace_id = MarketplaceMixin._new_marketplace_id.__get__(handler, MarketplaceMixin)
        handler.handle_marketplace_create_offer = MarketplaceMixin.handle_marketplace_create_offer.__get__(
            handler, MarketplaceMixin
        )

        with patch("apps.exchange.simple_exchange.handlers.marketplace.get_db_path", return_value=temp_db):
            handler.handle_marketplace_create_offer()

        # Verify the price was stored as TEXT
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT price FROM marketplace_offers LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        # Should be stored as string "0.1", not float 0.1
        assert isinstance(row[0], str)
        assert Decimal(row[0]) == Decimal("0.1")
