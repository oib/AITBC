"""#3047 (AUDIT-EXCHANGE-EXPIRY-FAILOPEN-1): settlement-mode funding and
matching must fail closed when no trustworthy chain head exists.

Before the fix, ``prepaid_credit``/``order_funded`` events carried no head,
so ``_match_orders_in_txn`` fell back to a live ``/rpc/head`` probe that is
missing during exactly the outage that strands the monitor's own height
probe — ``head_height=None`` skipped both the lazy expiry sweep and the
expiry predicate, and an expired-but-lazily-open order stayed matchable on
the funded money path (the #1554 unsigned-path residual leaking into
settlement mode).

Pins:
- settlement event + no event head + dead probe -> 503, nothing funded,
  nothing matched, nothing written (monitor retries next poll);
- event head present -> expiry enforced: expired orders are swept, never
  funded or matched;
- probe fallback still counts as a trustworthy head;
- order_funded on an already-expired SELL -> 409 (monitor refunds the
  lock) instead of funding it;
- the unsigned/flag-off #1554 residual is preserved byte-for-byte.

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
    monkeypatch.setenv("AIT_SELL_ESCROW", "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")
    monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359")


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


def _handler(head=1000):
    from apps.exchange.simple_exchange.handlers.base import BaseHandler

    h = MagicMock(spec=ExchangeMixin)
    h.send_error = MagicMock()
    h.send_json_response = MagicMock()
    h._client_ip = MagicMock(return_value="127.0.0.1")
    h._require_api_key = BaseHandler._require_api_key.__get__(h, BaseHandler)
    h._require_internal_api_key = BaseHandler._require_internal_api_key.__get__(h, BaseHandler)
    for name in (
        "handle_internal_settlement",
        "_event_prepaid_credit",
        "_event_order_funded",
        "_event_order_backing_expired",
        "_event_debit_refund",
        "_event_trade_state",
        "_internal_txn",
        "_peer_is_loopback",
        "_raw_peer_ip",
        "_match_orders_in_txn",
        "_expire_open_orders",
        "_chain_head_height",
    ):
        if hasattr(ExchangeMixin, name):
            attr = getattr(ExchangeMixin, name)
            if name in ("_expire_open_orders",):
                setattr(h, name, attr)
            else:
                setattr(h, name, attr.__get__(h, ExchangeMixin))
    h._chain_head_height = MagicMock(return_value=head)
    return h


def _txh(n: int) -> str:
    """Well-formed 0x + 64-hex chain tx hash (#3048 shape checks)."""
    return "0x" + f"{n:064x}"


def _post(h, db_path, body, head=1000):
    h.client_address = ("127.0.0.1", 43210)
    h.headers = {"X-Api-Key": "test-key"}
    h._read_json_body = MagicMock(return_value=body)
    h.send_error.reset_mock()
    h.send_json_response.reset_mock()
    if head != "keep":
        h._chain_head_height = MagicMock(return_value=head)
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


def _register_node(db_path, address):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO node_registry (address, label, status) VALUES (?, ?, 'registered')", (address, f"n-{address[-6:]}")
    )
    conn.commit()
    conn.close()


def _insert_order(
    db_path,
    *,
    order_type,
    user,
    amount="5",
    price="0.001",
    expiry_height=None,
    funded_state="unfunded",
    locked_ticks=None,
    status="open",
):
    """Resting order row in the shape the settlement events consume."""
    from apps.exchange.simple_exchange.db import to_ticks

    amount_d, price_d = Decimal(amount), Decimal(price)
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO orders (order_type, amount, price, total, filled, remaining, status, user_address,"
        " amount_ticks, price_ticks, filled_ticks, remaining_ticks, expiry_height, funded_state, locked_ticks)"
        " VALUES (?, ?, ?, ?, '0', ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
        (
            order_type,
            str(amount_d),
            str(price_d),
            str(amount_d * price_d),
            str(amount_d),
            status,
            user,
            to_ticks(amount_d),
            to_ticks(price_d),
            to_ticks(amount_d),
            expiry_height,
            funded_state,
            locked_ticks,
        ),
    )
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def _expired_book(db_path):
    """The #3047 shape: an expired-but-lazily-open unfunded BUY plus a
    compatible funded SELL resting. Returns (buyer, seller, buy_id,
    sell_id)."""
    buyer, seller = Account.create(), Account.create()
    _register_node(db_path, buyer.address)
    _register_node(db_path, seller.address)
    amount_ticks = int(Decimal("5") * 100_000_000)
    buy_id = _insert_order(db_path, order_type="BUY", user=buyer.address, expiry_height=500, funded_state="unfunded")
    sell_id = _insert_order(
        db_path,
        order_type="SELL",
        user=seller.address,
        expiry_height=None,
        funded_state="funded",
        locked_ticks=amount_ticks,
    )
    return buyer, seller, buy_id, sell_id


# --- prepaid_credit: fail closed --------------------------------------------


def test_prepaid_credit_no_head_anywhere_refuses_503(exchange_db, settlement_on):
    """The defect sequence: expired BUY still lazily open, funded SELL
    resting, credit arrives while BOTH the monitor's stamp and the node's
    /rpc/head probe are missing -> 503, nothing funded, nothing matched,
    nothing written. The monitor leaves the deposit unmarked and retries."""
    buyer, _seller, buy_id, sell_id = _expired_book(exchange_db)
    h = _handler(head=None)
    _post(
        h,
        exchange_db,
        {"event": "prepaid_credit", "node_address": buyer.address, "amount_eth": "0.05", "eth_tx_hash": _txh(41)},
        head=None,
    )
    resp = _last_json(h)
    assert h.send_json_response.call_args[1].get("status") == 503
    assert "head" in resp.get("error", "").lower()
    # Atomic refusal — the deposit itself is not even credited yet.
    assert _row(exchange_db, "SELECT COUNT(*) FROM prepaid_deposits")[0] == 0
    assert _row(exchange_db, "SELECT COUNT(*) FROM prepaid_debits")[0] == 0
    assert _row(exchange_db, "SELECT COUNT(*) FROM trades")[0] == 0
    assert _row(exchange_db, "SELECT status, funded_state FROM orders WHERE id = ?", (buy_id,)) == ("open", "unfunded")
    assert _row(exchange_db, "SELECT status, funded_state FROM orders WHERE id = ?", (sell_id,)) == ("open", "funded")


def test_prepaid_credit_event_head_enforces_expiry(exchange_db, settlement_on):
    """With the monitor's stamped head (600 > expiry 500) the credit still
    lands, but the expired BUY is swept first — never debited, never
    matched; the deposit itself credits normally."""
    buyer, _seller, buy_id, sell_id = _expired_book(exchange_db)
    h = _handler(head=None)  # node probe dead — the event head must carry it
    _post(
        h,
        exchange_db,
        {
            "event": "prepaid_credit",
            "node_address": buyer.address,
            "amount_eth": "0.05",
            "eth_tx_hash": _txh(42),
            "head": 600,
        },
        head=None,
    )
    resp = _last_json(h)
    assert resp["ok"] and resp["credited"]
    assert resp["funded_orders"] == []
    assert _row(exchange_db, "SELECT status, funded_state FROM orders WHERE id = ?", (buy_id,)) == (
        "expired",
        "backing_expired",
    )
    assert _row(exchange_db, "SELECT COUNT(*) FROM prepaid_debits")[0] == 0
    assert _row(exchange_db, "SELECT COUNT(*) FROM trades")[0] == 0
    assert _row(exchange_db, "SELECT status FROM orders WHERE id = ?", (sell_id,))[0] == "open"


def test_prepaid_credit_probe_head_enforces_expiry(exchange_db, settlement_on):
    """No stamp but a live /rpc/head probe is still a trustworthy head —
    same expiry enforcement through the fallback."""
    buyer, _seller, buy_id, _sell_id = _expired_book(exchange_db)
    h = _handler(head=600)
    _post(
        h,
        exchange_db,
        {"event": "prepaid_credit", "node_address": buyer.address, "amount_eth": "0.05", "eth_tx_hash": _txh(43)},
        head="keep",
    )
    resp = _last_json(h)
    assert resp["ok"] and resp["credited"]
    assert _row(exchange_db, "SELECT status FROM orders WHERE id = ?", (buy_id,))[0] == "expired"
    assert _row(exchange_db, "SELECT COUNT(*) FROM trades")[0] == 0


def test_prepaid_credit_unexpired_buy_still_funds_and_matches(exchange_db, settlement_on):
    """Guard against over-blocking: a live BUY + stamped head funds and
    matches exactly as before."""
    buyer, seller = Account.create(), Account.create()
    _register_node(exchange_db, buyer.address)
    _register_node(exchange_db, seller.address)
    amount_ticks = int(Decimal("5") * 100_000_000)
    buy_id = _insert_order(exchange_db, order_type="BUY", user=buyer.address, expiry_height=5000, funded_state="unfunded")
    sell_id = _insert_order(
        exchange_db,
        order_type="SELL",
        user=seller.address,
        expiry_height=None,
        funded_state="funded",
        locked_ticks=amount_ticks,
    )
    h = _handler(head=None)
    _post(
        h,
        exchange_db,
        {
            "event": "prepaid_credit",
            "node_address": buyer.address,
            "amount_eth": "0.05",
            "eth_tx_hash": _txh(44),
            "head": 1000,
        },
        head=None,
    )
    resp = _last_json(h)
    assert resp["ok"] and resp["funded_orders"] == [buy_id]
    trade = _row(exchange_db, "SELECT buy_order_id, sell_order_id, settlement_state FROM trades")
    assert trade == (buy_id, sell_id, "locked")


# --- order_funded -------------------------------------------------------------


def test_order_funded_no_head_anywhere_refuses_503(exchange_db, settlement_on):
    """Same fail-closed rule on the escrow-lock lane: no stamp + dead
    probe -> 503 retryable, the SELL stays unfunded."""
    seller = Account.create()
    _register_node(exchange_db, seller.address)
    amount_ticks = int(Decimal("5") * 100_000_000)
    sell_id = _insert_order(exchange_db, order_type="SELL", user=seller.address, expiry_height=None, funded_state="unfunded")
    h = _handler(head=None)
    _post(
        h,
        exchange_db,
        {"event": "order_funded", "order_id": sell_id, "locked_ticks": amount_ticks, "backing_tx_hash": _txh(45)},
        head=None,
    )
    assert h.send_json_response.call_args[1].get("status") == 503
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (sell_id,))[0] == "unfunded"


def test_order_funded_expired_sell_refused_409(exchange_db, settlement_on):
    """A lock landing after the SELL's expiry_height must not fund it —
    409 sends the monitor down the lock-refund path."""
    buyer, seller = Account.create(), Account.create()
    _register_node(exchange_db, buyer.address)
    _register_node(exchange_db, seller.address)
    amount_ticks = int(Decimal("5") * 100_000_000)
    _insert_order(exchange_db, order_type="BUY", user=buyer.address, expiry_height=5000, funded_state="funded")
    sell_id = _insert_order(exchange_db, order_type="SELL", user=seller.address, expiry_height=500, funded_state="unfunded")
    h = _handler(head=None)
    _post(
        h,
        exchange_db,
        {
            "event": "order_funded",
            "order_id": sell_id,
            "locked_ticks": amount_ticks,
            "backing_tx_hash": _txh(46),
            "head": 600,
        },
        head=None,
    )
    resp = _last_json(h)
    assert h.send_json_response.call_args[1].get("status") == 409
    assert "expired" in resp.get("error", "").lower()
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (sell_id,))[0] == "unfunded"
    assert _row(exchange_db, "SELECT COUNT(*) FROM trades")[0] == 0


# --- unsigned path: #1554 residual preserved ---------------------------------


def test_unsigned_match_still_fails_open_on_dead_rpc(temp_db):
    """#1554 documented residual: the flag-off/unsigned match path keeps its
    fail-open when no head exists anywhere — the fix targets settlement
    mode only. (Settlement is off in this fixture; unsigned orders never
    reach 'funded' anyway, so the residual cannot move money.)"""
    from apps.exchange.simple_exchange.handlers.exchange_orders import ExchangeOrdersMixin

    amount_d, price_d = Decimal("10"), Decimal("5")
    conn = sqlite3.connect(temp_db)
    conn.execute(
        "INSERT INTO orders (order_type, amount, price, total, filled, remaining, status, user_address,"
        " amount_ticks, price_ticks, filled_ticks, remaining_ticks, expiry_height)"
        " VALUES ('SELL', ?, ?, ?, '0', ?, 'open', '0xseller', ?, ?, 0, ?, 50)",
        (
            str(amount_d),
            str(price_d),
            str(amount_d * price_d),
            str(amount_d),
            int(amount_d * 100_000_000),
            int(price_d * 100_000_000),
            int(amount_d * 100_000_000),
        ),
    )
    conn.commit()
    conn.close()

    handler = MagicMock(spec=ExchangeMixin)
    handler._match_orders_in_txn = ExchangeMixin._match_orders_in_txn.__get__(handler, ExchangeMixin)
    handler._expire_open_orders = ExchangeOrdersMixin._expire_open_orders
    handler._chain_head_height = MagicMock(return_value=None)
    order = {
        "order_type": "BUY",
        "amount": "5",
        "price": "10",
        "total": "50",
        "filled": "0",
        "remaining": "5",
        "status": "open",
    }
    conn = sqlite3.connect(temp_db, timeout=30)
    conn.execute("BEGIN IMMEDIATE")
    handler._match_orders_in_txn(conn.cursor(), order)
    conn.commit()
    conn.close()
    # Residual preserved: dead RPC -> expired SELL still matches flag-off.
    assert _row(temp_db, "SELECT COUNT(*) FROM trades")[0] == 1


@pytest.fixture
def temp_db(tmp_path):
    """Bare orders/trades schema for the matcher-level residual pin."""

    path = str(tmp_path / "bare.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_type TEXT NOT NULL, amount TEXT NOT NULL,"
        " price TEXT NOT NULL, total TEXT NOT NULL, filled TEXT DEFAULT '0', remaining TEXT NOT NULL,"
        " status TEXT DEFAULT 'open', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, user_address TEXT,"
        " tx_hash TEXT, amount_ticks INTEGER, price_ticks INTEGER, filled_ticks INTEGER DEFAULT 0,"
        " remaining_ticks INTEGER, signature TEXT, envelope_hash TEXT, account_nonce INTEGER,"
        " expiry_height INTEGER, funded_state TEXT NOT NULL DEFAULT 'unfunded', cancelled_at TIMESTAMP,"
        " backing_tx_hash TEXT, locked_ticks INTEGER, seller_eth_address TEXT, funded_at TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, amount TEXT, price TEXT, total TEXT,"
        " created_at TIMESTAMP, buyer_address TEXT, seller_address TEXT, fee_ait TEXT, buy_order_id INTEGER,"
        " sell_order_id INTEGER, settlement_state TEXT, settlement_eth_tx_hash TEXT, settlement_ait_tx_hash TEXT,"
        " settlement_fee_tx_hash TEXT)"
    )
    conn.commit()
    conn.close()
    return path
