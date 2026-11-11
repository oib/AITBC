"""#1695: the unsigned legacy match path self-guards on ``user_address``.

``_match_orders_in_txn`` historically only applied the self-match guard
when the signed path passed ``guard_address`` explicitly, so flag-off
rollback mode let one address wash against itself. The order's own
``user_address`` now guards the match whenever no explicit guard is
given — string equality, case-insensitive, behavior-preserving for
distinct addresses.
"""

import sqlite3
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("EXCHANGE_SETTLEMENT_ENABLED", raising=False)


def _handler():
    h = MagicMock(spec=ExchangeMixin)
    h._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(h, ExchangeMixin)
    return h


def _insert_open_sell(db_path, user_address):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO orders (order_type, amount, price, total, remaining, user_address,
                            amount_ticks, price_ticks, filled_ticks, remaining_ticks)
        VALUES ('SELL', '10', '0.001', '0.01', '10', ?, ?, ?, 0, ?)
        """,
        (user_address, 10**9, 100_000, 10**9),
    )
    conn.commit()
    conn.close()


def _buy_order(user_address):
    return {
        "order_type": "BUY",
        "price": "0.001",
        "amount": "5",
        "total": "0.005",
        "remaining": "5",
        "filled": "0",
        "status": "open",
        "user_address": user_address,
    }


def _run_match(db_path, order):
    h = _handler()
    conn = sqlite3.connect(db_path)
    conn.execute("BEGIN IMMEDIATE")
    h._match_orders_in_txn(conn.cursor(), order)
    conn.commit()
    conn.close()


def _trade_count(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    finally:
        conn.close()


def test_same_address_does_not_self_match(exchange_db):
    _insert_open_sell(exchange_db, "0xSELF")
    order = _buy_order("0xSELF")
    _run_match(exchange_db, order)
    assert _trade_count(exchange_db) == 0
    assert Decimal(order["remaining"]) == Decimal("5")
    assert order["status"] == "open"


def test_self_match_guard_is_case_insensitive(exchange_db):
    _insert_open_sell(exchange_db, "0xSeLf")
    order = _buy_order("0xself")
    _run_match(exchange_db, order)
    assert _trade_count(exchange_db) == 0


def test_distinct_address_still_matches(exchange_db):
    _insert_open_sell(exchange_db, "0xSELLER")
    order = _buy_order("0xBUYER")
    _run_match(exchange_db, order)
    assert _trade_count(exchange_db) == 1
    assert order["status"] == "filled"
