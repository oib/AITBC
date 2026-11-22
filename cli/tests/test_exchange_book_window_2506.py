"""#2506: orderbook/rates page the EXCHANGE stream instead of a recency window.

The old code fetched the newest ``2*limit`` ``status=open`` rows plus a
second newest-N ``status=cancelled`` merge — cancelled orders ate window
slots and the best price could sit outside it. The fix scans the stream
unfiltered with ``before_id`` paging until each side has ``limit`` live
orders (or history/cap ends), folding cancels via ``_apply_cancels``.
"""

import copy
from typing import cast

import aitbc_cli.commands.exchange_island as mod
from aitbc_cli.commands.exchange_island import (
    _live_book_orders,
    _orderbook_transactions,
)
from aitbc_cli.utils.http_client import AITBCHTTPClient


def _order(oid, side, price, tid, pair="AIT/ETH", status="open"):
    return {
        "transaction_id": tid,
        "sender": "0xw",
        "pair": pair,
        "side": side,
        "order_id": oid,
        "status": status,
        "min_price": price if side == "sell" else None,
        "max_price": price if side == "buy" else None,
        "amount": 1.0,
        "user_id": "0xw",
    }


def _cancel(oid, tid):
    return {
        "transaction_id": tid,
        "sender": "0xw",
        "action": "cancel",
        "order_id": oid,
        "status": "cancelled",
        "user_id": "0xw",
    }


class _StreamClient:
    """Emulates GET /transactions: newest-first, honours limit + before_id.

    No status/pair filtering — the real RPC applies payload filters, but
    the new scan deliberately sends none (cancels carry neither field).
    """

    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: r["transaction_id"], reverse=True)
        self.calls = []

    def get_json(self, path, params=None, **kwargs):
        params = params or {}
        self.calls.append(dict(params))
        limit = int(params.get("limit") or 100)
        before = params.get("before_id")
        out = [copy.deepcopy(r) for r in self.rows if before is None or r["transaction_id"] < before]
        return out[:limit]


def _client(rows) -> AITBCHTTPClient:
    return cast(AITBCHTTPClient, _StreamClient(rows))


def _book_with_cancels():
    """Auditor's repro shape: 50 open sells, newest 30 cancelled."""
    rows = []
    tid = 1
    # o01..o50 oldest->newest; o01 has the best (lowest) ask.
    for i in range(1, 51):
        rows.append(_order(f"o{i:02d}", "sell", 0.010 + i * 0.001, tid))
        tid += 1
    # 30 cancels for o21..o50 (newest rows).
    for i in range(21, 51):
        rows.append(_cancel(f"o{i:02d}", tid))
        tid += 1
    return rows


def test_orderbook_finds_live_orders_and_best_ask_beyond_old_window():
    """50 open / 30 cancelled: the book must show the 20 live orders AND
    the best ask o01 — the old 2x-limit window dropped both."""
    client = _StreamClient(_book_with_cancels())
    live, truncated = _live_book_orders(
        cast(AITBCHTTPClient, client), "island", lambda live: sum(1 for p in live if p.get("side") == "sell") >= 20
    )
    assert not truncated
    sells = [p for p in live if p.get("side") == "sell"]
    assert len(sells) == 20
    # live is stream-ordered (newest first); the best ask is the min price —
    # o01 @ 0.011 survives the scan even though it is the oldest row.
    best = min(sells, key=lambda p: float(p["min_price"]))
    assert best["order_id"] == "o01"
    assert {p["order_id"] for p in sells} == {f"o{i:02d}" for i in range(1, 21)}


def test_orderbook_transactions_returns_pair_live_orders(monkeypatch):
    rows = _book_with_cancels() + [_order("b1", "buy", 0.005, 999, pair="AIT/ETH")]
    client = _StreamClient(rows)
    monkeypatch.setattr(mod, "AITBCHTTPClient", lambda *a, **k: client)
    txs, simulated = _orderbook_transactions("http://x", "island", "AIT/ETH", 20)
    assert not simulated
    oids = {(t.get("payload") or t).get("order_id") for t in txs}
    assert "o01" in oids and "o20" in oids
    assert "o21" not in oids  # cancelled orders stay out
    assert "b1" in oids


def test_paging_walks_before_id_until_done(monkeypatch):
    rows = [_order(f"x{i}", "sell", 0.01 + i * 0.001, i) for i in range(1, 30)]
    client = _StreamClient(rows)
    monkeypatch.setattr(mod, "_BOOK_PAGE_SIZE", 10)
    live, truncated = _live_book_orders(cast(AITBCHTTPClient, client), "island", lambda live: len(live) >= 25)
    assert len(live) == 29
    assert not truncated
    befores = [c["before_id"] for c in client.calls if "before_id" in c]
    assert befores == sorted(befores, reverse=True)  # strictly descending cursor


def test_truncation_reported_at_page_cap(monkeypatch):
    rows = [_order(f"y{i}", "sell", 0.01, i) for i in range(1, 60)]
    client = _StreamClient(rows)
    monkeypatch.setattr(mod, "_BOOK_MAX_PAGES", 2)
    monkeypatch.setattr(mod, "_BOOK_PAGE_SIZE", 10)
    live, truncated = _live_book_orders(cast(AITBCHTTPClient, client), "island", lambda live: False)
    assert truncated is True
    assert len(client.calls) == 2


def test_exhausted_history_is_not_truncated():
    rows = [_order("z1", "sell", 0.01, 1)]
    live, truncated = _live_book_orders(_client(rows), "island", lambda live: False)
    assert live and not truncated
