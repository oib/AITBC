"""HTTP contract for ETH-11 phase 2 — signed orders, registration, cancel.

Runs the real ``ExchangeAPIHandler`` on a real socket (same pattern as
test_http_contract.py) with ``EXCHANGE_REQUIRE_SIGNED_ORDERS`` at its
default-on value, plus flag-off coverage proving the revertible surface.

Keys are throwaway — generated in-process by ``Account.create()``; nothing
reads a real wallet, password, keystore, or RPC endpoint.
"""

import json
import os
import sqlite3
import sys
import threading
import urllib.request
from decimal import Decimal
from pathlib import Path

import pytest
from eth_account import Account

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

API_KEY = "signed-contract-test-key"
CHAIN_ID = "ait-test-contract"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Phase-2 server: signed orders at the default (on), temp DB, dead RPC."""
    db_dir = tmp_path_factory.mktemp("exchange-db-p2")
    os.environ["EXCHANGE_DATABASE_URL"] = f"sqlite:///{db_dir}/exchange.db"
    os.environ["EXCHANGE_API_KEY"] = API_KEY
    os.environ["BLOCKCHAIN_RPC_BASE_URL"] = "http://127.0.0.1:1"
    os.environ.pop("EXCHANGE_REQUIRE_SIGNED_ORDERS", None)  # default = on
    os.environ["EXCHANGE_CHAIN_ID"] = CHAIN_ID
    # Unlimited price band: the oracle is unreachable on this host; band-edge
    # coverage lives in the handler-level tests with a stubbed feed.
    os.environ["EXCHANGE_PRICE_BAND_PCT"] = "999999"

    pkg = "apps.exchange.simple_exchange"
    for name in [m for m in sys.modules if m == pkg or m.startswith(pkg + ".")]:
        sys.modules.pop(name)

    from apps.exchange.simple_exchange.db import init_db
    from apps.exchange.simple_exchange.main import app

    init_db()

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        thread.join(0.05)
    else:
        raise RuntimeError("uvicorn did not start")
    port = srv.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", str(Path(db_dir) / "exchange.db")
    finally:
        srv.should_exit = True
        thread.join(timeout=5)


def _req(server, method, path, body=None, api_key=None):
    url = server + path
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if api_key:
        request.add_header("X-Api-Key", api_key)
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return e.code, {"raw": raw}


def _key():
    acct = Account.create()
    return acct.address, acct.key.hex()


def _sign(envelope, privkey):
    from aitbc.crypto.crypto import sign_transaction_data

    return sign_transaction_data(envelope, privkey)


def _post_signed(server, path, envelope, privkey, address):
    body = {"envelope": envelope, "signature": _sign(envelope, privkey), "user_address": address}
    return _req(server, "POST", path, body=body)


def _seed(db_path, address, label):
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO node_registry (address, label, status) VALUES (?, ?, 'seeded')", (address, label))
    conn.commit()
    conn.close()


@pytest.fixture
def live_head(monkeypatch):
    """Pin the chain head at 1000 — the exchange's own RPC is dead here, and a
    resolvable head is what expiry validation needs (503 without it, which is
    the fail-closed behavior the dead-RPC tests assert elsewhere)."""
    from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

    monkeypatch.setattr(ExchangeMixin, "_chain_head_height", lambda self: 1000)


def _order_envelope(side="SELL", amount=10, price="0.000083", expiry=999999, nonce=0):
    return {
        "side": side,
        "pair": "AIT/ETH",
        "amount_ticks": int(Decimal(amount) * 100_000_000),
        "price_ticks": int(Decimal(price) * 100_000_000),
        "expiry_height": expiry,
        "account_nonce": nonce,
        "chain_id": CHAIN_ID,
    }


# --- auth boundary --------------------------------------------------------


class TestSignedAuthBoundary:
    def test_empty_body_is_unauthorized(self, server):
        status, _ = _req(server[0], "POST", "/api/orders", body={})
        assert status == 401

    def test_unsigned_order_body_is_unauthorized(self, server):
        body = {"order_type": "BUY", "amount": "1", "price": "1", "user_address": "0xabc"}
        status, _ = _req(server[0], "POST", "/api/orders", body=body)
        assert status == 401

    def test_garbage_signature_is_unauthorized(self, server):
        status, _ = _req(
            server[0],
            "POST",
            "/api/orders",
            body={
                "envelope": _order_envelope(),
                "signature": "0x" + "00" * 65,
                "user_address": "0x" + "ab" * 20,
            },
        )
        assert status == 401

    def test_wrong_field_set_400(self, server):
        addr, key = _key()
        envelope = _order_envelope()
        del envelope["expiry_height"]
        status, _ = _post_signed(server[0], "/api/orders", envelope, key, addr)
        assert status == 400

    def test_wrong_chain_id_400(self, server):
        addr, key = _key()
        envelope = _order_envelope()
        envelope["chain_id"] = "other-chain"
        status, _ = _post_signed(server[0], "/api/orders", envelope, key, addr)
        assert status == 400

    def test_tampered_field_401(self, server):
        addr, key = _key()
        envelope = _order_envelope()
        signature = _sign(envelope, key)
        envelope["amount_ticks"] = 999  # sign A, submit B
        status, _ = _req(
            server[0],
            "POST",
            "/api/orders",
            body={"envelope": envelope, "signature": signature, "user_address": addr},
        )
        assert status == 401

    def test_wrong_signer_401(self, server):
        addr, key = _key()
        _other_addr, other_key = _key()
        status, _ = _post_signed(server[0], "/api/orders", _order_envelope(), other_key, addr)
        assert status == 401


# --- registration ---------------------------------------------------------


class TestRegistration:
    def test_unseeded_address_rejected(self, server):
        addr, key = _key()
        envelope = {
            "action": "exchange_register",
            "address": addr,
            "label": "ghost",
            "account_nonce": 0,
            "chain_id": CHAIN_ID,
        }
        status, body = _post_signed(server[0], "/api/exchange/nodes/register", envelope, key, addr)
        assert status == 403

    def test_unregistered_node_cannot_place(self, server, live_head):
        addr, key = _key()
        _seed(server[1], addr, "seeded-not-yet-claimed")
        status, body = _post_signed(server[0], "/api/orders", _order_envelope(nonce=0), key, addr)
        assert status == 403
        assert body.get("error") == "Node not registered"

    def test_label_mismatch_rejected(self, server):
        addr, key = _key()
        _seed(server[1], addr, "real-label")
        envelope = {
            "action": "exchange_register",
            "address": addr,
            "label": "spoofed-label",
            "account_nonce": 0,
            "chain_id": CHAIN_ID,
        }
        status, _ = _post_signed(server[0], "/api/exchange/nodes/register", envelope, key, addr)
        assert status == 400


# --- lifecycle ------------------------------------------------------------


class TestSignedLifecycle:
    def test_register_place_replay_my_orders_cancel(self, server, live_head):
        addr, key = _key()
        _seed(server[1], addr, "node-lifecycle")

        # register
        reg_env = {
            "action": "exchange_register",
            "address": addr,
            "label": "node-lifecycle",
            "account_nonce": 0,
            "chain_id": CHAIN_ID,
        }
        status, body = _post_signed(server[0], "/api/exchange/nodes/register", reg_env, key, addr)
        assert status == 200, body
        assert body["status"] == "registered"
        assert body["label"] == "node-lifecycle"

        # place (nonce advanced to 1 by the registration)
        order_env = _order_envelope(nonce=1)
        status, body = _post_signed(server[0], "/api/orders", order_env, key, addr)
        assert status == 200, body
        order_id = body["id"]
        assert body["status"] == "open"
        assert body.get("funded_state") == "unfunded"

        # byte-identical replay → recorded order, no new row
        status, body2 = _post_signed(server[0], "/api/orders", order_env, key, addr)
        assert status == 200
        assert body2["id"] == order_id

        # a DIFFERENT envelope on the consumed nonce → 409
        status, _ = _post_signed(server[0], "/api/orders", _order_envelope(amount=11, nonce=1), key, addr)
        assert status == 409

        # my-orders reflects the row + the advanced nonce
        status, doc = _req(server[0], "GET", f"/api/exchange/my-orders?addr={addr}")
        assert status == 200
        assert doc["registered"] is True
        assert doc["label"] == "node-lifecycle"
        assert doc["next_nonce"] == 2
        assert [o["id"] for o in doc["orders"]] == [order_id]

        # nodes board lists the label
        status, nodes = _req(server[0], "GET", "/api/exchange/nodes")
        assert status == 200
        labels = nodes if isinstance(nodes, list) else nodes.get("nodes", [])
        assert any(n.get("label") == "node-lifecycle" for n in labels)

        # cancel (nonce 2) — signed path, not the legacy DELETE
        cancel_env = {
            "action": "exchange_cancel",
            "order_id": order_id,
            "expiry_height": 999999,
            "account_nonce": 2,
            "chain_id": CHAIN_ID,
        }
        status, body = _post_signed(server[0], f"/api/orders/{order_id}/cancel", cancel_env, key, addr)
        assert status == 200, body
        assert body["status"] == "cancelled"

        # cancelling again → deterministic 409 (not open any more)
        status, _ = _post_signed(server[0], f"/api/orders/{order_id}/cancel", cancel_env, key, addr)
        assert status in (409, 400)  # stale nonce or terminal-state conflict — never 200

    def test_expired_envelope_rejected(self, server, live_head):
        addr, key = _key()
        _seed(server[1], addr, "node-expiry")
        reg_env = {
            "action": "exchange_register",
            "address": addr,
            "label": "node-expiry",
            "account_nonce": 0,
            "chain_id": CHAIN_ID,
        }
        status, _ = _post_signed(server[0], "/api/exchange/nodes/register", reg_env, key, addr)
        assert status == 200
        # expiry_height in the past relative to head
        status, _ = _post_signed(server[0], "/api/orders", _order_envelope(expiry=0, nonce=1), key, addr)
        assert status in (400, 409, 410)


# --- flag-off rollback ----------------------------------------------------


class TestFlagOff:
    def test_signed_routes_404_when_disabled(self, server, monkeypatch):
        monkeypatch.setenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", "0")
        for method, path in (
            ("GET", "/api/exchange/nodes"),
            ("GET", "/api/exchange/my-orders?addr=0x" + "ab" * 20),
            ("POST", "/api/exchange/nodes/register"),
            ("POST", "/api/orders/1/cancel"),
        ):
            status, _ = _req(server[0], method, path, body={} if method == "POST" else None)
            assert status == 404, f"{method} {path} answered {status} with the flag off"

    def test_unsigned_placement_restored_when_disabled(self, server, monkeypatch):
        monkeypatch.setenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", "0")
        body = {"order_type": "BUY", "amount": "1", "price": "1", "user_address": "0xlegacy"}
        status, doc = _req(server[0], "POST", "/api/orders", body=body, api_key=API_KEY)
        assert status == 200, doc
        assert doc["status"] == "open"
        # legacy rows carry no phase-2 envelope data
        conn = sqlite3.connect(server[1])
        row = conn.execute("SELECT signature, envelope_hash, funded_state FROM orders WHERE id = ?", (doc["id"],)).fetchone()
        conn.close()
        assert row[0] is None and row[1] is None and row[2] == "unfunded"
