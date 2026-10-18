"""Dashboard address balances must load in parallel and stay honest.

loadAddressRows() reads one /rpc/account/<address> balance per address.
Awaiting each inside a loop makes the table take ~N round-trips; the reads
are independent, so they must be started together (Promise.all) and mapped
back in input order. readApi() never rejects — every failure resolves to
{ ok: false } — so Promise.all cannot fail-fast on a single bad read, and a
failed balance must render 'N/A', never zero.

The source-shape guard alone cannot catch a still-serial or mis-ordered
implementation, so the real dashboard.js is executed in a node VM with a
controllable fetch that records when each request starts and resolves.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

WEBSITE = Path(__file__).resolve().parents[2] / "website"


def _function_body(src: str, name: str) -> str:
    m = re.search(rf"async function {name}\(.*?\n\}}\n", src, re.S)
    assert m, f"{name} not found"
    return m.group(0)


_NODE_VM = r"""
const fs = require('fs');
const vm = require('vm');
const dashboardFile = process.argv[1];

// Fetch stub: every call is recorded and left pending until the driver
// resolves it, so the test can observe start order and resolve out of order.
const pending = [];            // { path, resolve }
const fetchLog = [];           // paths in start order
const fetch = (path) => new Promise((resolve) => {
    fetchLog.push(path);
    pending.push({ path, resolve });
});
const okJson = (data) => ({ ok: true, status: 200, json: async () => data });
const badRes = () => ({ ok: false, status: 500, json: async () => ({}) });

const document = {
    getElementById: () => null,
    createElement: () => ({ style: {}, setAttribute() {}, appendChild() {}, addEventListener() {}, classList: { add(){}, toggle(){} } }),
    addEventListener: () => {},   // DOMContentLoaded captured, never fired
    querySelector: () => null,
    querySelectorAll: () => [],
    body: { appendChild() {} },
    hidden: false,
};
const sandbox = {
    document,
    window: { addEventListener() {}, matchMedia: () => ({ matches: false }), scrollTo() {}, requestAnimationFrame() { return 0; }, scrollY: 0 },
    fetch,
    console: { log() {}, error() {}, warn() {} },
    setInterval: () => 0, setTimeout: () => 0, clearInterval() {}, clearTimeout() {},
    Intl, Date, Promise, JSON, Object, Array, String, Number, Boolean, Math, isNaN, parseFloat, parseInt, encodeURIComponent, URL, URLSearchParams,
    lucide: { createIcons() {} },
};
sandbox.window.AITBC_CONFIG = { explorerApiUrl: '/explorer-api', chainId: 'c' };
sandbox.AITBC_CONFIG = sandbox.window.AITBC_CONFIG;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(dashboardFile, 'utf8'), sandbox);

const tick = () => new Promise((r) => setImmediate(r));
const results = {};

async function scenario(name, topReply, entryCount, driver) {
    pending.length = 0; fetchLog.length = 0;
    const p = sandbox.loadAddressRows(entryCount);
    await tick(); await tick();
    // First call is the top-addresses read; resolve it.
    pending[0].resolve(okJson(topReply));
    await tick(); await tick(); await tick();
    const balanceCalls = pending.slice(1);
    const out = await driver(balanceCalls);
    const result = await p;
    results[name] = { balanceStarts: balanceCalls.length, fetchLog: fetchLog.slice(), interim: out, result };
}

(async () => {
    // 1. All balance reads start before any resolves (parallel), and rows keep
    //    input order even when replies land out of order.
    await scenario('parallel', { addresses: [
        { address: 'a1', transaction_count: 3 },
        { address: 'a2', transaction_count: 2 },
        { address: 'a3', transaction_count: 1 },
    ]}, 10, async (calls) => {
        const startedBeforeResolve = calls.length === 3;
        // Resolve last-to-first to prove order is positional, not temporal.
        calls[2].resolve(okJson({ balance: '300' }));
        await tick();
        calls[0].resolve(okJson({ balance: '100' }));
        calls[1].resolve(okJson({ balance: '200' }));
        return { startedBeforeResolve };
    });

    // 2. One failed balance read -> 'N/A' on that row only, others still render.
    await scenario('one-failed', { addresses: [
        { address: 'a1', transaction_count: 3 },
        { address: 'a2', transaction_count: 2 },
    ]}, 10, async (calls) => {
        calls[0].resolve(okJson({ balance: '100' }));
        calls[1].resolve(badRes());
    });

    // 3. Non-object entries are skipped, not rendered as junk rows.
    await scenario('non-object', { addresses: [null, 'junk', { address: 'a1', transaction_count: 1 }] }, 10, async (calls) => {
        if (calls[0]) calls[0].resolve(okJson({ balance: '100' }));
    });

    // 4. Empty list -> ok with zero rows, no balance reads at all.
    await scenario('empty', { addresses: [] }, 10, async () => null);

    // 5. Reply that is not a list -> shape error, no rows fabricated.
    await scenario('bad-shape', { unexpected: true }, 10, async () => null);

    // 6. Entry without an address makes no balance call and stays 'N/A'.
    await scenario('missing-address', { addresses: [
        { address: 'a1', transaction_count: 3 },
        { transaction_count: 9 },
    ]}, 10, async (calls) => {
        if (calls[0]) calls[0].resolve(okJson({ balance: '100' }));
    });

    console.log(JSON.stringify(results));
})().catch((e) => { console.error('DRIVER FAIL:', e && e.stack || e); process.exit(1); });
"""


class TestDashboardLoading(unittest.TestCase):
    def setUp(self) -> None:
        self.body = _function_body((WEBSITE / "dashboard.js").read_text(encoding="utf-8"), "loadAddressRows")

    def test_balances_fetched_with_promise_all(self) -> None:
        self.assertIn("Promise.all", self.body)

    def test_no_await_inside_a_loop(self) -> None:
        self.assertIsNone(
            re.search(r"\bfor\s*\([^\n]*\)\s*\{[^}]*\bawait\b", self.body),
            "await inside a for-loop serialises the balance reads",
        )


class TestLoadAddressRowsBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("node"):
            raise unittest.SkipTest("node not installed")
        out = subprocess.run(
            ["node", "-e", _NODE_VM, str(WEBSITE / "dashboard.js")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode != 0:
            raise AssertionError(f"vm failed: {out.stderr[:800]}")
        cls.results = json.loads(out.stdout.strip())

    def test_balance_reads_all_start_before_any_resolves(self) -> None:
        r = self.results["parallel"]
        self.assertEqual(3, r["balanceStarts"], "expected 3 balance reads")
        self.assertTrue(r["interim"]["startedBeforeResolve"], "balance reads started serially")
        self.assertTrue(all("/rpc/account/" in p for p in r["fetchLog"][1:]))

    def test_rows_keep_input_order(self) -> None:
        rows = self.results["parallel"]["result"]["rows"]
        self.assertEqual(["a1", "a2", "a3"], [row["address"] for row in rows])
        self.assertEqual([row["txs"] for row in rows], [3, 2, 1])

    def test_failed_balance_is_na_not_zero(self) -> None:
        r = self.results["one-failed"]
        self.assertTrue(r["result"]["ok"])
        rows = r["result"]["rows"]
        self.assertEqual("N/A", rows[1]["balance"], "failed balance must render N/A")
        self.assertNotEqual("0", rows[1]["balance"], "failed balance must never read as zero")
        self.assertNotEqual("N/A", rows[0]["balance"], "successful balance lost its value")

    def test_non_object_entries_are_skipped(self) -> None:
        r = self.results["non-object"]
        self.assertTrue(r["result"]["ok"])
        rows = r["result"]["rows"]
        self.assertEqual(1, len(rows), "null/string entries must not become rows")
        self.assertEqual("a1", rows[0]["address"])
        self.assertEqual(1, r["balanceStarts"], "skipped entries must not fetch balances")

    def test_empty_list_returns_ok_no_rows(self) -> None:
        r = self.results["empty"]
        self.assertTrue(r["result"]["ok"])
        self.assertEqual([], r["result"]["rows"])
        self.assertEqual(0, r["balanceStarts"], "empty list must not fetch")

    def test_unexpected_reply_shape_is_an_error(self) -> None:
        r = self.results["bad-shape"]
        self.assertFalse(r["result"]["ok"])
        self.assertEqual("reply was not the expected shape", r["result"]["err"])

    def test_missing_address_makes_no_balance_call(self) -> None:
        r = self.results["missing-address"]
        self.assertTrue(r["result"]["ok"])
        rows = r["result"]["rows"]
        self.assertEqual(2, len(rows))
        self.assertEqual("N/A", rows[1]["address"])
        self.assertEqual("N/A", rows[1]["balance"])
        self.assertEqual(1, r["balanceStarts"], "N/A address must not trigger a fetch")


if __name__ == "__main__":
    unittest.main()
