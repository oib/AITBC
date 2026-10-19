"""WEB-DASH-1 C: dashboard.js failed-read pass — driven through a node vm.

A failed or unreadable reply must never read as empty, zero, "no jobs",
"no SLA data" or inert N/A; ok means status-ok AND parseable AND carrying
the needed field; failures name the reason and offer Try again; a rejected
credential (401/403) is named with the real status code and gets no retry;
fallback to public data is stated, never silent; last-good rows are kept
with exactly one stale note.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

WEBSITE = Path(__file__).resolve().parents[2] / "website"

_NODE_DASH_VM = r"""
const fs = require('fs');
const [file, mode] = process.argv.slice(1);
const els = {}; const handlers = [];
function el(tag) {
    const self = {
        style: {}, _html: '', children: [], className: '', _listeners: {}, _parent: null, value: '',
        classList: { add(c){ self.className = (self.className+' '+c).trim(); }, remove(){}, contains(c){ return (self.className||'').split(/\s+/).includes(c); } },
        set innerHTML(v){ self._html = v; self.children = []; const m2 = v.match(/class="([^"]+)"/); if (m2) { const c = el('div'); c.className = m2[1]; c._parent = self; self.children.push(c); } }, get innerHTML(){ return self._html; },
        set textContent(v){ self._text = v; }, get textContent(){ return self._text || ''; },
        setAttribute(){}, appendChild(c){ c._parent = self; self.children.push(c); return c; },
        prepend(c){ c._parent = self; self.children.unshift(c); },
        remove(){ if (self._parent) { const i = self._parent.children.indexOf(self); if (i >= 0) self._parent.children.splice(i, 1); } },
        querySelector(sel){ const cls = sel.replace(/^\./,''); return self.children.find(c => c.classList && c.classList.contains(cls)) || null; },
        querySelectorAll(sel){ const cls = sel.split(',').map(t => t.trim().replace(/^\./,'')); const out = []; const walk = (n) => { for (const c of (n.children || [])) { if (c.classList && cls.some(k => c.classList.contains(k))) out.push(c); walk(c); } }; walk(self); return out; },
    };
    return self;
}
const document = {
    getElementById: (id) => els[id] || (els[id] = el(id)),
    createElement: (t) => el(t),
    addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') handlers.push(fn); },
    querySelectorAll: () => [],
};
const resp = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => (body === 'BAD' ? Promise.reject(new Error('bad json')) : body) });
const JOB = { job_id: 'j1', state: 'QUEUED', payment_status: 'settlement_failed', requested_at: '2026-10-01T10:00:00Z' };
const MODES = {
    // ---------- customer ----------
    'cust-ok': { page: 'cust', fetch: (u) => Promise.resolve(u.includes('top-addresses') ? resp(200, []) : u.includes('/v1/market/jobs') ? resp(200, { items: [JOB] }) : resp(200, {})) },
    'cust-401': { page: 'cust', cred: 'fake-key', fetch: (u) => Promise.resolve(u.includes('/v1/jobs') ? resp(401, {}) : u.includes('/v1/market/jobs') ? resp(200, { items: [JOB] }) : resp(200, [])) },
    'cust-403': { page: 'cust', cred: 'fake-key', fetch: (u) => Promise.resolve(u.includes('/v1/jobs') ? resp(403, {}) : u.includes('/v1/market/jobs') ? resp(200, { items: [JOB] }) : resp(200, [])) },
    'cust-keyed-500': { page: 'cust', cred: 'fake-key', fetch: (u) => Promise.resolve(u.includes('/v1/jobs') ? resp(500, {}) : u.includes('/v1/market/jobs') ? resp(200, { items: [JOB] }) : resp(200, [])) },
    'cust-market-shape': { page: 'cust', fetch: (u) => Promise.resolve(u.includes('/v1/market/jobs') ? resp(200, {}) : resp(200, [])) },
    'cust-market-500': { page: 'cust', fetch: (u) => Promise.resolve(u.includes('/v1/market/jobs') ? resp(500, {}) : resp(200, [])) },
    'cust-keyed-empty': { page: 'cust', cred: 'fake-key', fetch: (u) => Promise.resolve(u.includes('/v1/jobs') ? resp(200, []) : resp(200, { items: [JOB] })) },
    'cust-stale': { page: 'cust', twice: true, fetch: (u) => Promise.resolve(
        u.includes('/v1/market/jobs') ? (globalThis.__n++ === 0 ? resp(200, { items: [JOB] }) : resp(500, {})) : resp(200, [])) },
    // ---------- shop ----------
    'shop-public-ok': { page: 'shop', fetch: (u) => Promise.resolve(
        u.includes('market/jobs') ? resp(200, { jobs: [{ state: 'RELEASED' }, JOB] })
        : u.includes('network-stats') ? resp(200, { unique_providers: 3 })
        : u.includes('gpu') ? resp(200, [])
        : u.includes('offer') ? resp(200, { offers: [] })
        : resp(200, [])) },
    'shop-public-500': { page: 'shop', fetch: (u) => Promise.resolve(
        u.includes('market/jobs') ? resp(500, {}) : u.includes('gpu') || u.includes('offer') ? resp(200, []) : resp(200, {})) },
    'shop-public-shape': { page: 'shop', fetch: (u) => Promise.resolve(
        u.includes('market/jobs') ? resp(200, {}) : u.includes('gpu') || u.includes('offer') ? resp(200, []) : resp(200, {})) },
    'shop-miner-401': { page: 'shop', cred: 'fake-key', miner: 'm1', fetch: (u) => Promise.resolve(
        u.includes('monitoring/metrics') ? resp(200, { jobs: { total: 5 }, miners: { online: 2, total: 3 } })
        : u.includes('miners/') ? resp(401, {})
        : u.includes('sla') ? resp(404, {})
        : u.includes('gpu') ? resp(200, [])
        : u.includes('offer') ? resp(200, [])
        : resp(200, [])) },
    'shop-sla-404': { page: 'shop', miner: 'm1', fetch: (u) => Promise.resolve(
        u.includes('sla') ? resp(404, {}) : u.includes('gpu') || u.includes('offer') ? resp(200, []) : resp(200, { jobs: [] })) },
    'shop-gpu-shape': { page: 'shop', fetch: (u) => Promise.resolve(
        u.includes('gpu') ? resp(200, { wrong: true }) : u.includes('offer') ? resp(200, []) : resp(200, { jobs: [] })) },
    'shop-offers-500': { page: 'shop', fetch: (u) => Promise.resolve(
        u.includes('offer') ? resp(500, {}) : u.includes('gpu') ? resp(200, []) : resp(200, { jobs: [] })) },
};
globalThis.__n = 0;
const m = MODES[mode];
const store = { 'aitbc_credential': m.cred || '' };
const sandbox = {
    document,
    window: { location: { href: 'http://x/shop-dashboard.html', search: '' }, AITBC_CONFIG: { explorerApiUrl: '/explorer-api', chainId: 'c' } },
    location: { href: 'http://x/', search: '' },
    sessionStorage: { getItem: (k) => store[k] || '', setItem: (k, v) => { store[k] = v; }, removeItem: (k) => { delete store[k]; } },
    fetch: m.fetch, console: { log(){}, error(){}, warn(){} },
    setInterval(){}, setTimeout: (f) => f(), URL, URLSearchParams, Intl,
    Date, isNaN, Boolean, String, Number, Array, Object, JSON,
    aitbcFmt: { date: () => '2026-10-18 12:00', num: (n) => String(n) },
    aitbcCopyBtn: () => '', encodeURIComponent,
};
sandbox.window.sessionStorage = sandbox.sessionStorage;
if (m.page === 'cust') document.getElementById('cust-jobs-table');
if (m.page === 'shop') {
    document.getElementById('shop-jobs-table');
    if (m.miner) document.getElementById('shop-miner-input').value = m.miner;
}
(async () => {
    const vm = require('vm');
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox);
    // Each pass must finish before the next starts: await a real timer (the
    // driver's own setTimeout — inside the vm the sandboxed one is sync).
    for (let i = 0; i < (m.twice ? 2 : 1); i++) {
        for (const fn of handlers) { try { await fn(); } catch (e) {} }
        await new Promise((r) => setTimeout(r, 5));
    }
    await new Promise((r) => setTimeout(r, 5));
    const text = (o) => (o.textContent || '') + (o.children || []).map(text).join('|') + (o._html || '');
    const ids = ['cust-jobs-table', 'cust-wallets-table', 'cust-jobs-scope', 'cust-total-jobs', 'cred-status',
        'shop-jobs-table', 'shop-gpus-table', 'shop-offers-table', 'shop-wallets-table', 'shop-jobs-scope',
        'shop-stats-note', 'shop-earnings-note', 'shop-network-jobs', 'shop-network-released',
        'shop-miner-uptime', 'shop-earnings-total'];
    const out = {};
    ids.forEach((id) => { out[id] = text(document.getElementById(id)); });
    console.log('JSON:' + JSON.stringify(out));
})();
"""


def _run_dash_vm(mode: str) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("skipped: node not available for the vm fixture")
    r = subprocess.run(
        [node, "-e", _NODE_DASH_VM, str(WEBSITE / "dashboard.js"), mode],
        capture_output=True,
        text=True,
        timeout=30,
    )
    line = next((x for x in r.stdout.splitlines() if x.startswith("JSON:")), None)
    if not line:
        raise AssertionError(f"vm fixture produced no JSON for dashboard.js/{mode}: stderr={r.stderr[:400]}")
    return json.loads(line[5:])


class TestDashboardCustomerReads(unittest.TestCase):
    def test_ok_public_market_view(self) -> None:
        r = _run_dash_vm("cust-ok")
        self.assertIn("j1", r["cust-jobs-table"])
        self.assertIn("settlement failed", r["cust-jobs-table"])  # humanized
        self.assertNotIn("unavailable", r["cust-jobs-table"])
        self.assertEqual("market-wide", r["cust-jobs-scope"])

    def test_401_named_with_real_code_and_fallback_stated(self) -> None:
        r = _run_dash_vm("cust-401")
        self.assertIn("Credential rejected (HTTP 401)", r["cust-jobs-table"])
        self.assertIn("showing public network data", r["cust-jobs-table"])
        self.assertIn("Credential rejected (HTTP 401)", r["cred-status"])
        self.assertIn("j1", r["cust-jobs-table"])  # public fallback rendered

    def test_403_uses_the_real_code_not_hardcoded_401(self) -> None:
        r = _run_dash_vm("cust-403")
        self.assertIn("Credential rejected (HTTP 403)", r["cust-jobs-table"])
        self.assertNotIn("HTTP 401", r["cust-jobs-table"])

    def test_keyed_500_fallback_named_with_retry(self) -> None:
        r = _run_dash_vm("cust-keyed-500")
        self.assertIn("Couldn't load your view (HTTP 500)", r["cust-jobs-table"])
        self.assertIn("showing public network data instead", r["cust-jobs-table"])
        self.assertIn("Try again", r["cust-jobs-table"])

    def test_market_shape_failure_is_not_no_data(self) -> None:
        r = _run_dash_vm("cust-market-shape")
        self.assertIn("reply was not the expected shape", r["cust-jobs-table"])
        self.assertIn("Try again", r["cust-jobs-table"])
        self.assertNotIn("No data.", r["cust-jobs-table"])

    def test_market_500_named(self) -> None:
        r = _run_dash_vm("cust-market-500")
        self.assertIn("HTTP 500", r["cust-jobs-table"])
        self.assertIn("Try again", r["cust-jobs-table"])
        self.assertEqual("unavailable", r["cust-total-jobs"])

    def test_keyed_empty_is_honest_scoped_empty(self) -> None:
        """An approved credential returning [] shows 'your account' +
        No data — it must not silently fall back to the market feed."""
        r = _run_dash_vm("cust-keyed-empty")
        self.assertEqual("your account", r["cust-jobs-scope"])
        self.assertIn("No data.", r["cust-jobs-table"])
        self.assertNotIn("j1", r["cust-jobs-table"])

    def test_reload_failure_keeps_last_good_with_one_note(self) -> None:
        r = _run_dash_vm("cust-stale")
        self.assertIn("j1", r["cust-jobs-table"], "last-good rows must stay")
        self.assertIn("Stale — last good", r["cust-jobs-table"])
        self.assertIn("Try again", r["cust-jobs-table"])
        self.assertEqual(1, r["cust-jobs-table"].count("Stale — last good"))


class TestDashboardShopReads(unittest.TestCase):
    def test_public_ok_counts(self) -> None:
        r = _run_dash_vm("shop-public-ok")
        self.assertEqual("2 (latest)", r["shop-network-jobs"])
        self.assertEqual("1", r["shop-network-released"])
        self.assertNotIn("unavailable", r["shop-network-jobs"])

    def test_public_500_never_reads_as_zeros(self) -> None:
        r = _run_dash_vm("shop-public-500")
        self.assertEqual("unavailable", r["shop-network-jobs"])
        self.assertEqual("unavailable", r["shop-network-released"])
        self.assertIn("Jobs feed: HTTP 500", r["shop-stats-note"])

    def test_public_shape_failure_never_reads_as_zeros(self) -> None:
        r = _run_dash_vm("shop-public-shape")
        self.assertEqual("unavailable", r["shop-network-jobs"])
        self.assertIn("reply was not the expected shape", r["shop-stats-note"])

    def test_miner_401_named_at_the_panel(self) -> None:
        r = _run_dash_vm("shop-miner-401")
        self.assertIn("Credential rejected (HTTP 401)", r["shop-jobs-table"])
        # no Try again on a rejected credential — reload cannot help
        self.assertNotIn("Try again", r["shop-jobs-table"])
        self.assertIn("Earnings: Credential rejected (HTTP 401)", r["shop-earnings-note"])
        self.assertEqual("unavailable", r["shop-earnings-total"])

    def test_sla_404_is_not_no_sla_data(self) -> None:
        r = _run_dash_vm("shop-sla-404")
        self.assertEqual("unavailable", r["shop-miner-uptime"])
        self.assertIn("Miner uptime: HTTP 404", r["shop-earnings-note"])
        self.assertNotIn("no SLA data", r["shop-miner-uptime"])

    def test_gpu_shape_failure_named(self) -> None:
        r = _run_dash_vm("shop-gpu-shape")
        self.assertIn("reply was not the expected shape", r["shop-gpus-table"])
        self.assertIn("Try again", r["shop-gpus-table"])

    def test_offers_500_named(self) -> None:
        r = _run_dash_vm("shop-offers-500")
        self.assertIn("HTTP 500", r["shop-offers-table"])
        self.assertIn("Try again", r["shop-offers-table"])


if __name__ == "__main__":
    unittest.main()
