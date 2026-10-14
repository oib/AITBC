"""ETH-8 phase 3 (C3): funding gates — prepaid-ETH debits on BUYs, payout
snapshot + lock instructions on SELLs, funded-only matching, and atomic
debit refunds on cancel/expiry.

Everything sits behind EXCHANGE_SETTLEMENT_ENABLED; flag-off behavior is
byte-identical to phase 2 (first test asserts it).

Throwaway keys + throwaway DBs only.
"""

import sqlite3
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account

from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin


@pytest.fixture(autouse=True)
def _env(monkeypatch):
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
    buckets = ExchangeMixin.handle_node_register.__globals__.get("_RATE_BUCKETS")
    lock = ExchangeMixin.handle_node_register.__globals__.get("_RATE_LOCK")
    if buckets is not None and lock is not None:
        with lock:
            buckets.clear()


# EIP-55 test vectors — valid checksummed funding destinations, no secrets.
_ESCROW_ADDR = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
_BRIDGE_ADDR = "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359"


@pytest.fixture
def settlement_on(monkeypatch):
    monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
    # Under the flag the funding destinations must be configured EIP-55
    # addresses — placement refuses the order when either env is missing.
    monkeypatch.setenv("AIT_SELL_ESCROW", _ESCROW_ADDR)
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", _BRIDGE_ADDR)


@pytest.fixture
def exchange_db(tmp_path, monkeypatch):
    """Phase-3 tests need the REAL schema — the conftest fixture hand-rolls
    a minimal orders/trades registry without the settlement columns. This
    module-local override runs init_db() instead."""
    from apps.exchange.simple_exchange import db as exchange_db_module
    from apps.exchange.simple_exchange.handlers import base

    path = str(tmp_path / "exchange.db")
    monkeypatch.setenv("EXCHANGE_API_KEY", "test-key")
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{path}")
    exchange_db_module.init_db()
    base._operation_ledgers.pop(path, None)
    return path


def _sign(envelope, privkey):
    from aitbc.crypto.crypto import sign_transaction_data

    return sign_transaction_data(envelope, privkey)


def _handler():
    h = MagicMock(spec=ExchangeMixin)
    h.send_error = MagicMock()
    h.send_json_response = MagicMock()
    h._client_ip = MagicMock(return_value="127.0.0.1")
    for name in (
        "handle_node_register",
        "handle_place_order",
        "handle_cancel_order",
        "handle_set_payout",
        "handle_exchange_nodes",
        "get_orderbook",
        "_orderbook_row",
        "_place_order_signed",
        "_verify_signed_body",
        "_order_envelope_error",
        "_cancel_envelope_error",
        "_live_head_if_unexpired",
        "_signed_order_limits",
        "_book_capacity_error",
        "_commit_signed_order",
        "_signed_order_gate",
        "_insert_signed_order",
        "_fund_order_in_txn",
        "_match_orders_in_txn",
        "_expire_open_orders",
        "_commit_register",
        "_commit_payout",
        "_commit_cancel",
        "_registry_status",
        "_registry_labels",
        "_expected_nonce",
        "_claim_nonce",
        "_order_by_envelope",
        "_chain_head_height",
        "_ait_eth_band",
        "_ait_eth_rate",
        "_node_rows",
        "_watchlisted_addresses",
    ):
        if hasattr(ExchangeMixin, name):
            attr = getattr(ExchangeMixin, name)
            if name in ("_expected_nonce", "_claim_nonce", "_expire_open_orders", "_watchlisted_addresses"):
                setattr(h, name, attr)
            else:
                setattr(h, name, attr.__get__(h, ExchangeMixin))
    h._ait_eth_band = MagicMock(return_value=(Decimal("0"), Decimal("1e18")))
    h._chain_head_height = MagicMock(return_value=1000)
    return h


def _register(db_path, address, privkey, label):
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO node_registry (address, label, status) VALUES (?, ?, 'seeded')", (address, label))
    conn.commit()
    conn.close()
    h = _handler()
    env = {
        "action": "exchange_register",
        "address": address,
        "label": label,
        "account_nonce": 0,
        "chain_id": "ait-localnet",
    }
    h._read_json_body = MagicMock(return_value={"envelope": env, "signature": _sign(env, privkey), "user_address": address})
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_node_register()
    assert not h.send_error.called, h.send_error.call_args_list
    return h


def _set_payout(db_path, h, address, privkey, eth_address, nonce=1):
    env = {
        "action": "exchange_set_payout",
        "eth_address": eth_address,
        "account_nonce": nonce,
        "chain_id": "ait-localnet",
    }
    h._read_json_body = MagicMock(return_value={"envelope": env, "signature": _sign(env, privkey), "user_address": address})
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_set_payout()


def _order_body(addr, key, *, side="SELL", amount=10, price="0.001", expiry=2000, nonce=1):
    env = {
        "side": side,
        "pair": "AIT/ETH",
        "amount_ticks": int(Decimal(amount) * 100_000_000),
        "price_ticks": int(Decimal(price) * 100_000_000),
        "expiry_height": expiry,
        "account_nonce": nonce,
        "chain_id": "ait-localnet",
    }
    return {"envelope": env, "signature": _sign(env, key), "user_address": addr}


def _place(db_path, h, body):
    h._read_json_body = MagicMock(return_value=body)
    h.send_error.reset_mock()
    h.send_json_response.reset_mock()
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_place_order()


def _cancel(db_path, h, addr, key, order_id, nonce):
    env = {
        "action": "exchange_cancel",
        "order_id": order_id,
        "expiry_height": 2000,
        "account_nonce": nonce,
        "chain_id": "ait-localnet",
    }
    h._read_json_body = MagicMock(return_value={"envelope": env, "signature": _sign(env, key), "user_address": addr})
    h.send_error.reset_mock()
    h.send_json_response.reset_mock()
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_cancel_order(str(order_id))


def _last_json(h):
    assert h.send_json_response.called, f"no response; send_error={h.send_error.call_args_list}"
    return h.send_json_response.call_args[0][0]


def _prepay(db_path, address, amount_eth):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO prepaid_deposits (node_address, amount_eth, eth_tx_hash) VALUES (?, ?, ?)",
        (address, str(amount_eth), f"0xdep{address[-6:]}{abs(hash(amount_eth)) % 1000}"),
    )
    conn.commit()
    conn.close()


def _debit_row(db_path, order_id):
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT amount_eth, committed_eth, state FROM prepaid_debits WHERE order_id = ?", (order_id,)
    ).fetchone()
    conn.close()
    return row


def _order_row(db_path, order_id):
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT funded_state, seller_eth_address, locked_ticks, status FROM orders WHERE id = ?", (order_id,)
    ).fetchone()
    conn.close()
    return row


def _fund_order(db_path, order_id, locked_ticks=None):
    """Simulate the C4 order_funded endpoint event (not yet built)."""
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE orders SET funded_state = 'funded', locked_ticks = ? WHERE id = ?", (locked_ticks, order_id))
    conn.commit()
    conn.close()


def _trade_rows(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT amount, total, buy_order_id, sell_order_id, settlement_state, fee_ait FROM trades").fetchall()
    conn.close()
    return rows


# --- flag-off inertness ----------------------------------------------------


def test_flag_off_byte_identical(exchange_db):
    """Settlement unset: phase-2 behavior is unchanged — SELL places without
    a payout address, matching is funding-blind, trade rows carry no
    settlement columns, responses carry no funding instruction."""
    a, b = Account.create(), Account.create()
    _register(exchange_db, a.address, a.key.hex(), "n-sell")
    _register(exchange_db, b.address, b.key.hex(), "n-buy")
    h = _handler()
    _place(exchange_db, h, _order_body(a.address, a.key.hex(), side="SELL", amount=10, price="0.001", nonce=1))
    doc = _last_json(h)
    assert doc["status"] == "open" and "funding" not in doc
    _place(exchange_db, h, _order_body(b.address, b.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    doc = _last_json(h)
    assert doc["status"] == "filled" and "funding" not in doc
    trades = _trade_rows(exchange_db)
    assert len(trades) == 1
    assert trades[0][2] is None and trades[0][3] is None and trades[0][4] is None  # no order ids / settlement_state
    conn = sqlite3.connect(exchange_db)
    assert conn.execute("SELECT COUNT(*) FROM prepaid_debits").fetchone()[0] == 0
    conn.close()


# --- SELL funding gates ----------------------------------------------------


def test_sell_without_payout_refused(exchange_db, settlement_on):
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-nopay")
    h = _handler()
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="SELL", nonce=1))
    resp = _last_json(h)
    assert "payout" in resp.get("error", "").lower()
    conn = sqlite3.connect(exchange_db)
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    # Refused BEFORE the nonce claim — the same nonce places successfully
    # once the payout exists.
    conn.close()
    _set_payout(exchange_db, h, node.address, node.key.hex(), Account.create().address, nonce=1)
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="SELL", nonce=2))
    assert _last_json(h)["status"] == "open"


def test_sell_unfunded_lock_instruction_and_snapshot(exchange_db, settlement_on):
    node, payout = Account.create(), Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-seller")
    h = _handler()
    _set_payout(exchange_db, h, node.address, node.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="SELL", amount=10, price="0.001", nonce=2))
    doc = _last_json(h)
    assert doc["status"] == "open" and doc["funded_state"] == "unfunded"
    assert doc["funding"]["type"] == "ait_lock"
    assert doc["funding"]["payload"] == f"sell_quote={doc['id']}"
    assert Decimal(doc["funding"]["required_ait"]) == Decimal("10")  # fee 0 → amount only
    row = _order_row(exchange_db, doc["id"])
    assert row[0] == "unfunded" and row[1] == payout.address


# --- BUY funding gates -----------------------------------------------------


def test_buy_without_deposit_unfunded(exchange_db, settlement_on):
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-poor")
    h = _handler()
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    doc = _last_json(h)
    assert doc["funded_state"] == "unfunded"
    assert doc["funding"]["type"] == "eth_prepay"
    assert doc["funding"]["needed_eth"] == "0.01"
    assert doc["funding"]["tag"] == f"EXCHANGE_DEPOSIT:{node.address}"
    assert doc["funding"]["bridge_eth_address"] == _BRIDGE_ADDR


def test_buy_with_sufficient_deposit_funded(exchange_db, settlement_on):
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-rich")
    _prepay(exchange_db, node.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    doc = _last_json(h)
    assert doc["funded_state"] == "funded"
    assert doc["funding"]["debited_eth"] == "0.01"
    row = _order_row(exchange_db, doc["id"])
    assert row[0] == "funded"
    assert _debit_row(exchange_db, doc["id"]) == ("0.01", "0", "open")


def test_buy_partial_deposit_unfunded(exchange_db, settlement_on):
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-half")
    _prepay(exchange_db, node.address, "0.004")
    h = _handler()
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    doc = _last_json(h)
    assert doc["funded_state"] == "unfunded"
    assert Decimal(doc["funding"]["needed_eth"]) == Decimal("0.006")


# --- funded-only matching --------------------------------------------------


def _resting_funded_sell(exchange_db, amount=10, price="0.001", locked_ticks=None, nonce=2):
    node, payout = Account.create(), Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-rests")
    h = _handler()
    _set_payout(exchange_db, h, node.address, node.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="SELL", amount=amount, price=price, nonce=nonce))
    doc = _last_json(h)
    assert doc["status"] == "open"
    locked = locked_ticks if locked_ticks is not None else int(Decimal(amount) * 100_000_000)
    _fund_order(exchange_db, doc["id"], locked_ticks=locked)
    return node, doc["id"]


def test_unfunded_buy_never_matches(exchange_db, settlement_on):
    _resting_funded_sell(exchange_db)
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-buynofund")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    assert _last_json(h)["status"] == "open"
    assert _trade_rows(exchange_db) == []


def test_unfunded_sell_never_matched(exchange_db, settlement_on):
    # Resting sell has payout but no lock -> stays 'unfunded'.
    seller, payout = Account.create(), Account.create()
    _register(exchange_db, seller.address, seller.key.hex(), "n-snou")
    h = _handler()
    _set_payout(exchange_db, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(seller.address, seller.key.hex(), side="SELL", nonce=2))
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-byes")
    _prepay(exchange_db, buyer.address, "0.05")
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    assert _last_json(h)["status"] == "open"
    assert _trade_rows(exchange_db) == []


def test_underlocked_sell_skipped(exchange_db, settlement_on):
    """The in-scan safety net: a 'funded' SELL whose recorded lock cannot
    cover remaining + fee is never matched (monitor marks it later)."""
    _resting_funded_sell(exchange_db, amount=10, locked_ticks=int(Decimal("4") * 100_000_000))
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-buylock")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    assert _last_json(h)["status"] == "open"
    assert _trade_rows(exchange_db) == []


def test_funded_match_writes_links_and_commits_cost(exchange_db, settlement_on):
    _resting_funded_sell(exchange_db, amount=10)
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-buyyes")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    doc = _last_json(h)
    assert doc["status"] == "filled"
    trades = _trade_rows(exchange_db)
    assert len(trades) == 1
    amount, total, buy_id, sell_id, state, fee = trades[0]
    assert Decimal(amount) == Decimal("10") and Decimal(total) == Decimal("0.01")
    assert buy_id == doc["id"] and sell_id is not None and state == "locked"
    assert Decimal(fee) == Decimal("0")
    assert _debit_row(exchange_db, doc["id"]) == ("0.01", "0.01", "consumed")


def test_split_fill_fee_and_commit_math(exchange_db, settlement_on, monkeypatch):
    """Two partial buys against one locked sell: each trade's fee is its own
    qty*pct, each buy's commit is its own total — never the whole lock."""
    monkeypatch.setenv("EXCHANGE_FEE_PCT", "0.01")
    # Lock covers amount + fee (10 * 1.01 = 10.1) — the funded-gate cover rule.
    _resting_funded_sell(exchange_db, amount=10, price="0.001", locked_ticks=int(Decimal("10.1") * 100_000_000))
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-split")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=4, price="0.001", nonce=1))
    doc1 = _last_json(h)
    assert doc1["status"] == "filled"
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=6, price="0.001", nonce=2))
    doc2 = _last_json(h)
    assert doc2["status"] == "filled"
    trades = _trade_rows(exchange_db)
    assert len(trades) == 2
    assert Decimal(trades[0][5]) == Decimal("0.04")  # 4 * 0.01
    assert Decimal(trades[1][5]) == Decimal("0.06")  # 6 * 0.01
    # Each buy's debit committed exactly its trade total (0.004 / 0.006).
    assert _debit_row(exchange_db, doc1["id"]) == ("0.004", "0.004", "consumed")
    assert _debit_row(exchange_db, doc2["id"]) == ("0.006", "0.006", "consumed")


def test_self_match_still_blocked(exchange_db, settlement_on):
    node, payout = Account.create(), Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-selfx")
    _prepay(exchange_db, node.address, "0.05")
    h = _handler()
    _set_payout(exchange_db, h, node.address, node.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="SELL", nonce=2))
    sell_id = _last_json(h)["id"]
    _fund_order(exchange_db, sell_id, locked_ticks=int(Decimal("10") * 100_000_000))
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", nonce=3))
    assert _last_json(h)["status"] == "open"
    assert _trade_rows(exchange_db) == []


# --- refunds ---------------------------------------------------------------


def test_cancel_funded_buy_refunds_and_expires_backing(exchange_db, settlement_on):
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-cancelbuy")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    doc = _last_json(h)
    _cancel(exchange_db, h, buyer.address, buyer.key.hex(), doc["id"], nonce=2)
    resp = _last_json(h)
    assert resp["status"] == "cancelled" and resp["refunded_eth"] == "0.01"
    assert _debit_row(exchange_db, doc["id"]) == ("0.01", "0", "refunded")
    assert _order_row(exchange_db, doc["id"])[0] == "backing_expired"


def test_partial_fill_cancel_refund_math(exchange_db, settlement_on):
    """Buy 10 @0.001 debits 0.01; a 4-AIT fill commits 0.004; the cancel
    refunds only the uncommitted 0.006 — the matched trade's cost stays
    earmarked for settlement."""
    _resting_funded_sell(exchange_db, amount=4)
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-part")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    doc = _last_json(h)
    assert doc["status"] == "open" and doc["filled"] == "4"
    _cancel(exchange_db, h, buyer.address, buyer.key.hex(), doc["id"], nonce=2)
    resp = _last_json(h)
    assert resp["refunded_eth"] == "0.006"
    assert _debit_row(exchange_db, doc["id"]) == ("0.01", "0.004", "refunded")


def test_expiry_flips_backing_expired_and_refunds(exchange_db, settlement_on):
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-expbuy")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    # expiry_height 500 < head 1000? A live-head check refuses already-expired
    # envelopes, so place at expiry 2000 then advance the head past it.
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=10, price="0.001", nonce=1))
    doc = _last_json(h)
    assert doc["status"] == "open"
    h._chain_head_height = MagicMock(return_value=3000)
    other = Account.create()
    _register(exchange_db, other.address, other.key.hex(), "n-expother")
    _prepay(exchange_db, other.address, "0.05")
    _place(
        exchange_db, h, _order_body(other.address, other.key.hex(), side="BUY", amount=1, price="0.001", expiry=5000, nonce=1)
    )
    row = _order_row(exchange_db, doc["id"])
    assert row[3] == "expired" and row[0] == "backing_expired"
    assert _debit_row(exchange_db, doc["id"]) == ("0.01", "0", "refunded")


def test_inbound_buy_fill_closes_debit(exchange_db, settlement_on):
    """A funded BUY that fills fully closes its debit at match — the
    residual (better match price than the limit) returns to spendable."""
    _resting_funded_sell(exchange_db, amount=10, price="0.001")
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-fbetter")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    # Bid 0.002 but the resting sell is at 0.001 -> pays 0.001.
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=10, price="0.002", nonce=1))
    doc = _last_json(h)
    assert doc["status"] == "filled"
    # debit 0.02, committed 0.01 -> residual 0.01 refunded.
    assert _debit_row(exchange_db, doc["id"]) == ("0.02", "0.01", "refunded")


def test_candidate_buy_close_via_rematch(exchange_db, settlement_on):
    """The C4 order_funded re-match path drives _match_orders_in_txn with a
    funded SELL: a resting buy that fills must close its debit too."""
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-candbuy")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=5, price="0.001", nonce=1))
    buy_doc = _last_json(h)
    seller, payout = Account.create(), Account.create()
    _register(exchange_db, seller.address, seller.key.hex(), "n-cands")
    _set_payout(exchange_db, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(seller.address, seller.key.hex(), side="SELL", amount=5, price="0.001", nonce=2))
    sell_doc = _last_json(h)
    _fund_order(exchange_db, sell_doc["id"], locked_ticks=int(Decimal("5") * 100_000_000))
    # Drive the re-match the way the endpoint will: order dict + own txn.
    conn = sqlite3.connect(exchange_db)
    conn.execute("BEGIN IMMEDIATE")
    order = {
        "id": sell_doc["id"],
        "order_type": "SELL",
        "price": "0.001",
        "remaining": "5",
        "filled": "0",
        "status": "open",
        "funded_state": "funded",
        "user_address": seller.address,
    }
    h._match_orders_in_txn(conn.cursor(), order, head_height=1000, guard_address=seller.address)
    conn.commit()
    conn.close()
    assert len(_trade_rows(exchange_db)) == 1
    # candidate buy filled: 0.005 committed of 0.005 -> consumed.
    assert _debit_row(exchange_db, buy_doc["id"]) == ("0.005", "0.005", "consumed")


# --- book visibility -------------------------------------------------------


def test_orderbook_shows_only_funded(exchange_db, settlement_on):
    # One unfunded sell (has payout, no lock) + one funded sell.
    s1, p1 = Account.create(), Account.create()
    _register(exchange_db, s1.address, s1.key.hex(), "n-bookunf")
    h = _handler()
    _set_payout(exchange_db, h, s1.address, s1.key.hex(), p1.address, nonce=1)
    _place(exchange_db, h, _order_body(s1.address, s1.key.hex(), side="SELL", amount=10, price="0.001", nonce=2))
    s2_doc_id = None
    s2, p2 = Account.create(), Account.create()
    _register(exchange_db, s2.address, s2.key.hex(), "n-bookfnd")
    _set_payout(exchange_db, h, s2.address, s2.key.hex(), p2.address, nonce=1)
    _place(exchange_db, h, _order_body(s2.address, s2.key.hex(), side="SELL", amount=10, price="0.002", nonce=2))
    s2_doc_id = _last_json(h)["id"]
    _fund_order(exchange_db, s2_doc_id, locked_ticks=int(Decimal("10") * 100_000_000))
    h.send_json_response.reset_mock()
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=exchange_db):
        h.get_orderbook()
    book = _last_json(h)
    assert len(book["sells"]) == 1
    assert book["sells"][0]["id"] == s2_doc_id


# --- funding-destination env guard (C6) -------------------------------------


def _orders_count(db_path):
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return n


def _last_status(h):
    return h.send_json_response.call_args[1].get("status")


def test_buy_refused_when_bridge_env_unset(exchange_db, settlement_on, monkeypatch):
    monkeypatch.delenv("BRIDGE_ETH_ADDRESS", raising=False)
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-novault")
    h = _handler()
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", nonce=1))
    assert _last_status(h) == 503
    assert "BRIDGE_ETH_ADDRESS" in _last_json(h)["error"]
    assert _orders_count(exchange_db) == 0
    # The refusal never burned the account nonce — the same envelope lands
    # once the env is configured.
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", _BRIDGE_ADDR)
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", nonce=1))
    assert _last_json(h)["status"] == "open"


def test_sell_refused_when_escrow_env_unset(exchange_db, settlement_on, monkeypatch):
    monkeypatch.delenv("AIT_SELL_ESCROW", raising=False)
    node, payout = Account.create(), Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-noesc")
    h = _handler()
    _set_payout(exchange_db, h, node.address, node.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="SELL", nonce=2))
    assert _last_status(h) == 503
    assert "AIT_SELL_ESCROW" in _last_json(h)["error"]
    assert _orders_count(exchange_db) == 0


def test_buy_refused_when_env_empty(exchange_db, settlement_on, monkeypatch):
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "")
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-empty")
    h = _handler()
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", nonce=1))
    assert _last_status(h) == 503
    assert _orders_count(exchange_db) == 0


def test_buy_refused_when_env_malformed(exchange_db, settlement_on, monkeypatch):
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "exchange-bridge-wallet")
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-badaddr")
    h = _handler()
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", nonce=1))
    assert _last_status(h) == 503
    assert _orders_count(exchange_db) == 0


def test_buy_refused_when_env_not_checksummed(exchange_db, settlement_on, monkeypatch):
    # Valid shape but not the EIP-55 form — the vector's checksum has
    # uppercase letters, so the lowered spelling must fail.
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", _BRIDGE_ADDR.lower())
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-lowcase")
    h = _handler()
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", nonce=1))
    assert _last_status(h) == 503
    assert _orders_count(exchange_db) == 0


def test_flag_off_never_reads_destination_envs(exchange_db, monkeypatch):
    # Settlement off + both destination envs unset: placement is byte-
    # identical to before the guard — the order lands unfunded, no funding
    # instruction is attached.
    monkeypatch.delenv("AIT_SELL_ESCROW", raising=False)
    monkeypatch.delenv("BRIDGE_ETH_ADDRESS", raising=False)
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-flagoff")
    h = _handler()
    _place(exchange_db, h, _order_body(node.address, node.key.hex(), side="BUY", nonce=1))
    doc = _last_json(h)
    assert doc["status"] == "open"
    assert doc["funded_state"] == "unfunded"
    assert "funding" not in doc
