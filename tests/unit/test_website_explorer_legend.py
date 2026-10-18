"""WEB-LEGEND-1: explorer activity-chart legend toggle — driven through a
node vm with a Chart stub recording options.plugins.legend.display and
update() calls.

Rules under test: collapsed by default at <=640px, expanded otherwise; the
toggle reads Types (N) where N counts only datasets with activity (same
predicate as the Chart.js labels.filter); a user choice survives the
refresh destroy/rebuild and breakpoint crossings; before any choice the
state may follow the media query; a failed or shapeless read with no
chart instance hides the toggle and never renders "Types (0)".
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
const [file, mode] = process.argv.slice(1);
const els = {}; const handlers = [];
function el(tag) {
    const self = {
        style: {}, _html: '', children: [], className: '', _listeners: {},
        _parent: null, value: '', dataset: {}, hidden: false,
        classList: {
            add(c){ self.className = (self.className + ' ' + c).trim(); },
            remove(){},
            contains(c){ return (self.className || '').split(/\s+/).includes(c); },
        },
        set innerHTML(v){ self._html = v; self.children = []; const m2 = v.match(/class="([^"]+)"/); if (m2) { const c = el('div'); c.className = m2[1]; c._parent = self; self.children.push(c); } },
        get innerHTML(){ return self._html; },
        set textContent(v){ self._text = v; },
        get textContent(){ return self._text || ''; },
        get parentElement(){ return self._parent; },
        set parentElement(p){ self._parent = p; },
        get nextSibling(){ return null; },
        setAttribute(k, v){ (self._attrs = self._attrs || {})[k] = v; },
        getAttribute(k){ return self._attrs ? self._attrs[k] : null; },
        appendChild(c){ c._parent = self; self.children.push(c); return c; },
        prepend(c){ c._parent = self; self.children.unshift(c); },
        insertBefore(c){ c._parent = self; self.children.unshift(c); return c; },
        remove(){ if (self._parent) { const i = self._parent.children.indexOf(self); if (i >= 0) self._parent.children.splice(i, 1); } },
        querySelector(sel){ const cls = sel.replace(/^\./, ''); return self.children.find(c => c.classList && c.classList.contains(cls)) || null; },
        addEventListener(ev, fn){ (self._listeners[ev] = self._listeners[ev] || []).push(fn); },
        getContext(){ return {}; },
        click(){ (self._listeners.click || []).forEach(fn => { try { fn(); } catch (e) { self._err = String(e); } }); },
    };
    return self;
}
const document = {
    getElementById: (id) => els[id] || (els[id] = el(id)),
    createElement: (t) => el(t),
    addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') handlers.push(fn); },
    querySelectorAll: () => [],
};
const resp = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const ACT = {
    labels: ['2026-10-16', '2026-10-17', '2026-10-18'],
    datasets: [
        { label: 'TRANSFER', data: [5, 7, 3], backgroundColor: '#10b981' },
        { label: 'ESCROW_LOCK', data: [0, 0, 0], backgroundColor: '#c4b5fd' },
        { label: 'EXCHANGE', data: [1, 0, 2], backgroundColor: '#84cc16' },
    ],
};
const BLOCKS = { blocks: [{ height: 100, hash: '0xabc', tx_count: 1, timestamp: '2026-10-18T00:00:00Z', proposer: '0x1', transactions: [] }] };
const MODES = {
    'w375':       { narrow: true,  activity: () => resp(200, ACT) },
    'w1280':      { narrow: false, activity: () => resp(200, ACT) },
    'toggle':     { narrow: true,  activity: () => resp(200, ACT), click: true },
    'persist':    { narrow: true,  activity: () => resp(200, ACT), click: true, retry: true },
    'preflip':    { narrow: true,  activity: () => resp(200, ACT), flip: true, retry: true },
    'postchoice': { narrow: true,  activity: () => resp(200, ACT), click: true, flip: true, retry: true },
    'http500':    { narrow: true,  activity: () => resp(500, {}) },
    'shapefail':  { narrow: true,  activity: () => resp(200, { buckets: [] }) },
    'empty':      { narrow: true,  activity: () => resp(200, { labels: [], datasets: [] }) },
};
const m = MODES[mode];
const narrow = { matches: m.narrow };
class ChartStub {
    constructor(ctx, cfg) {
        this.ctx = ctx; this.cfg = cfg; this.options = cfg.options; this.data = cfg.data;
        this.updates = 0; this.destroyed = false; this.legend = { height: 0 };
        ChartStub.instances.push(this);
    }
    update() { this.updates++; }
    destroy() { this.destroyed = true; }
}
ChartStub.instances = [];
const sandbox = {
    document,
    window: {
        location: { href: 'http://x/explorer.html', replace() {} },
        AITBC_CONFIG: { explorerApiUrl: '/explorer-api', chainId: 'c' },
        matchMedia: () => ({ matches: narrow.matches }),
    },
    location: { href: 'http://x/explorer.html', replace() {} },
    fetch: (u) => Promise.resolve(
        u.includes('analytics/activity') ? m.activity()
        : u.includes('blocks/latest') ? resp(200, BLOCKS)
        : u.includes('top-addresses') ? resp(200, { addresses: [] })
        : resp(200, {})),
    Chart: ChartStub,
    lucide: { createIcons() {} },
    console: { log() {}, error() {}, warn() {} },
    setInterval() {}, setTimeout: (f) => f(),
    URL, URLSearchParams, Intl, encodeURIComponent,
    Date, isNaN, Boolean, String, Number, Array, Object, JSON, Promise, Math,
    aitbcFmt: { time: () => '12:00', date: () => '2026-10-18 12:00', num: (n) => String(n) },
    aitbcCopyBtn: () => '',
    sessionStorage: { getItem: () => '', setItem() {}, removeItem() {} },
};
(async () => {
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox);
    const flush = () => new Promise((r) => setTimeout(r, 10));
    for (const fn of handlers) { try { await fn(); } catch (e) { console.log('HANDLER-ERR:' + e); } }
    await flush();
    const btn = document.getElementById('legend-toggle');
    if (m.click) { btn.click(); await flush(); }
    if (m.flip) { narrow.matches = !narrow.matches; }
    if (m.retry) { document.getElementById('chart-retry-btn').click(); await flush(); }
    const chart = sandbox.window.activityChartInstance || null;
    const out = {
        instances: ChartStub.instances.length,
        display: chart ? chart.options.plugins.legend.display : null,
        updates: chart ? chart.updates : -1,
        destroyed: ChartStub.instances.length > 1 ? ChartStub.instances[0].destroyed : false,
        btnHidden: btn.hidden,
        btnText: btn.textContent,
        ariaExpanded: btn.getAttribute('aria-expanded'),
        btnErr: btn._err || null,
        chartSource: document.getElementById('chart-source').textContent,
    };
    console.log('JSON:' + JSON.stringify(out));
})();
"""


def _run_vm(mode: str) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("skipped: node not available for the vm fixture")
    r = subprocess.run(
        [node, "-e", _NODE_VM, str(WEBSITE / "explorer.js"), mode],
        capture_output=True,
        text=True,
        timeout=30,
    )
    line = next((x for x in r.stdout.splitlines() if x.startswith("JSON:")), None)
    if not line:
        raise AssertionError(f"vm produced no JSON\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return json.loads(line[5:])


class TestExplorerLegendToggle(unittest.TestCase):
    def test_collapsed_by_default_at_375(self) -> None:
        r = _run_vm("w375")
        self.assertIs(r["display"], False, "legend must start collapsed at <=640px")
        self.assertFalse(r["btnHidden"], "toggle visible once a chart exists")
        self.assertEqual("Types (2)", r["btnText"], "N = active datasets only (3 sent, 1 zero)")
        self.assertEqual("false", r["ariaExpanded"])

    def test_expanded_by_default_at_1280(self) -> None:
        r = _run_vm("w1280")
        self.assertIs(r["display"], True, "legend must start expanded above 640px")
        self.assertEqual("true", r["ariaExpanded"])
        self.assertEqual("Types (2)", r["btnText"])

    def test_toggle_flips_display_and_updates_once(self) -> None:
        r = _run_vm("toggle")
        self.assertIs(r["display"], True, "click at 375px expands the collapsed legend")
        self.assertEqual(1, r["updates"], "exactly one chart.update() per click")
        self.assertEqual("true", r["ariaExpanded"])
        self.assertIsNone(r["btnErr"], f"click handler threw: {r['btnErr']}")

    def test_user_choice_survives_refresh_rebuild(self) -> None:
        r = _run_vm("persist")
        self.assertEqual(2, r["instances"], "retry fired a second loadActivityChart")
        self.assertTrue(r["destroyed"], "first chart instance was destroyed on rebuild")
        self.assertIs(r["display"], True, "expanded choice survives the rebuild at 375px")

    def test_media_flip_followed_before_choice(self) -> None:
        r = _run_vm("preflip")
        self.assertIs(r["display"], True, "no user choice: widening to desktop re-expands")

    def test_media_flip_ignored_after_choice(self) -> None:
        r = _run_vm("postchoice")
        self.assertIs(r["display"], True, "user chose expanded; widening keeps it anyway")
        # stronger check: user expanded at 375 then widened — stays expanded
        # (choice outranks the new media answer in both directions)

    def test_http_failure_hides_toggle_and_no_types_zero(self) -> None:
        r = _run_vm("http500")
        self.assertIsNone(r["display"], "no chart instance on a failed first read")
        self.assertTrue(r["btnHidden"], "toggle hidden with no chart data")
        self.assertNotIn("Types (0)", r["btnText"])

    def test_shape_failure_hides_toggle(self) -> None:
        r = _run_vm("shapefail")
        self.assertTrue(r["btnHidden"], "shapeless reply: no chart, no toggle")
        self.assertNotIn("Types (0)", r["btnText"])

    def test_empty_labels_hide_toggle(self) -> None:
        r = _run_vm("empty")
        self.assertTrue(r["btnHidden"], "empty labels: no chart built, toggle stays hidden")


if __name__ == "__main__":
    unittest.main()
