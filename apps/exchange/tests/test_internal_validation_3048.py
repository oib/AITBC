"""Pins for AUDIT-EXCHANGE-INTERNAL-VALIDATION-1 (#3048).

The internal settlement endpoint is loopback+key gated, but the shared
EXCHANGE_API_KEY made it a full-custody oracle: it enforced almost no
event preconditions, so a buggy monitor (or a leaked broader key) could
mint prepaid credit on misshapen hashes, fund a SELL on empty backing
evidence, expire orders unconditionally, refund debits on live orders,
and jump the trade mirror straight to ``refunded``.

Pins cover every closed gap: hash shape + normalization, per-event
preconditions, the dedicated internal key, and the tightened
needs_review_sweep transition map.
"""

import importlib.util
import sqlite3
from decimal import Decimal
from pathlib import Path

from eth_account import Account

# Sibling harness by file path — the bare ``tests`` package name collides
# with the repo-level tests/ dir under pytest's pythonpath, so a normal
# ``from tests.test_internal_settlement import …`` does not resolve.
_spec = importlib.util.spec_from_file_location(
    "_internal_settlement_harness_3048",
    Path(__file__).with_name("test_internal_settlement.py"),
)
_harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_harness)

_env = _harness._env  # noqa: F401 - autouse fixture
exchange_db = _harness.exchange_db  # noqa: F401 - fixture
settlement_on = _harness.settlement_on  # noqa: F401 - fixture
_handler = _harness._handler
_last_json = _harness._last_json
_make_filled_buy = _harness._make_filled_buy
_order_body = _harness._order_body
_place = _harness._place
_post = _harness._post
_prepay = _harness._prepay
_register = _harness._register
_row = _harness._row
_set_payout = _harness._set_payout
_txh = _harness._txh


def _close_order(db_path, order_id):
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()


def _funded_sell(h, db_path):
    """Registered seller + funded SELL order; returns the order doc."""
    seller, payout = Account.create(), Account.create()
    _register(db_path, seller.address, seller.key.hex(), "n-vsell")
    _set_payout(db_path, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(db_path, h, _order_body(seller.address, seller.key.hex(), side="SELL", amount=5, price="0.001", nonce=2))
    doc = _last_json(h)
    _post(
        h,
        db_path,
        {
            "event": "order_funded",
            "order_id": doc["id"],
            "locked_ticks": int(Decimal("5") * 100_000_000),
            "backing_tx_hash": _txh(101),
        },
    )
    return doc


# --- prepaid_credit: hash shape + normalization -----------------------------


def test_prepaid_credit_rejects_misshapen_tx_hash(exchange_db, settlement_on):
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-vhash")
    h = _handler()
    for bad in ("", "0x", "0xzz", "0x" + "ab" * 31, "0x" + "ab" * 65, "notahash", 12345):
        _post(
            h,
            exchange_db,
            {"event": "prepaid_credit", "node_address": node.address, "amount_eth": "0.01", "eth_tx_hash": bad, "head": 1000},
        )
        assert h.send_error.called and h.send_error.call_args[0][0] == 400, bad
    assert _row(exchange_db, "SELECT COUNT(*) FROM prepaid_deposits")[0] == 0


def test_prepaid_credit_case_variant_dedupes(exchange_db, settlement_on):
    """#3048: '0xAB…' and '0xab…' are the same chain tx — the UNIQUE
    dedupe only works once the hash is normalized before insert."""
    node = Account.create()
    _register(exchange_db, node.address, node.key.hex(), "n-vdedup")
    h = _handler()
    upper = "0x" + "AB" * 32
    lower = "0x" + "ab" * 32
    for txh in (upper, lower):
        _post(
            h,
            exchange_db,
            {"event": "prepaid_credit", "node_address": node.address, "amount_eth": "0.01", "eth_tx_hash": txh, "head": 1000},
        )
    resp = _last_json(h)
    assert resp["ok"] and resp["credited"] is False
    assert _row(exchange_db, "SELECT COUNT(*) FROM prepaid_deposits")[0] == 1
    # Stored normalized — lowercase canonical form.
    assert _row(exchange_db, "SELECT eth_tx_hash FROM prepaid_deposits")[0] == lower


# --- order_funded: backing evidence -----------------------------------------


def test_order_funded_requires_backing_hash(exchange_db, settlement_on):
    seller, payout = Account.create(), Account.create()
    _register(exchange_db, seller.address, seller.key.hex(), "n-vob1")
    h = _handler()
    _set_payout(exchange_db, h, seller.address, seller.key.hex(), payout.address, nonce=1)
    _place(exchange_db, h, _order_body(seller.address, seller.key.hex(), side="SELL", amount=5, price="0.001", nonce=2))
    doc = _last_json(h)
    for bad in (None, "", "0xlock", "0x" + "zz" * 32):
        body = {"event": "order_funded", "order_id": doc["id"], "locked_ticks": int(Decimal("5") * 100_000_000), "head": 1000}
        if bad is not None:
            body["backing_tx_hash"] = bad
        _post(h, exchange_db, body)
        assert h.send_error.called and h.send_error.call_args[0][0] == 400, bad
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (doc["id"],))[0] == "unfunded"


def test_order_funded_backing_hash_is_unique_across_orders(exchange_db, settlement_on):
    """One escrow lock covers one order — the same backing hash funding a
    second SELL would count one lock as cover for two ETH releases."""
    h = _handler()
    first = _funded_sell(h, exchange_db)
    seller2, payout2 = Account.create(), Account.create()
    _register(exchange_db, seller2.address, seller2.key.hex(), "n-vob2")
    _set_payout(exchange_db, h, seller2.address, seller2.key.hex(), payout2.address, nonce=1)
    _place(exchange_db, h, _order_body(seller2.address, seller2.key.hex(), side="SELL", amount=5, price="0.001", nonce=2))
    second = _last_json(h)
    assert second["id"] != first["id"]
    _post(
        h,
        exchange_db,
        {
            "event": "order_funded",
            "order_id": second["id"],
            "locked_ticks": int(Decimal("5") * 100_000_000),
            "backing_tx_hash": _txh(101),  # same lock as the first order
            "head": 1000,
        },
    )
    resp = _last_json(h)
    assert h.send_json_response.call_args[1].get("status") == 409
    assert "already funds" in resp.get("error", "")
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (second["id"],))[0] == "unfunded"


def test_order_funded_stores_normalized_backing(exchange_db, settlement_on):
    h = _handler()
    doc = _funded_sell(h, exchange_db)
    stored = _row(exchange_db, "SELECT backing_tx_hash FROM orders WHERE id = ?", (doc["id"],))[0]
    assert stored == _txh(101).lower()


# --- order_backing_expired: supplied head + open order ------------------------


def _open_buy(exchange_db, settlement_on):
    buyer = Account.create()
    _register(exchange_db, buyer.address, buyer.key.hex(), "n-vexp")
    _prepay(exchange_db, buyer.address, "0.05")
    h = _handler()
    _place(exchange_db, h, _order_body(buyer.address, buyer.key.hex(), side="BUY", amount=5, price="0.001", nonce=1))
    return h, _last_json(h)


def test_backing_expired_requires_supplied_head(exchange_db, settlement_on):
    h, doc = _open_buy(exchange_db, settlement_on)
    for bad in (None, "1000", True):
        body = {"event": "order_backing_expired", "order_id": doc["id"]}
        if bad is not None:
            body["head"] = bad
        _post(h, exchange_db, body)
        assert h.send_error.called and h.send_error.call_args[0][0] == 400, bad
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (doc["id"],))[0] == "funded"


def test_backing_expired_refuses_head_before_expiry(exchange_db, settlement_on):
    """expiry_height=2000 on the placed order — a head of 1999 must not
    expire it even though the monitor's own sweep would never send it."""
    h, doc = _open_buy(exchange_db, settlement_on)
    _post(h, exchange_db, {"event": "order_backing_expired", "order_id": doc["id"], "head": 1999})
    _last_json(h)
    assert h.send_json_response.call_args[1].get("status") == 409
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (doc["id"],))[0] == "funded"


def test_backing_expired_refuses_closed_order(exchange_db, settlement_on):
    h, doc = _open_buy(exchange_db, settlement_on)
    _close_order(exchange_db, doc["id"])
    _post(h, exchange_db, {"event": "order_backing_expired", "order_id": doc["id"], "head": 9999})
    assert h.send_json_response.call_args[1].get("status") == 409
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (doc["id"],))[0] == "funded"


def test_backing_expired_at_expiry_height_succeeds(exchange_db, settlement_on):
    h, doc = _open_buy(exchange_db, settlement_on)
    _post(h, exchange_db, {"event": "order_backing_expired", "order_id": doc["id"], "head": 2000})
    resp = _last_json(h)
    assert resp["ok"] and resp["funded_state"] == "backing_expired"
    assert _row(exchange_db, "SELECT funded_state FROM orders WHERE id = ?", (doc["id"],))[0] == "backing_expired"


# --- debit_refund: closed orders only ----------------------------------------


def test_debit_refund_refuses_open_order(exchange_db, settlement_on):
    """The defect: refunding a live order's reservation lets the same
    prepaid balance be re-reserved while committed_eth keeps accruing —
    obligations exceed deposits."""
    h, doc = _open_buy(exchange_db, settlement_on)
    _post(h, exchange_db, {"event": "debit_refund", "order_id": doc["id"]})
    _last_json(h)
    assert h.send_json_response.call_args[1].get("status") == 409
    assert _row(exchange_db, "SELECT state FROM prepaid_debits WHERE order_id = ?", (doc["id"],))[0] == "open"


def test_debit_refund_still_works_on_closed_order(exchange_db, settlement_on):
    h, doc = _open_buy(exchange_db, settlement_on)
    _close_order(exchange_db, doc["id"])
    _post(h, exchange_db, {"event": "debit_refund", "order_id": doc["id"]})
    resp = _last_json(h)
    assert resp["ok"] and resp["refunded_eth"] == "0.005"


# --- trade_state: refunded evidence + sweep map ------------------------------


def test_trade_state_refunded_requires_evidence(exchange_db, settlement_on):
    h, _b, _buyer, _sid, trade_id = _make_filled_buy(exchange_db, settlement_on)
    for state in ("releasing", "released", "refund_pending", "refunding"):
        _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": state})
    # No ait_tx_hash -> refused before any state write.
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "refunded"})
    assert h.send_error.called and h.send_error.call_args[0][0] == 400
    assert _row(exchange_db, "SELECT settlement_state FROM trades WHERE id = ?", (trade_id,))[0] == "refunding"
    # Misshapen hash -> refused too.
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "refunded", "ait_tx_hash": "0xbad"})
    assert h.send_error.called
    # Real evidence -> accepted.
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "refunded", "ait_tx_hash": _txh(77)})
    resp = _last_json(h)
    assert resp["ok"] and resp["settlement_state"] == "refunded"


def test_needs_review_sweep_cannot_jump_to_terminal(exchange_db, settlement_on):
    """#3048: the mirror must replay the sweep lanes — a direct
    needs_review_sweep -> settled/refunded skipped every intermediate
    state (and the refunded recredit's evidence gate)."""
    h, _b, _buyer, _sid, trade_id = _make_filled_buy(exchange_db, settlement_on)
    for state in ("releasing", "released", "needs_review_sweep"):
        _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": state})
    for target in ("settled", "refunded"):
        body = {"event": "trade_state", "trade_id": trade_id, "state": target}
        if target == "refunded":
            body["ait_tx_hash"] = _txh(78)
        _post(h, exchange_db, body)
        resp = _last_json(h)
        assert "cannot move" in resp.get("error", ""), target
    # The legal resume lanes still work.
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "refunding"})
    _post(h, exchange_db, {"event": "trade_state", "trade_id": trade_id, "state": "refunded", "ait_tx_hash": _txh(79)})
    assert _last_json(h)["settlement_state"] == "refunded"


# --- dedicated internal key ---------------------------------------------------


def test_internal_key_narrows_the_credential(exchange_db, settlement_on, monkeypatch):
    """With EXCHANGE_INTERNAL_API_KEY provisioned, the broader
    EXCHANGE_API_KEY must NOT authenticate the custody endpoint."""
    monkeypatch.setenv("EXCHANGE_INTERNAL_API_KEY", "internal-secret")
    h = _handler()
    _post(h, exchange_db, {"event": "debit_refund", "order_id": 1}, key="test-key")
    assert h.send_error.called and h.send_error.call_args[0][0] == 401
    _post(h, exchange_db, {"event": "debit_refund", "order_id": 1}, key="internal-secret")
    # Reaches the handler body (order 1 doesn't exist -> 404 json, not 401).
    assert not h.send_error.called
    assert h.send_json_response.call_args[1].get("status") == 404


def test_internal_key_falls_back_to_shared_key(exchange_db, settlement_on):
    """Unset dedicated key -> the shared key still works (migration path)."""
    h = _handler()
    _post(h, exchange_db, {"event": "debit_refund", "order_id": 1}, key="test-key")
    assert not h.send_error.called
    assert h.send_json_response.call_args[1].get("status") == 404
