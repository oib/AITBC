"""WEB-FIX-1 W5 — 375px layout guard, in two layers.

``TestLayoutHeuristics`` runs everywhere, offline and fast — a *static* CSS/
markup check: every ``<table>`` must sit inside an overflow wrapper, every
flex row that holds form controls must wrap, phone-breakpoint form controls
must be >= 16px, and the two W1/W2 fix mechanisms stay pinned. **It cannot
measure ``documentElement.scrollWidth``** — that needs a layout engine.

``TestLayout375Browser`` is the real assertion: every page at a 375px
viewport must satisfy ``scrollWidth <= innerWidth`` with API calls stubbed
to fixtures, plus a separate 44px tap-target check. It detects a Chromium
binary by environment (``AITBC_WEBSITE_BROWSER`` or ``chromium``/
``chromium-browser``/``google-chrome`` on PATH) plus the ``websockets``
package, and **skips cleanly with "no browser" otherwise** — so it is never
enforced in CI until a browser host exists. The same assertions can be run
by hand against any live page via ``scripts/ops/website-375-check.js``
(paste into devtools at a 375px device viewport).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"
STYLE = WEBSITE / "style.css"
SCRIPT = REPO / "scripts" / "ops" / "website-375-check.js"

PAGES = {
    "index.html": "",
    "exchange.html": "",
    "explorer.html": "",
    "marketplace.html": "",
    "bridges.html": "",
    "blocks.html": "",
    "alerts.html": "",
    "customer-dashboard.html": "",
    "shop-dashboard.html": "",
    "follower-api-key-announcement.html": "",
    "block.html": "?height=48691",
    "tx.html": "?hash=0x" + "ab" * 32,
    "search.html": "?query=0x" + "cd" * 20,
    "messages.html": "",
}


# ---------------------------------------------------------------------------
# Heuristic layer
# ---------------------------------------------------------------------------


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _TableParser(HTMLParser):
    """Tables with their ancestor class lists."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, set[str]]] = []
        self.tables: list[list[set[str]]] = []
        self.controls_in_class: dict[str, int] = {}  # class -> count of nested controls

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = set((dict(attrs).get("class") or "").split())
        if tag in ("input", "select", "button"):
            for _, ancestors in self.stack:
                for cls in ancestors:
                    self.controls_in_class[cls] = self.controls_in_class.get(cls, 0) + 1
        if tag == "table":
            self.tables.append([c for _, c in self.stack])
        if tag not in _VOID:
            self.stack.append((tag, classes))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def _overflow_wrapper_classes(css: str) -> set[str]:
    """Single-class selectors whose rule sets overflow-x to a clipping value."""
    out: set[str] = set()
    for m in re.finditer(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", css):
        if re.search(r"overflow-x:\s*(auto|scroll|hidden|clip)", m.group(2)):
            out.add(m.group(1))
    return out


def _flex_rules(css: str) -> dict[str, tuple[str, bool]]:
    """Single-class selectors carrying display:flex → (direction, wraps)."""
    rules: dict[str, tuple[str, bool]] = {}
    for m in re.finditer(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", css):
        if re.search(r"display:\s*flex\b", m.group(2)):
            d = re.search(r"flex-direction:\s*(\S+)", m.group(2))
            rules[m.group(1)] = (
                d.group(1) if d else "row",
                bool(re.search(r"flex-wrap:\s*wrap", m.group(2))),
            )
    return rules


class TestLayoutHeuristics(unittest.TestCase):
    """Static rules — cannot measure scrollWidth; see TestLayout375Browser."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.css = STYLE.read_text(encoding="utf-8")
        cls.parsers: dict[str, _TableParser] = {}
        for page in sorted(WEBSITE.glob("*.html")):
            p = _TableParser()
            p.feed(page.read_text(encoding="utf-8"))
            cls.parsers[page.name] = p

    def test_every_markup_table_sits_in_an_overflow_wrapper(self) -> None:
        wrappers = _overflow_wrapper_classes(self.css)
        bad: list[str] = []
        for name, p in self.parsers.items():
            for ancestors in p.tables:
                if not any(cls & wrappers for cls in ancestors):
                    bad.append(f"{name}: <table> outside any overflow wrapper ({ancestors})")
        self.assertEqual([], bad, "tables without an overflow-wrapped ancestor:\n" + "\n".join(bad))

    def test_js_emitted_tables_are_wrapped(self) -> None:
        # Scan every website/*.js — any new table emitter is covered
        # automatically. Every emitted <table> must sit in a .table-wrap
        # template within 400 chars before it.
        for jspath in sorted(WEBSITE.glob("*.js")):
            js = jspath.name
            src = jspath.read_text(encoding="utf-8")
            for m in re.finditer(r'<table[^>]*class="([^"]*)"', src):
                head = src[max(0, m.start() - 400) : m.start()]
                self.assertIn(
                    'class="table-wrap"',
                    head,
                    f"{js}: emitted table {m.group(1)!r} is not inside a table-wrap template",
                )

    def test_flex_rows_holding_controls_wrap(self) -> None:
        # Row-direction flex only — horizontal overflow is the defect class;
        # flex-wrap is meaningless on column-direction containers.
        flex = _flex_rules(self.css)
        bad: list[str] = []
        for name, p in self.parsers.items():
            for cls, n in p.controls_in_class.items():
                rule = flex.get(cls)
                if rule and rule[0] == "row" and not rule[1]:
                    bad.append(f"{name}: .{cls} is display:flex without flex-wrap but holds {n} controls")
        self.assertEqual([], bad, "control-bearing flex rows that cannot wrap:\n" + "\n".join(sorted(bad)))

    def test_phone_breakpoint_form_controls_get_16px(self) -> None:
        m = re.search(
            r"@media\s*\(pointer:\s*coarse\)\s*,\s*\(max-width:\s*640px\)\s*\{(?P<body>.*?)^\}",
            self.css,
            re.S | re.M,
        )
        self.assertIsNotNone(m, "no (pointer: coarse)/(max-width:640px) tap-target block found")
        body = m.group("body")
        sel = re.search(r"(input:not\(\[type=.checkbox.\]\)[^,{]*,\s*select,\s*textarea)\s*\{([^}]*)\}", body)
        self.assertIsNotNone(sel, "media block does not cover input/select/textarea")
        self.assertIn("font-size: 16px", sel.group(2), "form controls lack font-size:16px at the phone breakpoint")

    def test_w1_fix_pinned(self) -> None:
        m = re.search(r"\.visually-hidden\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertRegex(
            m.group(1), r"left:\s*0\b", ".visually-hidden lost left:0 — clipped spans inside scrolled tables re-widen the page"
        )

    def test_w2_fix_pinned(self) -> None:
        m = re.search(r"\.journal-controls\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertIn("flex-wrap: wrap", m.group(1), ".journal-controls must wrap at narrow widths")
        # min-width:auto floors a flex item at its min-content — a long unit
        # name option made the live page overflow even with wrap. Pin both
        # layers: the row (flex item of .journal-head) and the selects.
        self.assertIn("min-width: 0", m.group(1), ".journal-controls is a flex item of .journal-head — needs min-width:0")
        m2 = re.search(r"\.journal-controls\s+select\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m2)
        self.assertIn(
            "min-width: 0", m2.group(1), ".journal-controls select needs min-width:0 or min-content beats max-width:100%"
        )

    def test_web_pages1_fixes_pinned(self) -> None:
        # WEB-PAGES-1: topic.html and author.html scrolled sideways on a
        # phone — unbreakable hex (topic hash, author address, moderator
        # list) won over min-content. Pin the wrap rules.
        m = re.search(r"\.subtitle\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertIn("overflow-wrap: anywhere", m.group(1), ".subtitle must break unbroken identifiers")
        m = re.search(r"\.card\s+p\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertIn("overflow-wrap: anywhere", m.group(1), ".card p must break unbroken identifiers")
        m = re.search(r"\.card\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertIn("min-width: 0", m.group(1), ".card needs min-width:0 or min-content beats the grid")
        # 44px tap targets live in the shared phone/touch media block.
        m = re.search(
            r"@media\s*\(pointer:\s*coarse\)\s*,\s*\(max-width:\s*640px\)\s*\{(?P<body>.*?)^\}",
            self.css,
            re.S | re.M,
        )
        self.assertIsNotNone(m)
        body = m.group("body")
        for sel in (".msg-topic-chip", ".clickable-value", ".msg-author", "#contact-email-link"):
            self.assertIn(sel, body, f"{sel} is missing from the phone tap-target block")

    def test_web_bridges3_fix_pinned(self) -> None:
        # WEB-BRIDGES-3: the tx link inside a phone card line was 22px tall —
        # the only <a> inside .bridge-card-line (addresses are spans), so
        # this selector reaches exactly it and nothing on the desktop table.
        m = re.search(
            r"@media\s*\(pointer:\s*coarse\)\s*,\s*\(max-width:\s*640px\)\s*\{(?P<body>.*?)^\}",
            self.css,
            re.S | re.M,
        )
        self.assertIsNotNone(m, "no (pointer: coarse)/(max-width:640px) tap-target block found")
        sel = re.search(r"\.bridge-card-line\s+a\s*\{([^}]*)\}", m.group("body"))
        self.assertIsNotNone(sel, ".bridge-card-line a is missing from the phone tap-target block")
        self.assertIn("min-height: 44px", sel.group(1), ".bridge-card-line a lacks the 44px floor")

    def test_web_polish1_topic_filter_pinned(self) -> None:
        # WEB-POLISH-1: the messages topic filter truncated long chips into
        # a horizontal scroll strip at 375 px. The fix wraps the row and
        # caps each chip at the card's content width.
        m = re.search(r"\.msg-topic-list\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertIn("flex-wrap: wrap", m.group(1), ".msg-topic-list must wrap, not scroll-truncate")
        self.assertIn("min-width: 0", m.group(1), ".msg-topic-list needs min-width:0 inside the card")
        m = re.search(r"\.topic-item\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertIn("max-width: 100%", m.group(1), ".topic-item must cap at the card's content width")
        self.assertIn("min-height: 44px", m.group(1), ".topic-item lost the 44px touch target")

    def test_no_sub_11px_font_sizes(self) -> None:
        # WEB-POLISH-1 item 3: nothing may render body text below ~11px.
        # The --font-xs token (0.72rem ≈ 11.5px) is the floor; any literal
        # rem/em/px size under it is a regression. rem→px at the 16px root.
        self.assertIn("--font-xs: 0.72rem", self.css)
        bad: list[str] = []
        for m in re.finditer(r"font-size:\s*([0-9.]+)(px|rem|em)\b", self.css):
            v, unit = float(m.group(1)), m.group(2)
            px = v if unit == "px" else v * 16
            if px < 11:
                bad.append(f"font-size: {m.group(0)} ≈ {px:.1f}px")
        self.assertEqual([], bad, "font sizes under 11px:\n" + "\n".join(bad))

    def test_web_bridges4_table_stacking_pinned(self) -> None:
        # WEB-BRIDGES-4: the bridge table scrolled inside .table-wrap at
        # desktop widths (861px in a 786px wrap). The fix stacks the address
        # and tx-hash halves and the copy button inside table cells — cards
        # keep everything on one line. Pin the CSS group, the emitted
        # classes, and the padding step that closes the last gap at 768px.
        m = re.search(r"([^{}]*\.bridge-table\s+\.bridge-copy[^{}]*)\{([^}]*)\}", self.css)
        self.assertIsNotNone(m, "no .bridge-table .bridge-copy rule — the table lost its stacking group")
        self.assertIn("display: block", m.group(2), ".bridge-copy must stack under the value in table cells")
        for cls in (".bridge-addr-a", ".bridge-addr-b", ".bridge-tx-a", ".bridge-tx-b"):
            self.assertIn(f".bridge-table {cls}", m.group(1), f"{cls} missing from the table stacking group")
        js = (WEBSITE / "bridges.js").read_text(encoding="utf-8")
        for cls in ("bridge-addr-a", "bridge-addr-b", "bridge-tx-a", "bridge-tx-b", "bridge-copy"):
            self.assertIn(cls, js, f"bridges.js no longer emits {cls}")
        m = re.search(r"\.bridge-table\s+td\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertIn("padding: 0.45rem 0.3rem", m.group(1), "td padding step-down is part of the 768px fit")
        # WEB-BRIDGES-5: long live chain ids (ait-shadow-soak…) made the
        # Route cell 148px and re-broke the 768px fit — the td must be able
        # to wrap inside its stacked spans.
        m = re.search(r"\.bridge-table\s+\.bridge-route\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m, "no .bridge-table .bridge-route wrap rule")
        self.assertIn("white-space: normal", m.group(1))
        self.assertIn("overflow-wrap: anywhere", m.group(1))

    def test_explorer_inner_container_adds_no_inset(self) -> None:
        # WEB-POLISH-1 item 5: explorer.html nests a second .container
        # inside the page one — it must not re-pad or the cards sit deeper
        # than on every other page.
        m = re.search(r"\.explorer-container\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m)
        self.assertIn("padding: 0", m.group(1), ".explorer-container must not add its own inset")


# ---------------------------------------------------------------------------
# Browser layer — skipped cleanly when no browser exists
# ---------------------------------------------------------------------------

_HEX = "ab" * 32
_FIXTURES = {
    "/rpc/network-info": {
        "is_hub": True,
        "role": "HUB",
        "p2p_node_id": "fixture-node",
        "chain_id": "aitbc-fixture",
        "contact_email": "",
    },
    "/v1/market/jobs": [
        {
            "job_id": f"job_{i}",
            "state": "completed",
            "payment_status": "paid",
            "model": "fixture-model-70b",
            "escrow_contract_id": "0x" + _HEX,
            "tx_hash": "0x" + _HEX,
            "requested_at": "2026-10-15T20:41:00Z",
        }
        for i in range(3)
    ],
    "/v1/jobs": [],
    "/api/analytics/top-addresses": {"addresses": [{"address": "0x" + "cd" * 20, "transaction_count": 42} for _ in range(3)]},
    "/rpc/account/": {"balance": "72000000"},
    "/api/chain/head": {"height": 48691, "hash": "0x" + _HEX, "timestamp": "2026-10-15T21:00:00Z"},
    "/api/alerts/history": {
        "events": [{"name": "FixtureAlert", "state": "firing", "since": "2026-10-15T19:00:00Z", "detail": "fixture"}]
    },
    "/api/alerts": {"firing": [], "pending": [], "prometheus_ok": True, "watcher": {}},
    "/api/journal/counts": {"prometheus_ok": True},
    # Long unit name populates a long #journal-unit <option> — exercises the
    # min-width:auto floor that made the live alerts page overflow at 375px.
    "/api/journal/recent": {
        "entries": [
            {
                "ts": "2026-10-15T19:00:00Z",
                "unit": "aitbc-blockchain-node.service",
                "priority": "warning",
                "message": "fixture entry",
            }
        ],
        "journal_access": True,
    },
    # Five blocks x (1 block row + 1 tx row) = 10 live-feed items on
    # explorer.html — exercises the .live-feed-item tap targets that only
    # exist once the feed actually renders.
    "/api/blocks/latest": {
        "blocks": [
            {
                "height": 48691 - i,
                "hash": "0x" + _HEX,
                "tx_count": 1,
                "timestamp": "2026-10-15T21:00:00Z",
                "proposer": "0x" + "ef" * 20,
                "transactions": [{"tx_hash": "0x" + _HEX, "type": "TRANSFER", "created_at": "2026-10-15T21:00:00Z"}],
            }
            for i in range(5)
        ]
    },
    "/api/blocks/non-empty": {
        "blocks": [
            {
                "height": 48690 - i,
                "hash": "0x" + _HEX,
                "tx_count": i + 1,
                "timestamp": "2026-10-15T20:00:00Z",
                "proposer": "0x" + "ef" * 20,
            }
            for i in range(30)
        ]
    },
    "/api/blocks/by-hash/": {"height": 48691, "hash": "0x" + _HEX, "transactions": []},
    "/api/blocks/by-address/": {"blocks": []},
    "/api/blocks/": {
        "height": 48691,
        "hash": "0x" + _HEX,
        "proposer": "0x" + "ef" * 20,
        "timestamp": "2026-10-15T20:00:00Z",
        "transactions": [],
    },
    "/api/transactions/by-hash/": {
        "tx_hash": "0x" + _HEX,
        "type": "TRANSFER",
        "status": "confirmed",
        "sender": "0x" + "ef" * 20,
        "recipient": "0x" + "cd" * 20,
        "block_height": 48690,
    },
    "/api/transactions/search": {"transactions": [], "blocks": []},
    "/api/analytics/network-stats": {
        "total_ait": 0,
        "transfer_volume_ait": 0,
        "active_offers": 5,
        "anchored_offers": 5,
        "unique_nodes": 5,
        "unique_providers": 3,
        "total_transactions": 100,
    },
    # Real shape (routers/analytics.py): {labels, datasets:[{label,data,...}]}.
    # One all-zero dataset exercises the labels.filter — the legend must show
    # N=2 active types, not the 3 datasets returned.
    "/api/analytics/activity": {
        "labels": ["2026-10-16", "2026-10-17", "2026-10-18"],
        "datasets": [
            {"label": "TRANSFER", "data": [5, 7, 3], "backgroundColor": "#10b981"},
            {"label": "ESCROW_LOCK", "data": [0, 0, 0], "backgroundColor": "#c4b5fd"},
            {"label": "EXCHANGE", "data": [1, 0, 2], "backgroundColor": "#84cc16"},
        ],
    },
    "/api/analytics/provider-reputation/": {
        "score": 98,
        "level": "GOLD",
        "transactions": 12,
        "days_active": 30,
        "total_volume": 5,
    },
    "/v1/market/gpu/list": {
        "offers": [
            {"id": "offer-1", "service_type": "ollama", "price_ait": "1.5", "provider": "0x" + "ef" * 20, "status": "open"}
        ]
    },
    "/v1/market/offer": {"offers": []},
    "/v1/exchange/history": {"trades": []},
    "/exchange/price": {"price_ait": "1.0"},
    # WEB-BRIDGES-4/-5: realistic row mix — 42-char 0x addresses, 66-char
    # transfer ids, a refunded row, and the live chain names
    # (ait-hub/ait-shadow-soak/ait-v2-leaf-test, full ids ending
    # .aitbc.bubuit.net) so the desktop-width table-fit guard exercises
    # the widest Route cell, not a trivially short dataset.
    "/rpc/bridge/transfers": {
        "transfers": [
            {
                "transfer_id": "0x" + _HEX,
                "confirm_time": "2026-10-15T19:30:00Z",
                "source_chain": "ait-hub.aitbc.bubuit.net",
                "target_chain": "ait-shadow-soak.aitbc.bubuit.net",
                "sender": "0x" + "ef" * 20,
                "recipient": "0x" + "cd" * 20,
                "amount": "36000000",
                "release_amount": "35900000",
                "asset": "native",
                "status": "completed",
            },
            {
                "transfer_id": "0x" + "12" * 32,
                "confirm_time": "2026-10-15T18:10:00Z",
                "source_chain": "ait-hub.aitbc.bubuit.net",
                "target_chain": "ait-v2-leaf-test.aitbc.bubuit.net",
                "sender": "0x" + "aa" * 20,
                "recipient": "0x" + "aa" * 20,
                "amount": "12000000",
                "release_amount": "0",
                "asset": "native",
                "status": "refunded",
            },
            {
                "transfer_id": "0x" + "34" * 32,
                "confirm_time": "2026-10-14T09:00:00Z",
                "source_chain": "ait-shop-island.aitbc.bubuit.net",
                "target_chain": "ait-hub.aitbc.bubuit.net",
                "sender": "0x" + "bb" * 20,
                "recipient": "0x" + "99" * 20,
                "amount": "5000000",
                "release_amount": "4990000",
                "asset": "native",
                "status": "failed",
            },
            {
                "transfer_id": "0x" + "56" * 32,
                "confirm_time": "2026-10-15T20:00:00Z",
                "source_chain": "ait-hub.aitbc.bubuit.net",
                "target_chain": "sepolia",
                "sender": "0x" + "77" * 20,
                "recipient": "0x" + "11" * 20,
                "amount": "8000000",
                "asset": "native",
                "status": "pending",
            },
        ]
    },
    "/v1/bridge/status": {},
    "/v1/monitoring/metrics": {},
    "/pool-hub/v1/sla/metrics/": {},
    # MSG-4 read surface — a couple of topics and messages so messages.html
    # renders its rows in the fixture pass.
    "/api/messages/topics": {
        "success": True,
        "chain_id": "aitbc-fixture",
        "index_height": 48865,
        "topics": [
            # Long slugs + badges — the chip row must wrap inside its card
            # at 375 px, not truncate into a hidden scroll strip.
            {
                "topic": "governance-proposals",
                "message_count": 42,
                "pinned_count": 2,
                "locked": True,
                "last_block_height": 48865,
                "last_timestamp": "2026-10-15T22:30:00Z",
            },
            {
                "topic": "hardware-benchmarks-rtx4090",
                "message_count": 128,
                "hidden_count": 1,
                "last_block_height": 48860,
                "last_timestamp": "2026-10-15T22:00:00Z",
            },
            {
                "topic": "marketplace-offers-wrx",
                "message_count": 7,
                "last_block_height": 48850,
                "last_timestamp": "2026-10-15T21:00:00Z",
            },
            {
                "topic": "escrow-dispute-resolution",
                "message_count": 3,
                "last_block_height": 48840,
                "last_timestamp": "2026-10-15T20:00:00Z",
            },
        ],
        "count": 4,
        "total_topics": 4,
        "scan_bounded": False,
    },
    "/api/messages": {
        "success": True,
        "chain_id": "aitbc-fixture",
        "index_height": 48865,
        "messages": [
            {
                "message_id": "0x" + _HEX,
                "tx_hash": "0x" + _HEX,
                "block_height": 48865,
                "author": "0x" + "cd" * 20,
                "sender": "0x" + "cd" * 20,
                "topic": "msg-fix",
                "kind": "post",
                "body": "fixture message body",
                "parent": None,
                "timestamp": "2026-10-15T22:30:00Z",
                "fee": 360000,
            }
        ],
        "count": 1,
        "next_cursor": None,
        "scan_bounded": False,
    },
}

_STUB_JS = f"""
window.fetch = ((u, opts) => {{
  let p = new URL(u, location.origin).pathname;
  p = p.replace(/^\\/explorer-api/, '');
  const F = {json.dumps(_FIXTURES)};
  const keys = Object.keys(F).sort((a, b) => b.length - a.length);
  for (const k of keys) {{
    if (p === k || p.startsWith(k)) {{
      return Promise.resolve(new Response(JSON.stringify(F[k]),
        {{status: 200, headers: {{'Content-Type': 'application/json'}}}}));
    }}
  }}
  return Promise.resolve(new Response('{{}}', {{status: 200,
    headers: {{'Content-Type': 'application/json'}}}}));
}});
"""

_MEASURE_JS = """
(() => {
  const vw = window.innerWidth;
  const offenders = [];
  document.querySelectorAll('*').forEach(el => {
    if (!el.getBoundingClientRect) return;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 && !el.closest('.table-wrap')) {
      offenders.push(`${el.tagName}.${[...el.classList].join('.')}#${el.id||''} right=${Math.round(r.right)}`);
    }
  });
  const TAP = '.status-strip a.status-part, .site-footer a, .filter-btn, .block-item, ' +
              '.journal-controls select, .block-list-table td a, .alerts-table td a, .top-addresses-table td a, ' +
              '.live-feed-item, tbody tr[role="link"], select.endpoint, ' +
              '.copy-btn';
  // A zero-height rect means the element sits in a display:none subtree —
  // it is not a rendered tap target, so it cannot be undersized.
  const tap = [...document.querySelectorAll(TAP)]
    .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; }).length;
  const smallCtl = [...document.querySelectorAll(
    'input:not([type="checkbox"]):not([type="radio"]), select, textarea')]
    .filter(e => parseFloat(getComputedStyle(e).fontSize) < 16).length;
  // WEB-POLISH-1: topic chips must wrap inside their card — a chip whose
  // rect runs past the topics box is truncated or bleeds (scroll-strip or
  // overflow, both are the flagged defect).
  const topicsBox = document.getElementById('topics-container');
  let chipBleed = 0;
  if (topicsBox) {
    const cb = topicsBox.getBoundingClientRect();
    chipBleed = [...topicsBox.querySelectorAll('.topic-item')]
      .filter(b => { const r = b.getBoundingClientRect();
                     return r.right > cb.right + 1 || r.left < cb.left - 1; }).length;
  }
  // WEB-BRIDGES-4: the bridge table must fit inside its .table-wrap at
  // desktop widths — before the fix it measured 861px in a 786px wrap.
  const bt = document.querySelector('.bridge-table');
  const bw = bt ? bt.closest('.table-wrap') : null;
  return JSON.stringify({sw: document.documentElement.scrollWidth, vw,
                         offenders: offenders.slice(0, 10), tap, smallCtl, chipBleed,
                         bridgeWrapCw: bw ? bw.clientWidth : 0,
                         bridgeWrapSw: bw ? bw.scrollWidth : 0,
                         bridgeTableSw: bt ? bt.scrollWidth : 0});
})()
"""


def _find_browser() -> str | None:
    env = os.environ.get("AITBC_WEBSITE_BROWSER")
    if env:
        return env
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _websockets_available() -> bool:
    try:
        import websockets  # noqa: F401

        return True
    except ImportError:
        return False


_BROWSER = _find_browser()
_HAS_WS = _websockets_available()


@unittest.skipUnless(_BROWSER and _HAS_WS, "skipped: no browser (chromium on PATH) or no websockets package")
class TestLayout375Browser(unittest.TestCase):
    """Real layout engine pass — never enforced in CI until a browser host exists."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        handler = partial(SimpleHTTPRequestHandler, directory=str(WEBSITE))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.httpd.server_address[1]
        cls.httpd_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.httpd_thread.start()
        cls.addClassCleanup(cls.httpd.shutdown)

        cls.cdp_port = cls._free_port()
        cls.proc = subprocess.Popen(
            [
                _BROWSER,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                f"--remote-debugging-port={cls.cdp_port}",
                "--remote-allow-origins=*",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls.addClassCleanup(cls.proc.terminate)
        cls.ws_url = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{cls.cdp_port}/json/list", timeout=1) as r:
                    tabs = json.load(r)
                if tabs:
                    cls.ws_url = tabs[0]["webSocketDebuggerUrl"]
                    break
            except Exception:  # noqa: BLE001,S110 -- CDP endpoint poll: retry until the timeout decides
                pass
            time.sleep(0.25)
        if not cls.ws_url:
            raise unittest.SkipTest("skipped: browser did not open a CDP endpoint")

    @staticmethod
    def _free_port() -> int:
        import socket

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def _measure(self, path: str, width: int = 375, expression: str = "") -> dict:
        import asyncio
        import websockets

        async def go() -> dict:
            async with websockets.connect(self.ws_url, max_size=50 * 1024 * 1024) as ws:
                mid = 0

                async def send(method: str, params: dict | None = None) -> dict:
                    nonlocal mid
                    mid += 1
                    await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
                    while True:
                        msg = json.loads(await ws.recv())
                        if msg.get("id") == mid:
                            if "error" in msg:
                                raise AssertionError(f"CDP {method}: {msg['error']}")
                            return msg

                await send("Page.enable")
                # mobile=False pins innerWidth at the requested width — with
                # mobile=True Chrome lets the layout viewport grow to fit
                # wide content and scrollWidth==innerWidth passes vacuously.
                await send(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": 800, "deviceScaleFactor": 1, "mobile": False},
                )
                await send("Page.addScriptToEvaluateOnNewDocument", {"source": _STUB_JS})
                await send("Page.navigate", {"url": f"http://127.0.0.1:{self.port}/{path}"})
                await asyncio.sleep(2.5)
                res = await send("Runtime.evaluate", {"expression": expression or _MEASURE_JS, "returnByValue": True})
                val = res.get("result", {}).get("result", {}).get("value")
                self.assertIsNotNone(val, f"{path}: measurement produced no result")
                return json.loads(val)

        return asyncio.run(go())

    def test_no_horizontal_overflow_at_375px(self) -> None:
        """Primary W5 assertion: whole-page scrollWidth <= innerWidth."""
        bad: list[str] = []
        for page, qs in PAGES.items():
            r = self._measure(page + qs)
            if r["sw"] > r["vw"]:
                bad.append(f"{page}: scrollWidth={r['sw']} > {r['vw']} via {r['offenders']}")
        self.assertEqual([], bad, "pages with horizontal overflow at 375px:\n" + "\n".join(bad))

    def test_tap_targets_and_form_fonts_at_375px(self) -> None:
        """Secondary W5 assertion — separate so a tap regression can't mask overflow."""
        bad: list[str] = []
        for page, qs in PAGES.items():
            r = self._measure(page + qs)
            if r["tap"] or r["smallCtl"]:
                bad.append(f"{page}: {r['tap']} targets <44px, {r['smallCtl']} controls <16px")
        self.assertEqual([], bad, "pages with undersized targets/fonts at 375px:\n" + "\n".join(bad))

    def test_messages_topic_chips_stay_in_card_at_375px(self) -> None:
        """WEB-POLISH-1: long topic chips must wrap inside the topics card —
        none may have a rect running past #topics-container."""
        r = self._measure("messages.html")
        self.assertEqual(0, r["chipBleed"], f"topic chips escape the card: {r['offenders']}")

    def test_bridge_table_fits_wrap_at_desktop_widths(self) -> None:
        """WEB-BRIDGES-4: .table-wrap may keep overflow-x:auto as a safety
        net but must not need it — the table fits at every served width."""
        for w in (768, 1024, 1280, 1440):
            r = self._measure("bridges.html", width=w)
            self.assertGreater(r["bridgeWrapCw"], 0, f"{w}px: .bridge-table not rendered")
            self.assertLessEqual(
                r["bridgeWrapSw"],
                r["bridgeWrapCw"],
                f"{w}px: bridge table scrolls inside .table-wrap "
                f"({r['bridgeWrapSw']} > {r['bridgeWrapCw']}; table={r['bridgeTableSw']})",
            )

    def test_legend_toggle_at_375_and_1280(self) -> None:
        """WEB-LEGEND-1/2: at <=640px the chart legend starts collapsed behind
        a visible >=44px toggle reading Types (N=filtered items); above 640px
        the legend renders and the toggle is display:none (desktop unchanged).
        The toggle lives OUTSIDE the fixed-height chart container — the canvas
        must stay inside #activity-chart-container and clear of #chart-source
        in both collapsed and expanded states (WEB-LEGEND-1 v1 put it inside
        and pushed the canvas 52px out of the box, over the source line).
        """
        expr = """
        (() => {
          const c = window.activityChartInstance;
          const btn = document.getElementById('legend-toggle');
          const box = document.getElementById('activity-chart-container');
          const cv = document.getElementById('activity-chart');
          const src = document.getElementById('chart-source');
          if (!c || !btn || !box || !cv || !src) return JSON.stringify({err: 'missing node'});
          const rect = (e) => { const b = e.getBoundingClientRect(); return {t: b.top, b: b.bottom}; };
          const snap = () => ({
            legendH: c.legend ? c.legend.height : 0,
            display: c.options.plugins.legend.display,
            btnH: btn.getBoundingClientRect().height,
            hidden: btn.hidden,
            cssDisplay: getComputedStyle(btn).display,
            text: btn.textContent,
            ariaExpanded: btn.getAttribute('aria-expanded'),
            canvasInBox: rect(cv).b <= rect(box).b + 0.5,
            canvasClearOfSrc: rect(cv).b <= rect(src).t + 0.5,
          });
          const collapsed = snap();
          btn.click();
          const expanded = snap();
          return JSON.stringify({collapsed, expanded});
        })()
        """
        r375 = self._measure("explorer.html", 375, expr)
        self.assertIsNone(r375.get("err"), f"375px: {r375}")
        c375, e375 = r375["collapsed"], r375["expanded"]
        self.assertFalse(c375["display"], "375px: legend must start collapsed")
        self.assertLess(c375["legendH"], 40, "375px: collapsed legend box must free the space")
        self.assertFalse(c375["hidden"], "375px: toggle must be visible with data")
        self.assertNotEqual(c375["cssDisplay"], "none", "375px: toggle must render")
        self.assertGreaterEqual(c375["btnH"], 44, "375px: toggle must be a 44px target")
        self.assertEqual("false", c375["ariaExpanded"])
        self.assertEqual("Types (2)", c375["text"], "N = active datasets (fixture: 3 sent, 1 zero)")
        self.assertTrue(c375["canvasInBox"], "375px collapsed: canvas must stay in its box")
        self.assertTrue(c375["canvasClearOfSrc"], "375px collapsed: canvas must clear the source line")
        self.assertTrue(e375["display"], "375px: click expands the legend")
        self.assertGreater(e375["legendH"], c375["legendH"])
        self.assertTrue(e375["canvasInBox"], "375px expanded: canvas must stay in its box")
        self.assertTrue(e375["canvasClearOfSrc"], "375px expanded: canvas must clear the source line")

        r1280 = self._measure("explorer.html", 1280, expr)
        self.assertIsNone(r1280.get("err"), f"1280px: {r1280}")
        c1280 = r1280["collapsed"]
        self.assertTrue(c1280["display"], "1280px: legend must render as before")
        self.assertGreater(c1280["legendH"], 0, "1280px: legend has height as before")
        self.assertEqual("none", c1280["cssDisplay"], "1280px: toggle hidden on desktop")


if __name__ == "__main__":
    unittest.main()
