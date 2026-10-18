"""Blocks page must not run Explorer init (null-listener error on live).

blocks.html loads explorer.js for the shared top-level ``renderBlockCard``
helper — but the file's DOMContentLoaded handler is page init: it bound
``clear-search-btn``/``search-input`` listeners unguarded (Uncaught
TypeError on blocks.html, observed live) and started three intervals that
polled the explorer API for a page that has none of the panels. The handler
now returns early when ``#live-feed-list`` is absent, so a non-Explorer
page gets zero listeners, zero intervals and zero fetches while still
keeping ``renderBlockCard`` available.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

WEBSITE = Path(__file__).resolve().parents[2] / "website"

_NODE_VM = r"""
const fs = require('fs');
const vm = require('vm');
const explorerFile = process.argv[1];
let domReady = null;
let intervals = 0;
let fetches = 0;
const document = {
    // blocks.html owns none of the Explorer elements — every lookup is null.
    getElementById: () => null,
    createElement: () => ({ style: {}, setAttribute() {}, appendChild() {}, addEventListener() {}, classList: { add(){}, toggle(){} } }),
    addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') domReady = fn; },
    querySelector: () => null,
    querySelectorAll: () => [],
    body: { appendChild() {} },
    hidden: false,
};
const sandbox = {
    document,
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }), scrollTo() {}, requestAnimationFrame() { return 0; }, scrollY: 0 },
    fetch: () => { fetches++; return Promise.reject(new Error('fetch fired on non-explorer page')); },
    console: { log() {}, error() {}, warn() {} },
    setInterval: () => { intervals++; return 0; },
    setTimeout: () => 0, clearInterval() {}, clearTimeout() {},
    Intl, Date, Promise, JSON, Object, Array, String, Number, Boolean, Math, isNaN, parseFloat, parseInt, encodeURIComponent, URL, URLSearchParams,
    lucide: { createIcons() { sandbox.__icons = (sandbox.__icons || 0) + 1; } },
};
sandbox.window.AITBC_CONFIG = { explorerApiUrl: '/explorer-api', chainId: 'c' };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(explorerFile, 'utf8'), sandbox);
let threw = null;
try {
    if (domReady) domReady();
} catch (e) {
    threw = String(e && e.message || e);
}
console.log(JSON.stringify({
    handlerRegistered: !!domReady,
    threw,
    intervals,
    fetches,
    icons: sandbox.__icons || 0,
    hasRenderBlockCard: typeof sandbox.renderBlockCard === 'function' || typeof sandbox.window.renderBlockCard === 'function',
}));
"""


class TestBlocksPageSkipsExplorerInit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("node"):
            raise unittest.SkipTest("node not installed")

    def _run(self) -> dict:
        out = subprocess.run(
            ["node", "-e", _NODE_VM, str(WEBSITE / "explorer.js")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(out.returncode, 0, f"vm failed: {out.stderr[:800]}")
        return json.loads(out.stdout.strip())

    def test_dom_ready_is_noop_without_explorer_dom(self) -> None:
        r = self._run()
        self.assertTrue(r["handlerRegistered"], "no DOMContentLoaded handler found")
        self.assertIsNone(r["threw"], f"init threw on a page without Explorer DOM: {r['threw']}")
        self.assertEqual(r["intervals"], 0, "poll intervals started on a non-Explorer page")
        self.assertEqual(r["fetches"], 0, "explorer API fetched on a non-Explorer page")

    def test_render_block_card_stays_available(self) -> None:
        # blocks.js renders cards via the shared top-level helper — the gate
        # must not take it away.
        r = self._run()
        self.assertTrue(r["hasRenderBlockCard"], "renderBlockCard not defined at top level")

    def test_source_pin_gate_before_icons(self) -> None:
        src = (WEBSITE / "explorer.js").read_text()
        gate = "if (!document.getElementById('live-feed-list')) return;"
        handler = "document.addEventListener('DOMContentLoaded'"
        icons = "lucide.createIcons()"
        self.assertIn(gate, src, "Explorer-page gate missing")
        self.assertLess(src.index(handler), src.index(gate), "gate sits outside DOMContentLoaded")
        self.assertLess(src.index(gate), src.index(icons), "gate must run before page init")


if __name__ == "__main__":
    unittest.main()
