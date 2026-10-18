"""WEB-TZ-1: zone labels on local-clock timestamps — driven through a node
vm under three TZ environments.

The shared helper aitbcFmt.zone (status.js) labels the viewer's local zone
("GMT+2"/"CEST"/"EDT", engine-dependent, UTC±n fallback). explorer.js's
block card must carry that real label instead of the literal " UTC" that
was two hours wrong for CEST viewers; N/A gets no zone word. Assertions
check consistency between the rendered hour and the rendered label — not
a hard-coded zone word, since Intl short names differ by engine.
"""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

WEBSITE = Path(__file__).resolve().parents[2] / "website"
FIXED = "2026-10-18T12:00:00Z"  # 14:00 CEST, 12:00 UTC, 08:00 EDT
FIXED_SECS = 1792324800  # same instant as epoch seconds (number path)

_NODE_VM = r"""
const fs = require('fs');
const vm = require('vm');
const [statusFile, explorerFile, instant, secs] = process.argv.slice(1);
const els = {};
function el(tag) {
    const self = {
        style: {}, _html: '', children: [], className: '', _listeners: {},
        _parent: null, value: '', dataset: {}, hidden: false,
        classList: {
            add(c){ self.className = (self.className + ' ' + c).trim(); },
            remove(){},
            toggle(){},
            contains(c){ return (self.className || '').split(/\s+/).includes(c); },
        },
        set innerHTML(v){ self._html = v; self.children = []; },
        get innerHTML(){ return self._html; },
        set textContent(v){ self._text = v; },
        get textContent(){ return self._text || ''; },
        setAttribute(){}, getAttribute(){ return null; },
        appendChild(c){ c._parent = self; self.children.push(c); return c; },
        addEventListener(){},
    };
    return self;
}
const document = {
    getElementById: (id) => els[id] || (els[id] = el(id)),
    createElement: (t) => el(t),
    createDocumentFragment: () => el('frag'),
    addEventListener(){},
    querySelector: () => null,
    querySelectorAll: () => [],
    body: el('body'),
    hidden: false,
};
const sandbox = {
    document,
    window: { addEventListener() {}, scrollTo() {}, requestAnimationFrame(f) { return 0; }, scrollY: 0 },
    fetch: () => Promise.reject(new Error('no fetch in tz fixture')),
    console: { log() {}, error() {}, warn() {} },
    setInterval() {}, setTimeout: (f) => 0, clearInterval() {}, clearTimeout() {},
    URL, URLSearchParams, Intl, encodeURIComponent,
    Date, isNaN, Boolean, String, Number, Array, Object, JSON, Promise, Math, parseFloat, parseInt,
    aitbcCopyBtn: () => '',
    lucide: { createIcons() {} },
};
sandbox.window.AITBC_CONFIG = { explorerApiUrl: '/explorer-api', chainId: 'c' };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(statusFile, 'utf8'), sandbox);
// In a browser, `window.aitbcFmt` is the global `aitbcFmt`; in the vm the
// plain `window` object doesn't proxy globals, so wire it by hand.
sandbox.aitbcFmt = sandbox.window.aitbcFmt;
vm.runInContext(fs.readFileSync(explorerFile, 'utf8'), sandbox);
const cell = (html) => {
    const m = html.match(/Timestamp<\/th><td>([^<]*)<\/td>/);
    return m ? m[1] : 'NO-CELL';
};
const out = {
    date: sandbox.window.aitbcFmt.date(instant),
    zone: sandbox.window.aitbcFmt.zone(instant),
    tzOffsetMin: new Date(instant).getTimezoneOffset(),
    cardStr: cell(sandbox.renderBlockCard({ timestamp: instant })),
    cardNum: cell(sandbox.renderBlockCard({ timestamp: Number(secs) })),
    cardNone: cell(sandbox.renderBlockCard({})),
    cardBad: cell(sandbox.renderBlockCard({ timestamp: 'not-a-date' })),
};
console.log('JSON:' + JSON.stringify(out));
"""


def _run_vm(tz: str) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("skipped: node not available for the vm fixture")
    env = dict(os.environ, TZ=tz)
    r = subprocess.run(
        [node, "-e", _NODE_VM, str(WEBSITE / "status.js"), str(WEBSITE / "explorer.js"), FIXED, str(FIXED_SECS)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    line = next((x for x in r.stdout.splitlines() if x.startswith("JSON:")), None)
    if not line:
        raise AssertionError(f"vm produced no JSON\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return json.loads(line[5:])


def _hour_offset(stamp: str) -> int:
    """Offset (hours) the rendered local stamp shows vs the UTC instant."""
    hh = int(stamp.split(" ")[1].split(":")[0])
    off = hh - 12
    if off > 12:
        off -= 24
    if off < -12:
        off += 24
    return off


class TestZoneLabel(unittest.TestCase):
    def _check(self, tz: str) -> dict:
        r = _run_vm(tz)
        zone, stamp = r["zone"], r["date"]
        # The rendered hour and the engine's own offset must agree.
        self.assertEqual(-r["tzOffsetMin"] // 60, _hour_offset(stamp), f"{tz}: stamp {stamp} inconsistent with offset")
        # Label: numeric UTC/GMT±n must equal the offset; an alphabetic
        # short name (CEST, EDT…) is an honest engine-dependent name.
        import re

        m = re.fullmatch(r"(?:UTC|GMT)([+-]\d+(?:\.\d+)?)", zone)
        if m:
            self.assertAlmostEqual(float(m.group(1)), -r["tzOffsetMin"] / 60, msg=f"{tz}: label {zone} wrong for offset")
        else:
            self.assertRegex(zone, r"^[A-Z]{2,6}$", f"{tz}: unexpected label {zone!r}")
        return r

    def test_zone_label_consistent_in_three_timezones(self) -> None:
        for tz in ("Europe/Berlin", "UTC", "America/New_York"):
            with self.subTest(tz=tz):
                self._check(tz)

    def test_block_card_carries_real_zone_not_literal_utc(self) -> None:
        r = _run_vm("Europe/Berlin")
        self.assertEqual(f"{r['date']} {r['zone']}", r["cardStr"], "string timestamp must render '<local> <zone>'")
        self.assertNotRegex(r["cardStr"], r" UTC$", "bare ' UTC' after a local stamp is the bug")
        self.assertEqual(r["cardStr"], r["cardNum"], "number (seconds) timestamp takes the same path")

    def test_utc_viewer_gets_honest_utc(self) -> None:
        r = _run_vm("UTC")
        # In a real UTC zone the label IS honest — emitted by zone(), not
        # by a literal suffix.
        self.assertEqual(f"{r['date']} {r['zone']}", r["cardStr"])

    def test_no_timestamp_and_unparseable_show_bare_na(self) -> None:
        r = _run_vm("Europe/Berlin")
        self.assertEqual("N/A", r["cardNone"], "no timestamp → N/A, no zone word")
        self.assertEqual("N/A", r["cardBad"], "unparseable timestamp → N/A, not '- UTC'")

    def test_source_pin_no_literal_utc_suffix(self) -> None:
        js = (WEBSITE / "explorer.js").read_text(encoding="utf-8")
        self.assertNotIn("} UTC", js, "literal ' UTC' suffix after a formatted value")
        self.assertNotIn("' UTC'", js)
        self.assertNotIn('" UTC"', js)

    def test_zone_helper_shared_not_duplicated(self) -> None:
        status = (WEBSITE / "status.js").read_text(encoding="utf-8")
        explorer = (WEBSITE / "explorer.js").read_text(encoding="utf-8")
        dashboard = (WEBSITE / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("zone: function", status, "aitbcFmt.zone is the shared home")
        self.assertNotIn("timeZoneName", explorer, "no second Intl copy in explorer.js")
        self.assertIn("aitbcFmt.zone(d)", dashboard, "dashboard tzLabel calls the shared helper")


if __name__ == "__main__":
    unittest.main()
