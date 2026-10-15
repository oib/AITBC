"""ETH-8 phase 3 (C4): the internal settlement endpoint — the wallet
bridge's only write path into exchange.db. Loopback raw peer +
EXCHANGE_API_KEY, flag-gated to 404, forward-only trade mirroring,
idempotent event dedupe.

Also covers the two C4 review rules: a settled trade never restores
spendable balance (committed is cumulative), and per-fill fees are the
difference of cumulative fee so their sum can never exceed fee(amount).

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


@pytest.fixture
def settlement_on(monkeypatch):
    monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
    # Placement under the flag refuses when a funding destination env is
    # unset — same EIP-55 test vectors as test_funded_orders.
    monkeypatch.setenv("AIT_SELL_ESCROW", "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359")


@pytest.fixture
def exchange_db(tmp_path, monkeypatch):
    """Real schema (see test_funded_orders for why the conftest fixture is
    not enough for phase-3 tests)."""
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
    from apps.exchange.simple_exchange.handlers.base import BaseHandler

    h = MagicMock(spec=ExchangeMixin)
    h.send_error = MagicMock()
    h.send_json_response = MagicMock()
    h._client_ip = MagicMock(return_value="127.0.0.1")
    h._require_api_key = BaseHandler._require_api_key.__get__(h, BaseHandler)
    for name in (
        "handle_node_register",
        "handle_place_order",
        "handle_set_payout",
        "handle_internal_settlement",
        "_event_prepaid_credit",
        "_event_order_funded",
        "_event_order_backing_expired",
        "_event_debit_refund",
        "_event_trade_state",
        "_internal_txn",
        "_peer_is_loopback",
        "_raw_peer_ip",
        "_place_order_signed",
        "_verify_signed_body",
        "_order_envelope_error",
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
        "_registry_status",
        "_registry_labels",
        "_expected_nonce",
        "_claim_nonce",
        "_order_by_envelope",
        "_chain_head_height",
        "_ait_eth_band",
        "_ait_eth_rate",
        "_watchlisted_addresses",
        "_node_rows",
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


def _post(h, db_path, body, peer="127.0.0.1", key="test-key", extra_headers=None):
    h.client_address = (peer, 43210)
    h.headers = dict(extra_headers or {})
    if key:
        h.headers["X-Api-Key"] = key
    h._read_json_body = MagicMock(return_value=body)
    h.send_error.reset_mock()
    h.send_json_response.reset_mock()
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_internal_settlement()


def _last_json(h):
    assert h.send_json_response.called, f"no response; send_error={h.send_error.call_args_list}"
    return h.send_json_response.call_args[0][0]


def _row(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def _make_filled_buy(exchange_db, settlement_on, amount="10", price="0.001"):
    """Resting funded sell + funded buy that fills it fully. Returns
    (handler, buy_doc, buyer_account, sell_order_id, trade_id)."""
    seller, payout = Account.create(), Account.create()
    _register(exchange_db, seller.address, seller.key.hex(), "n-isell")
    h = _handler()
    _set_payout(exchange_db, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(seller.address, seller.key.hex(), side="SELL", amount=amount, price=price, nonce=2))
    sell_doc = _last_json(h)
    lock = int((Decimal(amount) + Decimal(amount) * Decimal("0.01")) * 100_000_000)  # covers a pct<=1% fee too
    _post(
        h,
        exchange_db,
        {"event": "order_funded", "order_id": sell_doc["id"], "locked_ticks": lock, "backing_tx_hash": "0xlock"},
    )
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-ibuy")
    _prepay(exchange_db, buyer.address, "0.05")
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=amount, price=price, nonce=1))
    buy_doc = _last_json(h)
    trade = _row(exchange_db, "SELECT id FROM trades ORDER BY id DESC LIMIT 1")
    return h, buy_doc, buyer, sell_doc["id"], (trade[0] if trade else None)


def _prepay(db_path, address, amount_eth):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO prepaid_deposits (node_address, amount_eth, eth_tx_hash) VALUES (?, ?, ?)",
        (address, str(amount_eth), f"0xdep{address[-6:]}"),
    )
    conn.commit()
    conn.close()


# --- access gates -----------------------------------------------------------


def test_flag_off_503(exchange_db):
    """Flag-off answers 503 'disabled', never 404 — the wallet monitor maps
    404 to 'order gone' and refunds the lock; a flag mismatch must stay
    retryable (ETH-JOIN gap 3)."""
    h = _handler()
    h.client_address = ("127.0.0.1", 43210)
    h.headers = {"X-Api-Key": "test-key"}
    h._read_json_body = MagicMock(return_value={"event": "debit_refund", "order_id": 1})
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=exchange_db):
        h.handle_internal_settlement()
    assert not h.send_error.called
    args, kwargs = h.send_json_response.call_args
    assert kwargs.get("status") == 503
    assert "disabled" in str(args[0].get("error", ""))


def test_non_loopback_refused(exchange_db, settlement_on):
    h = _handler()
    _post(h, exchange_db, {"event": "debit_refund", "order_id": 1}, peer="10.0.0.5")
    assert h.send_error.called and h.send_error.call_args[0][0] == 403


def test_bad_api_key_refused(exchange_db, settlement_on):
    h = _handler()
    _post(h, exchange_db, {"event": "debit_refund", "order_id": 1}, key="wrong")
    assert h.send_error.called and h.send_error.call_args[0][0] == 401


def test_proxy_headers_refused(exchange_db, settlement_on):
    # Loopback peer + valid key still refuses when a proxy stamp is present —
    # a future nginx rule must never reach this endpoint.
    for stamp in ("X-Forwarded-For", "X-Real-IP"):
        h = _handler()
        _post(h, exchange_db, {"event": "debit_refund", "order_id": 1}, extra_headers={stamp: "127.0.0.1"})
        assert h.send_error.called and h.send_error.call_args[0][0] == 403, stamp


# --- prepaid_credit ----------------------------------------------------------


def test_prepaid_credit_funds_waiting_buy_and_matches(exchange_db, settlement_on):
    # Resting funded sell.
    seller, payout = Account.create(), Account.create()
    _register(exchange_db, seller.address, seller.key.hex(), "n-csell")
    h = _handler()
    _set_payout(exchange_db, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(seller.address, seller.key.hex(), side="SELL", amount=5, price="0.001", nonce=2))
    sell_doc = _last_json(h)
    _post(
        h,
        exchange_db,
        {"event": "order_funded", "order_id": sell_doc["id"], "locked_ticks": int(Decimal("5") * 100_000_000)},
    )
    # Unfunded buy waits; the credit event funds and matches it in one txn.
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-cbuy")
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=5, price="0.001", nonce=1))
    buy_doc = _last_json(h)
    assert buy_doc["funded_state"] == "unfunded"
    _post(
        h,
        exchange_db,
        {"event": "prepaid_credit", "node_address": buyer.address, "amount_eth": "0.02", "eth_tx_hash": "0xc1"},
    )
    resp = _last_json(h)
    assert resp["ok"] and resp["credited"] and resp["funded_orders"] == [buy_doc["id"]]
    trades = _row(exchange_db, "SELECT buy_order_id, sell_order_id, settlement_state FROM trades")
    assert trades[0] == buy_doc["id"] and trades[1] == sell_doc["id"] and trades[2] == "locked"
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (buy_doc["id"],))[0] == "funded"


def test_prepaid_credit_canonicalizes_lowercase(exchange_db, settlement_on):
    # The tag text arrives however the user typed it — a lowercase address
    # must credit the same node and fund its waiting orders.
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-lower")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=5, price="0.001", nonce=1))
    buy_doc = _last_json(h)
    assert buy_doc["funded_state"] == "unfunded"
    _post(
        h,
        exchange_db,
        {"event": "prepaid_credit", "node_address": buyer.address.lower(), "amount_eth": "0.02", "eth_tx_hash": "0xlc"},
    )
    resp = _last_json(h)
    assert resp["ok"] and resp["credited"] and resp["funded_orders"] == [buy_doc["id"]]
    assert _row(exchange_db, "SELECT node_address FROM prepaid_deposits")[0] == buyer.address


def test_prepaid_credit_unregistered_node_refused(exchange_db, settlement_on):
    # Tag points at an address that never registered — refuse 409 and credit
    # nothing; the monitor records the deposit as unattributable.
    node = Account.create()
    h = _handler()
    _post(
        h,
        exchange_db,
        {"event": "prepaid_credit", "node_address": node.address, "amount_eth": "0.02", "eth_tx_hash": "0xunreg"},
    )
    resp = _last_json(h)
    assert "registered" in resp.get("error", "")
    assert h.send_json_response.call_args[1].get("status") == 409
    assert _row(exchange_db, "SELECT COUNT(*) FROM prepaid_deposits")[0] == 0


def test_prepaid_credit_invalid_hex_refused(exchange_db, settlement_on):
    h = _handler()
    _post(
        h,
        exchange_db,
        {"event": "prepaid_credit", "node_address": "0xZZZZ1234", "amount_eth": "0.02", "eth_tx_hash": "0xbad"},
    )
    assert h.send_error.called and h.send_error.call_args[0][0] == 400
    assert _row(exchange_db, "SELECT COUNT(*) FROM prepaid_deposits")[0] == 0


def test_prepaid_credit_dedupes_on_tx_hash(exchange_db, settlement_on):
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-dedup")
    h = _handler()
    body = {"event": "prepaid_credit", "node_address": node.address, "amount_eth": "0.01", "eth_tx_hash": "0xsame"}
    _post(h, exchange_db, body)
    _post(h, exchange_db, body)
    resp = _last_json(h)
    assert resp["ok"] and resp["credited"] is False
    assert _row(exchange_db, "SELECT COUNT(*) FROM prepaid_deposits")[0] == 1


# --- order_funded -------------------------------------------------------------


def test_order_funded_insufficient_cover_refused(exchange_db, settlement_on):
    seller, payout = Account.create(), Account.create()
    _register(exchange_db, seller.address, seller.key.hex(), "n-undercov")
    h = _handler()
    _set_payout(exchange_db, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(seller.address, seller.key.hex(), side="SELL", amount=10, price="0.001", nonce=2))
    sell_doc = _last_json(h)
    _post(
        h,
        exchange_db,
        {"event": "order_funded", "order_id": sell_doc["id"], "locked_ticks": int(Decimal("4") * 100_000_000)},
    )
    resp = _last_json(h)
    assert "cover" in resp.get("error", "").lower()
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (sell_doc["id"],))[0] == "unfunded"


def test_order_funded_rematch_fills_resting_buy(exchange_db, settlement_on):
    # Resting funded buy waits; the sell's funding event re-matches it.
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-rbuy")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=5, price="0.001", nonce=1))
    buy_doc = _last_json(h)
    seller, payout = Account.create(), Account.create()
    _register(exchange_db, seller.address, seller.key.hex(), "n-rsell")
    _set_payout(exchange_db, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(seller.address, seller.key.hex(), side="SELL", amount=5, price="0.001", nonce=2))
    sell_doc = _last_json(h)
    _post(
        h,
        exchange_db,
        {"event": "order_funded", "order_id": sell_doc["id"], "locked_ticks": int(Decimal("5") * 100_000_000)},
    )
    resp = _last_json(h)
    assert resp["ok"] and resp["funded_state"] == "funded"
    trades = _row(exchange_db, "SELECT buy_order_id, sell_order_id FROM trades")
    assert trades == (buy_doc["id"], sell_doc["id"])
    # The resting buy filled -> debit closed 'consumed'.
    assert _row(exchange_db, "SELECT state, committed_eth FROM prepaid_debits WHERE order_id = ?", (buy_doc["id"],)) == (
        "consumed",
        "0.005",
    )


# --- backing_expired / debit_refund ------------------------------------------


def test_backing_expired_flips_and_closes_debit(exchange_db, settlement_on):
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-bexp")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=5, price="0.001", nonce=1))
    buy_doc = _last_json(h)
    _post(h, exchange_db, {"event": "order_backing_expired", "order_id": buy_doc["id"]})
    resp = _last_json(h)
    assert resp["ok"] and resp["funded_state"] == "backing_expired"
    assert _row(exchange_db, "SELECT state FROM prepaid_debits WHERE order_id = ?", (buy_doc["id"],))[0] == "refunded"


def test_debit_refund_idempotent(exchange_db, settlement_on):
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-dref")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=5, price="0.001", nonce=1))
    buy_doc = _last_json(h)
    _post(h, exchange_db, {"event": "debit_refund", "order_id": buy_doc["id"]})
    resp = _last_json(h)
    assert resp["ok"] and resp["refunded_eth"] == "0.005" and resp["was"] == "open"
    _post(h, exchange_db, {"event": "debit_refund", "order_id": buy_doc["id"]})
    resp = _last_json(h)
    assert resp["ok"] and resp["refunded_eth"] is None and resp["was"] == "refunded"


# --- trade_state -------------------------------------------------------------


def test_trade_state_forward_only(exchange_db, settlement_on):
    h, buy_doc, _buyer, _sell_id, trade_id = _make_filled_buy(exchange_db, settlement_on)
    # Backwards: locked -> releasing first, then a regression is refused.
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "releasing", "eth_tx_hash": "0xeth"})
    assert _last_json(h)["settlement_state"] == "releasing"
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "locked"})
    resp = _last_json(h)
    assert "cannot move" in resp.get("error", "")
    # Drive to settled, then prove terminal.
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "released"})
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "settling"})
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "settled", "ait_tx_hash": "0xait"})
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "releasing"})
    assert "cannot move" in _last_json(h).get("error", "")
    row = _row(
        exchange_db,
        "SELECT settlement_state, settlement_eth_tx_hash, settlement_ait_tx_hash FROM trades WHERE id = ?",
        (trade_id,),
    )
    assert row == ("settled", "0xeth", "0xait")


def test_trade_state_same_state_is_noop(exchange_db, settlement_on):
    h, _b, _buyer, _sid, trade_id = _make_filled_buy(exchange_db, settlement_on)
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "locked"})
    resp = _last_json(h)
    assert resp["ok"] and resp["unchanged"]


def test_settled_trade_does_not_restore_spendable(exchange_db, settlement_on):
    """Review rule: committed_eth is cumulative — settlement of the trade
    must NOT return the ETH to the buyer's spendable balance."""
    h, buy_doc, buyer, _sid, trade_id = _make_filled_buy(exchange_db, settlement_on)
    # The buy filled fully: debit 0.01 committed 0.01 'consumed'. Spendable
    # is deposits(0.05) - committed(0.01) = 0.04.
    for state in ("releasing", "released", "settling", "settled"):
        _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": state})
    deb = _row(exchange_db, "SELECT committed_eth, state FROM prepaid_debits WHERE order_id = ?", (buy_doc["id"],))
    assert deb == ("0.01", "consumed")  # unchanged by settlement
    # A new buy needing 0.045 must still be refused — the 0.01 is gone.
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=45, price="0.001", nonce=2))
    assert _last_json(h)["funded_state"] == "unfunded"


def test_refunded_trade_releases_commitment(exchange_db, settlement_on):
    """Only a refund decrements committed_eth — the buyer's ETH cost comes
    back to spendable (the seller's AIT goes back via the escrow refund)."""
    # Resting sell of 4; buy of 10 partially fills it -> committed 0.004.
    seller, payout = Account.create(), Account.create()
    _register(exchange_db, seller.address, seller.key.hex(), "n-rfs")
    h = _handler()
    _set_payout(exchange_db, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(seller.address, seller.key.hex(), side="SELL", amount=4, price="0.001", nonce=2))
    sell_doc = _last_json(h)
    _post(
        h, exchange_db, {"event": "order_funded", "order_id": sell_doc["id"], "locked_ticks": int(Decimal("4") * 100_000_000)}
    )
    buyer = Account.create()
    buyer_key = buyer.key.hex()
    _register(exchange_db, buyer.address, buyer_key, "n-rfb")
    _prepay(exchange_db, buyer.address, "0.05")
    _place(exchange_db, h, _order_body(buyer.address, buyer_key, side="BUY", amount=10, price="0.001", nonce=1))
    buy_doc = _last_json(h)
    assert buy_doc["filled"] == "4"
    trade_id = _row(exchange_db, "SELECT id FROM trades")[0]
    # Trade proves not_sent -> refund path releases the commitment.
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "releasing"})
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "refund_pending"})
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "refunding"})
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "refunded"})
    resp = _last_json(h)
    assert resp["ok"] and resp["released_eth"] == "0.004"
    deb = _row(exchange_db, "SELECT committed_eth, state FROM prepaid_debits WHERE order_id = ?", (buy_doc["id"],))
    assert Decimal(deb[0]) == 0 and deb[1] == "open"  # commitment released; debit still open


# --- fee cumulative difference ------------------------------------------------


def test_fill_fees_sum_within_lock_cover(exchange_db, settlement_on, monkeypatch):
    """Three odd fills: per-fill fees are the cumulative difference, so their
    sum can never exceed fee(amount) — the escrow sweep always has the fee."""
    monkeypatch.setenv("EXCHANGE_FEE_PCT", "0.017")
    seller, payout = Account.create(), Account.create()
    _register(exchange_db, seller.address, seller.key.hex(), "n-feesell")
    h = _handler()
    _set_payout(exchange_db, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(seller.address, seller.key.hex(), side="SELL", amount=10, price="0.001", nonce=2))
    sell_doc = _last_json(h)
    lock = int(Decimal("10.17") * 100_000_000)  # amount + fee(10)
    _post(h, exchange_db, {"event": "order_funded", "order_id": sell_doc["id"], "locked_ticks": lock})
    for i, amt in enumerate(("3.333333", "3.333333", "3.333334"), start=1):
        buyer = Account.create()
        _register(exchange_db, buyer.address, buyer.key.hex(), f"n-feeb{i}")
        _prepay(exchange_db, buyer.address, "0.05")
        _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=amt, price="0.001", nonce=1))
        assert _last_json(h)["status"] == "filled"
    conn = sqlite3.connect(exchange_db)
    fees = [Decimal(r[0]) for r in conn.execute("SELECT fee_ait FROM trades ORDER BY id")]
    conn.close()
    fee_of_amount = (Decimal("10") * Decimal("0.017")).quantize(Decimal("0.000001"))
    assert len(fees) == 3
    assert sum(fees) <= fee_of_amount
    # Fully filled -> the cumulative difference sums to exactly fee(amount).
    assert sum(fees) == fee_of_amount
