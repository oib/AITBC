"""Idempotency-Key handling for the exchange's financial mutations.

POST /api/orders and the market offer endpoints accept an
``Idempotency-Key`` header. The ledger row shares the order's SQLite
transaction, so replays return the recorded response verbatim and a crashed
attempt leaves no residue.
"""

import asyncio
import json
import sqlite3

import pytest
from starlette.requests import Request

from apps.exchange.simple_exchange.main import _dispatch


def _market_module_globals() -> dict:
    """Globals of the market mixin module *this file's _dispatch uses*.

    test_http_contract's server fixture pops and re-imports the whole
    ``apps.exchange.simple_exchange`` package — and that copy's lifespan
    shutdown kills its handler pool — so ``sys.modules`` may hold a
    different copy than the one bound at this module's import. Walk from
    the bound ``_dispatch`` instead of resolving the module by name.
    """
    handler_cls = _dispatch.__globals__["ExchangeAPIHandler"]
    mixin = next(c for c in handler_cls.__mro__ if c.__name__ == "MarketMixin")
    return mixin.handle_market_book_offer.__globals__


@pytest.fixture(autouse=True)
def _legacy_unsigned_placement(monkeypatch):
    """Idempotency-Key semantics here belong to the pre-phase-2 unsigned path.

    ETH-11 phase 2 made signed envelopes the default auth for POST
    /api/orders (the signature itself is the dedupe key there); pin the flag
    off so these tests keep exercising exactly the contract they document.
    """
    monkeypatch.setenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", "0")


def _request(method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None) -> Request:
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": hdrs,
    }
    return Request(scope, receive)


def _post(path: str, body: dict, key: str | None = None):
    headers = {"X-Api-Key": "test-key"}
    if key:
        headers["Idempotency-Key"] = key
    return asyncio.run(_dispatch(_request("POST", path, json.dumps(body).encode(), headers), "POST"))


class TestPlaceOrderIdempotency:
    BODY = {"order_type": "BUY", "amount": "1.5", "price": "2.0", "user_address": "0xabc"}

    def test_replay_returns_same_order(self, exchange_db):
        first = _post("/api/orders", self.BODY, key="k-1")
        assert first.status_code == 200
        order_id = json.loads(first.body)["id"]

        second = _post("/api/orders", self.BODY, key="k-1")
        assert second.status_code == 200
        assert json.loads(second.body)["id"] == order_id

        conn = sqlite3.connect(exchange_db)
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        conn.close()
        assert count == 1

    def test_same_key_different_body_conflicts(self, exchange_db):
        _post("/api/orders", self.BODY, key="k-2")
        conflict = _post("/api/orders", {**self.BODY, "amount": "9"}, key="k-2")
        assert conflict.status_code == 409
        assert "different request" in json.loads(conflict.body)["error"]

    def test_different_keys_create_distinct_orders(self, exchange_db):
        _post("/api/orders", self.BODY, key="k-3")
        _post("/api/orders", self.BODY, key="k-4")
        conn = sqlite3.connect(exchange_db)
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        conn.close()
        assert count == 2

    def test_no_key_still_works(self, exchange_db):
        resp = _post("/api/orders", self.BODY)
        assert resp.status_code == 200


class TestMarketOfferIdempotency:
    @pytest.fixture(autouse=True)
    def _buyer_can_pay(self, monkeypatch):
        """#1827: booking now verifies on-chain balance — this class tests
        idempotent replay, not funds, so stub a deep balance."""
        monkeypatch.setitem(_market_module_globals(), "_buyer_available_units", lambda wallet: 10**18)

    def test_book_offer_replays(self, exchange_db):
        conn = sqlite3.connect(exchange_db)
        conn.execute(
            "CREATE TABLE marketplace_offers (id TEXT PRIMARY KEY, item TEXT, item_type TEXT, price TEXT,"
            " wallet TEXT, status TEXT, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE marketplace_orders (id TEXT PRIMARY KEY, order_type TEXT, item TEXT, price TEXT,"
            " wallet TEXT, status TEXT, offer_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TEXT)"
        )
        conn.execute(
            "INSERT INTO marketplace_offers (id, item, item_type, price, wallet, status) VALUES ('of-1', 'gpu', 'hw', '5', '0xw', 'active')"
        )
        conn.commit()
        conn.close()

        first = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer"}, key="bk-1")
        assert first.status_code == 201
        order_id = json.loads(first.body)["order_id"]

        second = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer"}, key="bk-1")
        assert second.status_code == 201
        assert json.loads(second.body)["order_id"] == order_id


def _get(path: str):
    return asyncio.run(_dispatch(_request("GET", path), "GET"))


class TestMarketplaceExpiry:
    """#1563: marketplace rows carry expires_at; read paths lazily flip stale
    rows to 'expired' and booking an expired offer fails."""

    DDL = [
        "CREATE TABLE marketplace_offers (id TEXT PRIMARY KEY, item TEXT, item_type TEXT, price TEXT,"
        " wallet TEXT, status TEXT, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        " expires_at TEXT)",
        "CREATE TABLE marketplace_orders (id TEXT PRIMARY KEY, order_type TEXT, item TEXT, price TEXT,"
        " wallet TEXT, status TEXT, offer_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        " expires_at TEXT)",
    ]

    def _seed(self, exchange_db, offer_expires="2999-01-01 00:00:00", order_expires="2999-01-01 00:00:00"):
        conn = sqlite3.connect(exchange_db)
        for ddl in self.DDL:
            conn.execute(ddl)
        conn.execute(
            "INSERT INTO marketplace_offers (id, item, item_type, price, wallet, status, expires_at)"
            " VALUES ('of-x', 'gpu', 'hw', '5', '0xw', 'active', ?)",
            (offer_expires,),
        )
        conn.execute(
            "INSERT INTO marketplace_orders (id, order_type, item, price, wallet, status, offer_id, expires_at)"
            " VALUES ('ord-sell', 'SELL', 'gpu', '5', '0xw', 'open', 'of-x', ?)",
            (order_expires,),
        )
        conn.commit()
        conn.close()

    def test_stale_offer_and_sell_order_expire_lazily(self, exchange_db):
        self._seed(exchange_db, offer_expires="2000-01-01 00:00:00", order_expires="2999-01-01 00:00:00")
        resp = _get("/v1/market/offers")
        assert resp.status_code == 200
        offers = json.loads(resp.body)
        assert offers[0]["status"] == "expired"
        assert offers[0]["expires_at"] == "2000-01-01 00:00:00"
        conn = sqlite3.connect(exchange_db)
        offer_status = conn.execute("SELECT status FROM marketplace_offers WHERE id='of-x'").fetchone()[0]
        # The open SELL order follows its expired offer even though its own
        # expires_at is still in the future.
        order_status = conn.execute("SELECT status FROM marketplace_orders WHERE id='ord-sell'").fetchone()[0]
        conn.close()
        assert offer_status == "expired"
        assert order_status == "expired"

    def test_fresh_offer_stays_active(self, exchange_db):
        self._seed(exchange_db)
        resp = _get("/v1/market/offers/of-x")
        assert resp.status_code == 200
        assert json.loads(resp.body)["status"] == "active"

    def test_book_expired_offer_is_rejected(self, exchange_db):
        self._seed(exchange_db, offer_expires="2000-01-01 00:00:00")
        resp = _post("/v1/market/offers/of-x/book", {"wallet": "0xbuyer"})
        assert resp.status_code == 404
