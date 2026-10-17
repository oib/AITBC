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
        # dashboard.js/alerts.js build tables dynamically — pin that every
        # emitted <table> is preceded by a .table-wrap in the same template.
        for js in ("dashboard.js", "alerts.js", "bridges.js"):
            src = (WEBSITE / js).read_text(encoding="utf-8")
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
        "active_offers": 0,
        "unique_nodes": 5,
        "unique_providers": 3,
        "total_transactions": 100,
    },
    "/api/analytics/activity": {"buckets": []},
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
    "/rpc/bridge/transfers": {
        "transfers": [
            {
                "transfer_id": "0x" + _HEX,
                "confirm_time": "2026-10-15T19:30:00Z",
                "source_chain": "aitbc",
                "target_chain": "sepolia",
                "sender": "0x" + "ef" * 20,
                "recipient": "0x" + "cd" * 20,
                "amount": "36000000",
                "release_amount": "35900000",
                "asset": "native",
                "status": "completed",
            }
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
            {"topic": "msg-fix", "message_count": 2, "last_block_height": 48865, "last_timestamp": "2026-10-15T22:30:00Z"},
            {"topic": "general", "message_count": 1, "last_block_height": 48860, "last_timestamp": "2026-10-15T22:00:00Z"},
        ],
        "count": 2,
        "total_topics": 2,
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
  return JSON.stringify({sw: document.documentElement.scrollWidth, vw,
                         offenders: offenders.slice(0, 10), tap, smallCtl});
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

    def _measure(self, path: str) -> dict:
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
                # mobile=False pins innerWidth at 375 — with mobile=True
                # Chrome lets the layout viewport grow to fit wide content
                # and scrollWidth==innerWidth passes vacuously.
                await send(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": 375, "height": 800, "deviceScaleFactor": 1, "mobile": False},
                )
                await send("Page.addScriptToEvaluateOnNewDocument", {"source": _STUB_JS})
                await send("Page.navigate", {"url": f"http://127.0.0.1:{self.port}/{path}"})
                await asyncio.sleep(2.5)
                res = await send("Runtime.evaluate", {"expression": _MEASURE_JS, "returnByValue": True})
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


if __name__ == "__main__":
    unittest.main()
