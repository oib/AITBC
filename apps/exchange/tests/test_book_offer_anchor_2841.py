"""#2841: book-offer offer lookup must be deterministic (item names are not
unique) and an explicit buyer price may not undercut the offer it books."""

import asyncio
import json
import sqlite3

from starlette.requests import Request

from apps.exchange.simple_exchange.main import _dispatch


def _market_module_globals() -> dict:
    handler_cls = _dispatch.__globals__["ExchangeAPIHandler"]
    mixin = next(c for c in handler_cls.__mro__ if c.__name__ == "MarketMixin")
    return mixin.handle_market_book_offer.__globals__


DDL = [
    "CREATE TABLE marketplace_offers (id TEXT PRIMARY KEY, item TEXT, item_type TEXT, price TEXT,"
    " wallet TEXT, status TEXT, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TEXT)",
    "CREATE TABLE marketplace_orders (id TEXT PRIMARY KEY, order_type TEXT, item TEXT, price TEXT,"
    " wallet TEXT, status TEXT, offer_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TEXT)",
]


def _request(method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None) -> Request:
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": b"", "headers": hdrs}
    return Request(scope, receive)


def _post(path: str, body: dict):
    return asyncio.run(_dispatch(_request("POST", path, json.dumps(body).encode(), {"X-Api-Key": "test-key"}), "POST"))


def _seed(exchange_db, offers):
    conn = sqlite3.connect(exchange_db)
    for ddl in DDL:
        conn.execute(ddl)
    for offer_id, item, price, created_at in offers:
        conn.execute(
            "INSERT INTO marketplace_offers (id, item, item_type, price, wallet, status, created_at)"
            " VALUES (?, ?, 'hw', ?, '0xs', 'active', ?)",
            (offer_id, item, price, created_at),
        )
    conn.commit()
    conn.close()


def _order_row(exchange_db):
    conn = sqlite3.connect(exchange_db)
    row = conn.execute("SELECT offer_id, price FROM marketplace_orders WHERE order_type='BUY'").fetchone()
    conn.close()
    return row


RICH = 10**15


class TestDeterministicOfferLookup:
    def test_exact_id_wins_over_item_match(self, exchange_db, monkeypatch):
        """offer_id='gpu' is both an item name and another offer's id — the
        exact id match must win, not an arbitrary row."""
        # item matches inserted FIRST so an unordered scan picks them before
        # the exact-id row — only ORDER BY (id = ?) DESC makes the id win
        _seed(
            exchange_db,
            [
                ("of-a", "gpu", "3", "2026-01-01 00:00:02"),
                ("of-b", "gpu", "9", "2026-01-01 00:00:03"),
                ("gpu", "widget", "7", "2026-01-01 00:00:01"),  # id == the lookup key
            ],
        )
        g = _market_module_globals()
        monkeypatch.setitem(g, "_buyer_available_units", lambda w: RICH)
        resp = _post("/v1/market/offers/gpu/book", {"wallet": "0xbuyer"})
        assert resp.status_code == 201, resp.body
        offer_id, price = _order_row(exchange_db)
        assert offer_id == "gpu"
        assert price == "7"

    def test_item_lookup_is_deterministic_newest_first(self, exchange_db, monkeypatch):
        _seed(
            exchange_db,
            [
                ("of-a", "gpu", "3", "2026-01-01 00:00:01"),
                ("of-b", "gpu", "9", "2026-01-01 00:00:02"),
            ],
        )
        g = _market_module_globals()
        monkeypatch.setitem(g, "_buyer_available_units", lambda w: RICH)
        for _ in range(2):
            resp = _post("/v1/market/offers/gpu/book", {"wallet": "0xbuyer"})
            assert resp.status_code == 201, resp.body
        conn = sqlite3.connect(exchange_db)
        rows = conn.execute("SELECT offer_id FROM marketplace_orders").fetchall()
        conn.close()
        # both bookings picked the same (newest) offer — deterministic
        assert [r[0] for r in rows] == ["of-b", "of-b"]


class TestBuyerPriceAnchor:
    def test_price_below_offer_rejected(self, exchange_db, monkeypatch):
        _seed(exchange_db, [("of-1", "gpu", "100", "2026-01-01 00:00:01")])
        g = _market_module_globals()
        monkeypatch.setitem(g, "_buyer_available_units", lambda w: RICH)
        resp = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer", "price": "0.00000001"})
        assert resp.status_code == 400
        conn = sqlite3.connect(exchange_db)
        n = conn.execute("SELECT COUNT(*) FROM marketplace_orders").fetchone()[0]
        conn.close()
        assert n == 0

    def test_price_at_or_above_offer_books(self, exchange_db, monkeypatch):
        _seed(exchange_db, [("of-1", "gpu", "5", "2026-01-01 00:00:01")])
        g = _market_module_globals()
        monkeypatch.setitem(g, "_buyer_available_units", lambda w: RICH)
        resp = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer", "price": "5"})
        assert resp.status_code == 201, resp.body
        assert _order_row(exchange_db)[1] == "5"
