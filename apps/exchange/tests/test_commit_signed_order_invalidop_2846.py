"""#2846: _commit_signed_order's exception net must catch decimal.InvalidOperation.

An absurd-but-legal unsigned-path total can make the fee quantize raise
InvalidOperation (an ArithmeticError, not a ValueError). Before the fix it
escaped the except tuple — the connection closed without rollback and the
request 500'd instead of the honest 503 + ledger fail. Pin: the handler
answers 503 and a same-key retry is not wedged.
"""

from decimal import InvalidOperation
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account

from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin
from apps.exchange.simple_exchange.handlers import base


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EXCHANGE_CHAIN_ID", "ait-localnet")
    monkeypatch.setenv("EXCHANGE_MAX_ORDERS_PER_MIN", "100000")
    monkeypatch.setenv("EXCHANGE_REGISTER_PER_MIN", "100000")
    monkeypatch.setenv("EXCHANGE_READS_PER_MIN", "100000")
    monkeypatch.delenv("EXCHANGE_SETTLEMENT_ENABLED", raising=False)
    buckets = ExchangeMixin.handle_node_register.__globals__.get("_RATE_BUCKETS")
    lock = ExchangeMixin.handle_node_register.__globals__.get("_RATE_LOCK")
    if buckets is not None and lock is not None:
        with lock:
            buckets.clear()


@pytest.fixture
def exchange_db(tmp_path, monkeypatch):
    from apps.exchange.simple_exchange import db as exchange_db_module

    path = str(tmp_path / "exchange.db")
    monkeypatch.setenv("EXCHANGE_API_KEY", "test-key")
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{path}")
    exchange_db_module.init_db()
    base._operation_ledgers.pop(path, None)
    return path


def _handler():
    h = MagicMock(spec=ExchangeMixin)
    h.send_error = MagicMock()
    h.send_json_response = MagicMock()
    h._client_ip = MagicMock(return_value="127.0.0.1")
    for name in ("_commit_signed_order", "_signed_order_gate", "_insert_signed_order", "_match_orders_in_txn"):
        setattr(h, name, getattr(ExchangeMixin, name).__get__(h, ExchangeMixin))
    return h


def _envelope():
    return {
        "side": "BUY",
        "pair": "AIT/ETH",
        "amount_ticks": 1_000_000_000,
        "price_ticks": 100_000,
        "expiry_height": 2000,
        "account_nonce": 1,
        "chain_id": "ait-localnet",
    }


def test_invalid_operation_in_txn_is_caught_and_retry_not_wedged(exchange_db):
    acct = Account.create()
    h = _handler()
    h.headers = {"Idempotency-Key": "k-2846"}
    h._signed_order_gate = MagicMock(return_value=None)
    order = {"order_id": "o-2846", "user_address": acct.address}
    h._insert_signed_order = MagicMock(return_value=order)
    h._match_orders_in_txn = MagicMock(side_effect=[InvalidOperation("quantize overflow"), None])
    data = {"signature": "0x" + "ab" * 65}

    with patch("apps.exchange.simple_exchange.handlers.exchange_orders.get_db_path", return_value=exchange_db):
        # First attempt: InvalidOperation inside BEGIN IMMEDIATE → 503, no escape.
        h._commit_signed_order(data, _envelope(), acct.address, "envhash-1", 1000)
        assert h.send_json_response.call_args[0][0] == {"error": "Order placement failed"}
        assert h.send_json_response.call_args[1].get("status") == 503

        # Same Idempotency-Key retry must not be wedged by a phantom pending row.
        h.send_json_response.reset_mock()
        h._commit_signed_order(data, _envelope(), acct.address, "envhash-1", 1000)
        assert h.send_json_response.call_args[0][0] == order
