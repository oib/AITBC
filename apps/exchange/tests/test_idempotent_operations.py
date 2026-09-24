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


@pytest.fixture
def exchange_db(tmp_path, monkeypatch):
    """Point the exchange handlers + operation ledger at a temp database."""
    db_path = str(tmp_path / "exchange.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),
            amount TEXT NOT NULL,
            price TEXT NOT NULL,
            total TEXT NOT NULL,
            filled TEXT DEFAULT '0',
            remaining TEXT NOT NULL,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_address TEXT,
            tx_hash TEXT,
            amount_ticks INTEGER,
            price_ticks INTEGER,
            filled_ticks INTEGER DEFAULT 0,
            remaining_ticks INTEGER
        );
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount TEXT NOT NULL,
            price TEXT NOT NULL,
            total TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("EXCHANGE_API_KEY", "test-key")
    # get_db_path() resolves EXCHANGE_DATABASE_URL at call time, so env works
    # even where a previous suite popped and re-imported the handler modules
    # (test_http_contract does exactly that — setattr would patch a stale copy).
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{db_path}")
    # The ledger singleton caches per path — drop any stale entry.
    from apps.exchange.simple_exchange.handlers import base

    base._operation_ledgers.pop(db_path, None)
    return db_path


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
    def test_book_offer_replays(self, exchange_db):
        conn = sqlite3.connect(exchange_db)
        conn.execute(
            "CREATE TABLE marketplace_offers (id TEXT PRIMARY KEY, item TEXT, item_type TEXT, price TEXT,"
            " wallet TEXT, status TEXT, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE marketplace_orders (id TEXT PRIMARY KEY, order_type TEXT, item TEXT, price TEXT,"
            " wallet TEXT, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
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
