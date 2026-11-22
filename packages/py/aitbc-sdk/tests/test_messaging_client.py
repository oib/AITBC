"""MSG-15 Phase A: SDK MessagingClient — post/read/subscribe over fake RPC.

No live host, no real keys: `submit` is a stub capturing envelopes, and the
HTTP layer is a fake. Assertions check the signing boundary (the helper never
picks a wallet, never sees keys) and the subscribe cursor semantics.
"""

from __future__ import annotations

from typing import Any

import pytest

from aitbc_sdk.messaging import MessagingClient, MessagingNotFoundError
from aitbc_sdk.errors import AITBCConnectionError, AITBCError
import aitbc.messaging_client as mc

ALICE = "0x" + "11" * 20
BOB = "0x" + "22" * 20


class FakeHTTP:
    """AITBCHTTPClient stand-in: maps (path, params) → canned response."""

    def __init__(self, routes: dict[tuple, Any] | None = None, base_url: str = "http://rpc"):
        self.routes = routes or {}
        self.base_url = base_url
        self.calls: list[tuple[str, Any]] = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        key = (path, tuple(sorted((params or {}).items())))
        if key in self.routes:
            v = self.routes[key]
            if isinstance(v, Exception):
                raise v
            return v
        if (path, None) in self.routes:
            v = self.routes[(path, None)]
            if isinstance(v, Exception):
                raise v
            return v
        for (p, _), v in self.routes.items():
            if p == path:
                if isinstance(v, Exception):
                    raise v
                return v
        raise AITBCConnectionError(f"no canned route for {path}")


def _msg(height: int, n: int, body: str = "x") -> dict[str, Any]:
    return {"tx_hash": f"{n:064x}", "block_height": height, "body": body, "kind": "post"}


# ------------------------------------------------------------------ post


class TestPost:
    def test_refuses_without_wallet(self):
        c = MessagingClient(FakeHTTP())
        with pytest.raises(AITBCError, match="wallet"):
            c.post("dev", "hi", wallet="", submit=lambda *a: "tx")

    def test_refuses_without_submit(self):
        c = MessagingClient(FakeHTTP())
        with pytest.raises(AITBCError, match="submit"):
            c.post("dev", "hi", wallet="w", agent_address=ALICE, submit=None)  # type: ignore[arg-type]

    def test_builds_and_submits(self):
        captured = {}

        def submit(wallet, envelope, fee):
            captured.update(wallet=wallet, envelope=envelope, fee=fee)
            return "ab" * 32

        c = MessagingClient(FakeHTTP())
        out = c.post("Dev Topic", "hello", wallet="my-wallet", agent_address=ALICE, submit=submit)
        assert out["tx_hash"] == "ab" * 32
        assert captured["wallet"] == "my-wallet"
        env = captured["envelope"]
        # "Dev Topic" normalizes to its canonical slug.
        assert env["kind"] == "post" and env["topic"] == "dev-topic" and env["body"] == "hello"
        assert env["agent_address"] == ALICE

    def test_reply_parent(self):
        captured = {}
        c = MessagingClient(FakeHTTP())

        def submit(w, e, f):
            captured["env"] = e
            return "00" * 32

        c.post("dev", "re", wallet="w", agent_address=ALICE, parent="cd" * 32, submit=submit)
        assert captured["env"]["kind"] == "reply" and captured["env"]["parent"] == "cd" * 32

    def test_invalid_envelope_fails_before_submit(self):
        called = []
        c = MessagingClient(FakeHTTP())
        with pytest.raises(ValueError):
            c.post("dev", "x" * 5000, wallet="w", agent_address=ALICE, submit=lambda *a: called.append(a))
        assert called == []


# ------------------------------------------------------------------ reads


class TestReads:
    def test_read_params(self):
        http = FakeHTTP({("/rpc/messaging/messages", None): {"messages": []}})
        c = MessagingClient(http)
        c.read("dev", cursor="9:ab", limit=10)
        assert http.calls[0][1] == {"limit": 10, "topic": "dev", "cursor": "9:ab"}

    def test_show_404_distinct_from_connection(self):
        http = FakeHTTP({("/rpc/messaging/messages/0x" + "ab" * 32, None): Exception("404 Not Found")})
        c = MessagingClient(http)
        with pytest.raises(MessagingNotFoundError):
            c.show("ab" * 32)

        http2 = FakeHTTP()
        http2.routes[("/rpc/messaging/messages/0x" + "cd" * 32, None)] = AITBCConnectionError("refused")
        c2 = MessagingClient(http2)
        with pytest.raises((AITBCConnectionError, AITBCError)) as ei:
            c2.show("cd" * 32)
        assert not isinstance(ei.value, MessagingNotFoundError)


# ------------------------------------------------------------------ subscribe


class TestSubscribe:
    def _feed(self, pages: list[dict[str, Any]], monkeypatch, cursor_calls=None):
        it = iter(pages)

        def fake_fetch(rpc, *, topic=None, cursor=None, limit=50, timeout=10.0):
            try:
                return next(it)
            except StopIteration:
                return {"messages": []}

        monkeypatch.setattr(mc, "fetch_messages", fake_fetch)
        return fake_fetch

    def test_yields_only_newer_rows_oldest_first(self, monkeypatch):
        # Page returns newest-first; rows newer than the cursor yield oldest-first.
        page = {"messages": [_msg(10, 3, "c"), _msg(10, 2, "b"), _msg(9, 1, "a")]}
        self._feed([page], monkeypatch)
        c = MessagingClient(FakeHTTP())
        gen = c.subscribe("dev", from_cursor="9:" + "01" * 32, interval=0, max_polls=1)
        # Cursor (9, "0101…"): rows at height 10 are newer; the (9, "000…01") row
        # sorts below "0101…" and is not emitted.
        got = list(gen)
        assert [m["body"] for m in got] == ["b", "c"]

    def test_no_cursor_starts_at_head_no_backlog(self, monkeypatch):
        self._feed([{"messages": [_msg(10, 2)]}], monkeypatch)
        c = MessagingClient(FakeHTTP())
        assert list(c.subscribe("dev", interval=0, max_polls=1)) == []

    def test_second_poll_emits_arrivals(self, monkeypatch):
        pages = [
            {"messages": [_msg(10, 2, "old")]},
            {"messages": [_msg(11, 9, "new"), _msg(10, 2, "old")]},
        ]
        self._feed(pages, monkeypatch)
        c = MessagingClient(FakeHTTP())
        got = list(c.subscribe("dev", interval=0, max_polls=2))
        assert [m["body"] for m in got] == ["new"]

    def test_transport_failure_is_skipped(self, monkeypatch):
        calls = iter([mc.UNREACHABLE, {"messages": [_msg(5, 1, "x")]}])
        monkeypatch.setattr(mc, "fetch_messages", lambda *a, **k: next(calls))
        c = MessagingClient(FakeHTTP())
        got = list(c.subscribe("dev", from_cursor="1:00", interval=0, max_polls=2))
        assert [m["body"] for m in got] == ["x"]

    def test_bad_cursor_rejected(self):
        c = MessagingClient(FakeHTTP())
        with pytest.raises(AITBCError):
            list(c.subscribe("dev", from_cursor="not-a-cursor", interval=0, max_polls=1))


# ------------------------------------------------- AUDIT-MESSAGING-* fixes


def _msg0x(height: int, n: int, body: str = "x") -> dict[str, Any]:
    """A row as the live index emits it: ``0x``-prefixed tx_hash."""
    return {"tx_hash": "0x" + f"{n:064x}", "block_height": height, "body": body, "kind": "post"}


class TestSubscribeAuditFixes:
    def test_first_message_on_previously_empty_topic_is_delivered(self, monkeypatch):
        """#2573: an empty first poll is the baseline — the next post is new."""
        pages = iter(
            [
                {"messages": []},
                {"messages": [_msg(11, 7, "first-ever")]},
            ]
        )
        monkeypatch.setattr(mc, "fetch_messages", lambda *a, **k: next(pages, {"messages": []}))
        c = MessagingClient(FakeHTTP())
        got = list(c.subscribe("dev", interval=0, max_polls=2))
        assert [m["body"] for m in got] == ["first-ever"]

    def test_same_block_resume_with_0x_row_hashes(self, monkeypatch):
        """#2574: cursor hash is bare, row hashes are 0x-prefixed — same-block
        rows newer than the cursor still deliver and the cursor row does not."""
        cursor_row = _msg0x(10, 5, "cursor")
        newer = _msg0x(10, 9, "newer-same-block")
        page = {"messages": [newer, _msg0x(10, 7, "also-newer"), cursor_row, _msg0x(10, 3, "older")]}
        monkeypatch.setattr(mc, "fetch_messages", lambda *a, **k: page)
        c = MessagingClient(FakeHTTP())
        got = list(c.subscribe("dev", from_cursor="10:" + f"{5:064x}", interval=0, max_polls=1))
        assert [m["body"] for m in got] == ["also-newer", "newer-same-block"]

    def test_gap_pages_back_until_cursor_reached(self, monkeypatch):
        """#2575: a cursor older than one page must not be skipped — the
        kernel pages back through next_cursor until it reaches the cursor."""
        # Head page: newest 2 rows; next_cursor leads to the page holding the
        # cursor row and the rows between it and the head page. The resume
        # cursor names the (20, hash20) row itself.
        head = {
            "messages": [_msg(30, 30, "h30"), _msg(29, 29, "h29")],
            "next_cursor": "28:" + f"{28:064x}",
        }
        middle = {
            "messages": [_msg(28, 28, "m28"), _msg(27, 27, "m27")],
            "next_cursor": "26:" + f"{26:064x}",
        }
        tail = {
            "messages": [_msg(26, 26, "t26"), _msg(20, 20, "cursor-row"), _msg(19, 19, "older")],
            "next_cursor": None,
        }
        calls = []

        def fake_fetch(rpc, *, topic=None, cursor=None, limit=50, timeout=10.0):
            calls.append(cursor)
            if cursor is None:
                return head
            if cursor.startswith("28:"):
                return middle
            return tail

        monkeypatch.setattr(mc, "fetch_messages", fake_fetch)
        c = MessagingClient(FakeHTTP())
        got = list(c.subscribe("dev", from_cursor="20:" + f"{20:064x}", interval=0, max_polls=1))
        # Rows newer than (20, hash01): t26? no — (26,..)>(20,..) yes, m27,
        # m28, h29, h30 all newer; the cursor row and 'older' are not.
        assert [m["body"] for m in got] == ["t26", "m27", "m28", "h29", "h30"]
        assert calls[0] is None and calls[1].startswith("28:") and calls[2].startswith("26:")

    def test_gap_bound_raises_instead_of_skipping(self, monkeypatch):
        """#2575: when the cursor is beyond the back-page bound the subscribe
        reports the gap (SubscribeGapError) rather than jumping past rows."""
        page = {"messages": [_msg(99, 99)], "next_cursor": "98:" + f"{98:064x}"}
        monkeypatch.setattr(mc, "fetch_messages", lambda *a, **k: page)
        c = MessagingClient(FakeHTTP())
        with pytest.raises(mc.SubscribeGapError):
            list(c.subscribe("dev", from_cursor="1:" + f"{1:064x}", interval=0, max_polls=1))
