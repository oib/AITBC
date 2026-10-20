"""RESET-WEB-FRESH-1 (#339) — website pages against a fresh bc-2 chain.

A chain right after genesis serves real but nearly-empty data: a handful
of empty blocks, no transactions, no offers, an empty order book, zeroed
analytics. Every page must render its honest empty state — never an
exception, never a "failed to load" note for a read that answered fine,
never the old chain's identity.

The browser layer skips cleanly when no Chromium binary (or the
``websockets`` package) exists, same contract as
``test_website_layout_375.TestLayout375Browser`` — CI without a browser
runs nothing here, the IDE host runs all of it.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

import sys
from pathlib import Path

# Sibling harness modules are imported by their plain names. Whole-suite runs
# put tests/unit on sys.path, but a lone-file run does not — insert it so this
# module collects standalone too.
_UNIT = str(Path(__file__).resolve().parent)
if _UNIT not in sys.path:
    sys.path.insert(0, _UNIT)

import test_website_layout_375 as base  # noqa: E402
import test_website_states as states  # noqa: E402

WEBSITE = base.WEBSITE
_BROWSER = base._find_browser()
_HAS_WS = base._websockets_available()

_HEX = "ab" * 32
_FRESH: dict = {
    "/rpc/network-info": {
        "is_hub": True,
        "role": "HUB",
        "p2p_node_id": "fixture-hub",
        "chain_id": "bc-2",
        "contact_email": "",
        "validators": ["0x" + "ab" * 20, "0x" + "cd" * 20, "0x" + "ef" * 20, "0x" + "12" * 20],
    },
    "/rpc/head": {"height": 3, "hash": "0x" + _HEX, "timestamp": "2026-10-20T00:03:00Z"},
    "/api/chain/head": {"height": 3, "hash": "0x" + _HEX, "timestamp": "2026-10-20T00:03:00Z"},
    # Three empty blocks — the real fresh-chain shape, not a missing array.
    "/api/blocks/latest": {
        "blocks": [
            {
                "height": 3 - i,
                "hash": "0x" + _HEX,
                "tx_count": 0,
                "timestamp": f"2026-10-20T00:0{3 - i}:00Z",
                "proposer": "0x" + "ef" * 20,
                "transactions": [],
            }
            for i in range(3)
        ]
    },
    "/api/blocks/non-empty": {"blocks": []},
    "/api/analytics/network-stats": {
        "total_ait": 0,
        "transfer_volume_ait": 0,
        "active_offers": 0,
        "anchored_offers": 0,
        "unique_nodes": 0,
        "unique_providers": 0,
        "total_transactions": 0,
    },
    "/api/analytics/activity": {"labels": [], "datasets": []},
    "/api/analytics/top-addresses": {"addresses": []},
    "/v1/market/offer": {"offers": []},
    "/v1/market/jobs": [],
    "/exchange-api/orderbook": {"sells": [], "buys": []},
    "/exchange-api/trades": {"trades": []},
    "/api/chains": {"chains": [{"id": "bc-2", "name": "AIT Hub Network", "status": "active"}]},
    "/api/alerts/history": {"events": []},
    "/api/alerts": {"firing": [], "pending": [], "prometheus_ok": True, "watcher": {}},
    "/api/journal/counts": {"prometheus_ok": True},
    "/api/journal/recent": {"entries": []},
    "/api/transactions/search": {"transactions": [], "blocks": []},
}


def _probe(fields: dict[str, str]) -> str:
    """Eval expression: read DOM facts plus the stub-recorded page errors."""
    reads = ",".join(f"{name}: ({expr})" for name, expr in fields.items())
    return f"""
(() => {{
  const t = (id) => {{ const el = document.getElementById(id); return el ? el.textContent.trim() : null; }};
  const shown = (el) => !!el && !el.hidden;
  return JSON.stringify({{ {reads}, errors: window.__errors || ['no __errors hook'] }});
}})()
"""


@unittest.skipUnless(_BROWSER and _HAS_WS, "skipped: no browser (chromium on PATH) or no websockets package")
class TestFreshChainBrowser(unittest.TestCase):
    """Pages against bc-2 fixtures — production CSP, zero uncaught errors."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        handler = partial(base._CspHandler, directory=str(WEBSITE))
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
            except Exception:  # noqa: BLE001,S110
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

    def _run(self, path: str, fields: dict[str, str], fixtures: dict | None = None) -> dict:
        r = asyncio.run(
            states._cdp_steps(
                self.ws_url,
                f"http://127.0.0.1:{self.port}/{path}",
                states._stub_js(states._fixtures(**(fixtures or _FRESH))),
                [("eval", _probe(fields))],
            )
        )
        self.assertEqual([], states._security_log_entries(r["_events"]), "CSP/security Log entries")
        return r

    def test_index_facts_show_bc2_and_low_height(self) -> None:
        """index.html fact strip: the bc-2 id and a low fresh height, live."""
        r = self._run(
            "index.html",
            {
                "island": "t('fact-island')",
                "height": "t('fact-height')",
                "validators": "t('fact-validators')",
                "chainId": "t('chain-id')",
            },
        )
        self.assertEqual("bc-2", r["island"])
        self.assertEqual("3", r["height"])
        self.assertEqual("4", r["validators"])
        self.assertEqual("bc-2", r["chainId"])
        self.assertEqual([], r["errors"])

    def test_explorer_empty_panels_and_empty_blocks_feed(self) -> None:
        """explorer.html: 3 empty blocks render as feed items (no tx chips
        crash), zeroed analytics render 'No address data yet.' and no chart."""
        r = self._run(
            "explorer.html",
            {
                "feedItems": "document.querySelectorAll('#live-feed-list .live-feed-item').length",
                "feedText": "t('live-feed-list')",
                "feedLabels": "[...document.querySelectorAll('#live-feed-list .live-feed-hash')].map(e => e.textContent.trim())",
                "topAddresses": "t('top-addresses-container')",
                "chart": "!!window.activityChartInstance",
            },
        )
        self.assertEqual(3, r["feedItems"], r["feedText"])
        self.assertEqual(["#3", "#2", "#1"], r["feedLabels"])
        self.assertEqual("No address data yet.", r["topAddresses"])
        self.assertFalse(r["chart"])
        self.assertEqual([], r["errors"])

    def test_explorer_truly_empty_feed_waits_for_activity(self) -> None:
        """blocks:[] (not merely tx-free) is a proven-empty feed — the page
        waits for activity instead of reporting a failed read."""
        r = self._run(
            "explorer.html",
            {"feedText": "t('live-feed-list')"},
            fixtures={**_FRESH, "/api/blocks/latest": {"blocks": []}},
        )
        self.assertIn("Waiting for activity", r["feedText"])
        self.assertEqual([], r["errors"])

    def test_blocks_page_empty_chain(self) -> None:
        """blocks.html with no blocks at all: 'No blocks available', no error."""
        r = self._run(
            "blocks.html",
            {"blocks": "t('blocks-container')"},
            fixtures={**_FRESH, "/api/blocks/latest": {"blocks": []}},
        )
        self.assertIn("No blocks available", r["blocks"])
        self.assertEqual([], r["errors"])

    def test_blocks_page_lists_empty_blocks(self) -> None:
        """blocks.html with 3 tx-free blocks lists them without crashing."""
        r = self._run(
            "blocks.html",
            {
                "rows": "document.querySelectorAll('#blocks-container .block-item, #blocks-container tr').length",
                "blocks": "t('blocks-container')",
            },
        )
        self.assertGreater(r["rows"], 0, r["blocks"])
        self.assertEqual([], r["errors"])

    def test_marketplace_empty_offers(self) -> None:
        """marketplace.html: proven-empty offer list shows the empty state
        and a 0-of-0 count — not the 'could not be loaded' alert."""
        r = self._run(
            "marketplace.html",
            {
                "offers": "t('offers-container')",
                "count": "t('offer-count')",
                "alert": "!!document.querySelector('.offers-state[role=\"alert\"]')",
            },
        )
        self.assertIn("No offers listed yet", r["offers"])
        self.assertEqual("Showing 0 of 0 offers", r["count"])
        self.assertFalse(r["alert"])
        self.assertEqual([], r["errors"])

    def test_exchange_empty_book(self) -> None:
        """exchange.html: an empty book+tape answers show the combined
        ob-empty line, never an error box."""
        r = self._run(
            "exchange.html",
            {
                "empty": "shown(document.getElementById('ob-empty'))",
                "emptyText": "t('ob-empty')",
                "err": "shown(document.getElementById('ob-error')) || shown(document.getElementById('ob-tape-error'))",
                "ladder": "shown(document.getElementById('ob-ladder'))",
            },
        )
        self.assertTrue(r["empty"])
        self.assertIn("empty", r["emptyText"])
        self.assertFalse(r["err"])
        self.assertFalse(r["ladder"])
        self.assertEqual([], r["errors"])


if __name__ == "__main__":
    unittest.main()
