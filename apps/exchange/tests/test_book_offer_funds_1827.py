"""BOOK-OFFER-FUNDS-CHECK-1 (#1827): booking a marketplace offer commits the
buyer's funds — the endpoint must verify the buyer's on-chain available
balance covers the order (plus their other open BUY orders) before
inserting the BUY row, and fail closed when it cannot verify.

Dispatch goes through the real handler; ``_buyer_available_units`` is
patched per test — no real RPC.
"""

import asyncio
import json
import sqlite3

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

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": hdrs,
    }
    return Request(scope, receive)


def _post(path: str, body: dict):
    return asyncio.run(_dispatch(_request("POST", path, json.dumps(body).encode(), {"X-Api-Key": "test-key"}), "POST"))


def _set_balance(monkeypatch, fn):
    """Patch _buyer_available_units on the module copy _dispatch actually uses."""
    monkeypatch.setitem(_market_module_globals(), "_buyer_available_units", fn)


def _seed(exchange_db, offer_price="5"):
    conn = sqlite3.connect(exchange_db)
    for ddl in DDL:
        conn.execute(ddl)
    conn.execute(
        "INSERT INTO marketplace_offers (id, item, item_type, price, wallet, status)"
        " VALUES ('of-1', 'gpu', 'hw', ?, '0xw', 'active')",
        (offer_price,),
    )
    conn.commit()
    conn.close()


def _open_buy(exchange_db, wallet: str, price: str):
    conn = sqlite3.connect(exchange_db)
    conn.execute(
        "INSERT INTO marketplace_orders (id, order_type, item, price, wallet, status) VALUES (?, 'BUY', 'gpu', ?, ?, 'open')",
        (f"ord-{price}-{wallet[-4:]}", price, wallet),
    )
    conn.commit()
    conn.close()


# 1 AIT = 36_000_000 compute-units; offer price 5 AIT = 180_000_000 units.
RICH = 10**15
POOR = 100  # far below one AIT


class TestBookOfferFunds:
    def test_rich_buyer_books(self, exchange_db, monkeypatch):
        _seed(exchange_db)
        _set_balance(monkeypatch, lambda w: RICH)
        resp = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer"})
        assert resp.status_code == 201, resp.body

    def test_insufficient_balance_rejected_402(self, exchange_db, monkeypatch):
        _seed(exchange_db)
        _set_balance(monkeypatch, lambda w: POOR)
        resp = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer"})
        assert resp.status_code == 402
        assert "insufficient" in json.loads(resp.body)["error"]
        conn = sqlite3.connect(exchange_db)
        n = conn.execute("SELECT COUNT(*) FROM marketplace_orders WHERE order_type='BUY'").fetchone()[0]
        conn.close()
        assert n == 0

    def test_unverifiable_balance_fails_closed_503(self, exchange_db, monkeypatch):
        _seed(exchange_db)
        _set_balance(monkeypatch, lambda w: None)
        resp = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer"})
        assert resp.status_code == 503
        conn = sqlite3.connect(exchange_db)
        n = conn.execute("SELECT COUNT(*) FROM marketplace_orders WHERE order_type='BUY'").fetchone()[0]
        conn.close()
        assert n == 0

    def test_missing_wallet_rejected_400(self, exchange_db, monkeypatch):
        _seed(exchange_db)
        called = []
        _set_balance(monkeypatch, lambda w: called.append(w) or RICH)
        resp = _post("/v1/market/offers/of-1/book", {})
        assert resp.status_code == 400
        assert "wallet" in json.loads(resp.body)["error"]

    def test_open_orders_count_against_balance(self, exchange_db, monkeypatch):
        """Buyer has 200M units (~5.5 AIT): one open 4-AIT BUY leaves 1.5 AIT;
        booking a 5-AIT offer must fail even though raw balance > price."""
        _seed(exchange_db)
        _open_buy(exchange_db, "0xbuyer", "4")
        _set_balance(monkeypatch, lambda w: 200_000_000)
        resp = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer"})
        assert resp.status_code == 402

    def test_other_wallets_orders_dont_count(self, exchange_db, monkeypatch):
        _seed(exchange_db)
        _open_buy(exchange_db, "0xsomeone-else", "100")
        _set_balance(monkeypatch, lambda w: 200_000_000)
        resp = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer"})
        assert resp.status_code == 201, resp.body

    def test_buyer_supplied_price_checked(self, exchange_db, monkeypatch):
        """A buyer price above the offer price is what gets checked."""
        _seed(exchange_db, offer_price="1")
        _set_balance(monkeypatch, lambda w: 100_000_000)  # ~2.7 AIT — covers 1 AIT offer, not 5 AIT bid
        resp = _post("/v1/market/offers/of-1/book", {"wallet": "0xbuyer", "price": "5"})
        assert resp.status_code == 402
