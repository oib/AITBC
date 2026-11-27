"""#3046 pins: exchange ticks are 1e-8 AIT but the chain settles in integer
units of 1/36,000,000 AIT — a fill converts exactly only when its tick
count is a multiple of 25 (ticks * 9/25 units). Per-fill ROUND_HALF_UP
settlement over an off-grid quantity can pay a fraction of a unit more
than the escrow lock holds, draining commingled customer AIT.

Pins:
- placement rejects off-grid ``amount_ticks`` on BOTH the signed-envelope
  and legacy unsigned paths;
- the match engine refuses off-grid fills under settlement (legacy rows
  can never settle inexactly) while flag-off matching is unchanged;
- grid fills still match and produce on-grid trade quantities.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Reuse the signed-order e2e harness from test_funded_orders (helpers are
# plain functions; its pytest fixtures are replicated locally below).
_spec = importlib.util.spec_from_file_location(
    "_funded_orders_harness",
    Path(__file__).with_name("test_funded_orders.py"),
)
_funded = importlib.util.module_from_spec(_spec)
sys.modules["_funded_orders_harness"] = _funded
_spec.loader.exec_module(_funded)

_handler = _funded._handler
_register = _funded._register
_set_payout = _funded._set_payout
_order_body = _funded._order_body
_place = _funded._place
_last_json = _funded._last_json
ESCROW_ADDR = _funded._ESCROW_ADDR
BRIDGE_ADDR = _funded._BRIDGE_ADDR

from eth_account import Account  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Mirror test_funded_orders' env fixture (autouse there, not shared)."""
    monkeypatch.setenv("EXCHANGE_CHAIN_ID", "ait-localnet")
    monkeypatch.delenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", raising=False)
    monkeypatch.delenv("EXCHANGE_SETTLEMENT_ENABLED", raising=False)
    monkeypatch.delenv("EXCHANGE_FEE_PCT", raising=False)
    monkeypatch.setenv("EXCHANGE_MAX_ORDERS_PER_MIN", "100000")
    monkeypatch.setenv("EXCHANGE_REGISTER_PER_MIN", "100000")
    monkeypatch.setenv("EXCHANGE_READS_PER_MIN", "100000")
    for name in (
        "AIT_SELL_ESCROW",
        "BRIDGE_PAYOUT_ADDRESS",
        "GENESIS_WALLET_ADDRESS",
        "BRIDGE_ETH_ADDRESS",
        "SELL_TREASURY_ADDRESS",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settlement_on(monkeypatch):
    monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
    monkeypatch.setenv("AIT_SELL_ESCROW", ESCROW_ADDR)
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", BRIDGE_ADDR)


@pytest.fixture
def exchange_db(tmp_path, monkeypatch):
    from apps.exchange.simple_exchange import db as exchange_db_module
    from apps.exchange.simple_exchange.handlers import base

    path = str(tmp_path / "exchange.db")
    monkeypatch.setenv("EXCHANGE_API_KEY", "test-key")
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{path}")
    exchange_db_module.init_db()
    base._operation_ledgers.pop(path, None)
    return path


def _order_count(db_path) -> int:
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return n


class TestPlacementGrid:
    """Both placement paths refuse amounts off the 25-tick settle grid."""

    def test_signed_off_grid_amount_rejected(self, exchange_db, settlement_on):

        node = Account.create()
        _register(exchange_db, node.address, node.key.hex(), "n-grid1")
        h = _handler()
        _set_payout(exchange_db, h, node.address, node.key.hex(), Account.create().address, nonce=1)
        before = _order_count(exchange_db)

        # 1.00000001 AIT = 100,000,001 ticks — 100,000,001 % 25 = 1.
        _place(
            exchange_db, h, _order_body(node.address, node.key.hex(), side="SELL", amount="1.00000001", price="0.001", nonce=2)
        )

        assert h.send_error.called, "off-grid amount must be refused"
        assert _order_count(exchange_db) == before

    def test_signed_on_grid_amount_accepted(self, exchange_db, settlement_on):
        node = Account.create()
        _register(exchange_db, node.address, node.key.hex(), "n-grid2")
        h = _handler()
        _set_payout(exchange_db, h, node.address, node.key.hex(), Account.create().address, nonce=1)

        # 1.00000025 AIT = 100,000,025 ticks — divisible by 25.
        _place(
            exchange_db, h, _order_body(node.address, node.key.hex(), side="SELL", amount="1.00000025", price="0.001", nonce=2)
        )

        doc = _last_json(h)
        assert doc["status"] == "open"

    def test_envelope_check_unit(self):

        h = _handler()
        base_env = {
            "side": "SELL",
            "pair": "AIT/ETH",
            "amount_ticks": 100_000_025,
            "price_ticks": 100_000,
            "expiry_height": 2000,
            "account_nonce": 1,
        }
        assert h._order_envelope_error(dict(base_env)) is None
        env = dict(base_env, amount_ticks=100_000_026)
        assert h._order_envelope_error(env) is not None
        env = dict(base_env, amount_ticks=25)
        assert h._order_envelope_error(env) is None
        env = dict(base_env, amount_ticks=24)
        assert h._order_envelope_error(env) is not None

    def test_unsigned_path_off_grid_rejected(self, exchange_db, monkeypatch):
        """The legacy unsigned placement path enforces the same grid —
        flag-off orders must not smuggle inexact amounts into a later
        settlement-enabled match."""
        monkeypatch.setenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", "false")
        monkeypatch.setenv("EXCHANGE_API_KEY", "test-key")
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

        h = _handler()
        h._require_api_key = MagicMock(return_value=True)
        h.send_error = MagicMock()
        h._parse_order_payload = ExchangeMixin._parse_order_payload.__get__(h, ExchangeMixin)
        h._place_order_unsigned = ExchangeMixin._place_order_unsigned.__get__(h, ExchangeMixin)
        h._read_json_body = MagicMock(
            return_value={
                "order_type": "SELL",
                "amount": "1.00000001",
                "price": "0.001",
                "user_address": "0x" + "ab" * 20,
            }
        )
        with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=exchange_db):
            h.handle_place_order()
        assert h.send_error.called
        assert _order_count(exchange_db) == 0


def _insert_legacy_order(db_path, order_type, amount, price, *, funded=False, locked_ticks=None):
    """Seed an order row directly — the pre-#3046 shape that placement can
    no longer produce."""
    from apps.exchange.simple_exchange.db import to_ticks

    amount_d, price_d = Decimal(amount), Decimal(price)
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO orders (order_type, amount, price, total, remaining, status, user_address,"
        " amount_ticks, price_ticks, filled_ticks, remaining_ticks, funded_state, locked_ticks)"
        " VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, 0, ?, ?, ?)",
        (
            order_type,
            str(amount_d),
            str(price_d),
            str(amount_d * price_d),
            str(amount_d),
            "0x" + "11" * 20,
            to_ticks(amount_d),
            to_ticks(price_d),
            to_ticks(amount_d),
            "funded" if funded else "unfunded",
            locked_ticks,
        ),
    )
    conn.commit()
    oid = cur.lastrowid
    conn.close()
    return oid


def _match_handler():
    from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

    handler = MagicMock(spec=ExchangeMixin)
    handler._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(handler, ExchangeMixin)
    handler._chain_head_height = MagicMock(return_value=None)
    handler._expire_open_orders = MagicMock()
    return handler


def _run_match(db_path, order):
    handler = _match_handler()
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("BEGIN IMMEDIATE")
    handler._match_orders_in_txn(conn.cursor(), order, head_height=1000)
    conn.commit()
    conn.close()
    return handler


def _trades(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT amount, buy_order_id, sell_order_id, settlement_state FROM trades").fetchall()
    conn.close()
    return rows


def _buy_order(amount, price="0.001", order_id=None, funded=True):
    return {
        "id": order_id,
        "order_type": "BUY",
        "amount": amount,
        "price": price,
        "total": str(Decimal(amount) * Decimal(price)),
        "filled": "0",
        "remaining": amount,
        "status": "open",
        "user_address": "0x" + "22" * 20,
        "funded_state": "funded" if funded else "unfunded",
    }


class TestMatchGridGuard:
    """Under settlement, an off-grid fill quantity must never trade — the
    per-fill unit conversion would round and could over-draw the lock."""

    def test_off_grid_legacy_sell_never_fills(self, exchange_db, settlement_on):
        # Legacy SELL: 1.00000001 AIT remaining — off the 25-tick grid.
        _insert_legacy_order(
            exchange_db,
            "SELL",
            "1.00000001",
            "0.001",
            funded=True,
            locked_ticks=100_000_001,
        )
        _run_match(exchange_db, _buy_order("1.00000025"))
        assert _trades(exchange_db) == []

    def test_off_grid_inbound_buy_never_fills(self, exchange_db, settlement_on):
        _insert_legacy_order(
            exchange_db,
            "SELL",
            "1.00000025",
            "0.001",
            funded=True,
            locked_ticks=100_000_025,
        )
        # Crafted inbound BUY with an off-grid remainder (placement can no
        # longer produce this; the match engine must still refuse it).
        _run_match(exchange_db, _buy_order("1.00000001"))
        assert _trades(exchange_db) == []

    def test_on_grid_partial_fill_trades(self, exchange_db, settlement_on):
        _insert_legacy_order(
            exchange_db,
            "SELL",
            "2.00000050",
            "0.001",
            funded=True,
            locked_ticks=200_000_050,
        )
        _run_match(exchange_db, _buy_order("1.00000025"))
        trades = _trades(exchange_db)
        assert len(trades) == 1
        from apps.exchange.simple_exchange.db import to_ticks

        assert to_ticks(Decimal(trades[0][0])) % 25 == 0

    def test_flag_off_matching_unchanged(self, exchange_db, monkeypatch):
        """Phase-2 (no settlement) never converts to chain units — the grid
        guard is settlement-scoped and off-grid orders still match."""
        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "false")
        _insert_legacy_order(exchange_db, "SELL", "1.00000001", "0.001")
        _run_match(exchange_db, _buy_order("1.00000025", funded=False))
        assert len(_trades(exchange_db)) == 1
