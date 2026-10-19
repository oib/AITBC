"""WEB-STATES-1 — browser-layer tests for the three data-dependent states
strict CSP and the 30 s chart rebuild can break, on the local fixture server
under the production CSP header.

Covers what the layout suite never exercises:

1. Chart hide + forced rebuild: collapse gives chips; hiding a type must
   survive the 30 s ``refreshData`` rebuild (``hiddenTypes`` + ``update()``),
   the NEW chart instance must report the dataset invisible, and the canvas
   pixels must differ from the all-visible render and match the hidden render.
   The rebuild is forced with ``Emulation.setVirtualTimePolicy`` — no wall
   time is spent waiting for the interval.

2. Search click-through: tx and block rows carry ``data-href``; clicking
   must land on ``/tx.html?hash=`` / ``/block.html?height=`` and the landing
   page must render its type cell humanized.

3. Exchange deposit states: ``/v1/bridge/status`` on / disabled / error must
   leave the form enabled, inert, and inert-with-a-failure-note. A broken
   state must never present a bare ``0`` or empty value as healthy.

Every session injects a ``securitypolicyviolation`` recorder and asserts
zero violations plus zero security-source Log entries. Local fixture data
only — never the live site, no real address, no credential.
"""

import asyncio
import copy
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_website_layout_375 as base

WEBSITE = base.WEBSITE
_BROWSER = base._find_browser()
_HAS_WS = base._websockets_available()


# Mirrors base._STUB_JS but takes the fixture map — a ``{"__status": N,
# "body": ...}`` value replies with that status (exchange 500 case).
def _stub_js(fixtures: dict) -> str:
    return f"""
window.__csp = [];
document.addEventListener('securitypolicyviolation', e =>
  window.__csp.push((e.violatedDirective || '?') + '|' + (e.blockedURI || '?')));
window.fetch = ((u, opts) => {{
  let p = new URL(u, location.origin).pathname;
  p = p.replace(/^\\/explorer-api/, '');
  const F = {json.dumps(fixtures)};
  const keys = Object.keys(F).sort((a, b) => b.length - a.length);
  for (const k of keys) {{
    if (p === k || p.startsWith(k)) {{
      const v = F[k];
      if (v && typeof v === 'object' && '__status' in v) {{
        return Promise.resolve(new Response(JSON.stringify(v.body || {{}}),
          {{status: v.__status, headers: {{'Content-Type': 'application/json'}}}}));
      }}
      return Promise.resolve(new Response(JSON.stringify(v),
        {{status: 200, headers: {{'Content-Type': 'application/json'}}}}));
    }}
  }}
  return Promise.resolve(new Response('{{}}', {{status: 200,
    headers: {{'Content-Type': 'application/json'}}}}));
}});
"""


def _fixtures(**overrides):
    f = copy.deepcopy(base._FIXTURES)
    f.update(overrides)
    return f


def _security_log_entries(events: list[dict]) -> list[str]:
    bad = []
    for ev in events:
        if ev.get("method") != "Log.entryAdded":
            continue
        e = ev["params"]["entry"]
        if e.get("source") == "security" or "Refused" in e.get("text", ""):
            bad.append(e.get("text", ""))
    return bad


async def _wait_truthy(send, expr: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        res = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        if res.get("result", {}).get("result", {}).get("value"):
            return
        await asyncio.sleep(0.3)


async def _eval_step(send, expr: str, results: list, last: dict) -> dict:
    res = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    val = res.get("result", {}).get("result", {}).get("value")
    if val is None:
        return last
    parsed = json.loads(val) if isinstance(val, str) else val
    results.append(parsed if not isinstance(parsed, dict) else dict(parsed))
    return parsed


async def _cdp_steps(ws_url: str, url: str, stub_js: str, steps: list, width: int = 375) -> dict:
    """One CDP session running sequential steps on a FRESH tab per call —
    virtual-time overrides and init scripts must not bleed across sessions
    (a leftover setVirtualTimePolicy froze every later page load). Step forms:

    - ``("eval", expr)``      — Runtime.evaluate, last JSON result kept
    - ``("sleep", seconds)``  — real-time pause
    - ``("vt", ms)``          — Emulation.setVirtualTimePolicy budget advance
    - ``("wait", expr)``      — poll every 0.3 s (max 10 s) until truthy;
      for readiness after async rendering instead of racing a fixed sleep
    """
    import websockets

    events: list[dict] = []
    last: dict = {}
    results: list = []
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        mid = [0]

        async def send(method: str, params: dict | None = None, session: str | None = None) -> dict:
            counter = mid if session is None else session_ids
            if session is not None:
                counter[0] += 1
                await ws.send(json.dumps({"id": counter[0], "method": method, "params": params or {}, "sessionId": session}))
                while True:
                    msg = json.loads(await ws.recv())
                    if "id" not in msg:
                        events.append(msg)
                        continue
                    if msg.get("id") == counter[0]:
                        if "error" in msg:
                            raise AssertionError(f"CDP {method}: {msg['error']}")
                        return msg
            return await base._cdp_send(ws, mid, events, method, params)

        session_ids = [10000]
        target = await send("Target.createTarget", {"url": "about:blank"})
        target_id = target["result"]["targetId"]
        attached = await send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session = attached["result"]["sessionId"]

        try:
            await send("Page.enable", session=session)
            await send("Runtime.enable", session=session)
            await send("Log.enable", session=session)
            await send(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": 800, "deviceScaleFactor": 1, "mobile": False},
                session=session,
            )
            await send("Page.addScriptToEvaluateOnNewDocument", {"source": stub_js}, session=session)
            await send("Page.navigate", {"url": url}, session=session)
            await asyncio.sleep(2.5)

            async def ssend(method: str, params: dict) -> dict:
                return await send(method, params, session=session)

            for kind, arg in steps:
                if kind == "sleep":
                    await asyncio.sleep(arg)
                elif kind == "vt":
                    await ssend(
                        "Emulation.setVirtualTimePolicy",
                        {"policy": "pauseIfNetworkFetchesPending", "budget": arg},
                    )
                    await asyncio.sleep(4)
                elif kind == "wait":
                    await _wait_truthy(ssend, arg)
                else:
                    last = await _eval_step(ssend, arg, results, last)
            await base._cdp_drain(ws, events)
        finally:
            try:
                await send("Target.closeTarget", {"targetId": target_id})
            except Exception:  # noqa: BLE001
                pass
    last["_steps"] = results
    last["_events"] = events
    return last


@unittest.skipUnless(_BROWSER and _HAS_WS, "skipped: no browser (chromium on PATH) or no websockets package")
class TestStatesBrowser(unittest.TestCase):
    """Chart rebuild, search click-through, exchange deposit states — under
    the production CSP, zero violations allowed."""

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

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}/{path}"

    def _run(self, path: str, stub_js: str, steps: list, width: int = 375) -> dict:
        r = asyncio.run(_cdp_steps(self.ws_url, self._url(path), stub_js, steps, width))
        self.assertEqual([], _security_log_entries(r["_events"]), "CSP/security Log entries")
        return r

    # ── 1. Chart: hidden type survives the 30 s rebuild ─────────────────

    def test_chart_hidden_type_survives_rebuild(self) -> None:
        stub = _stub_js(_fixtures())
        steps = [
            ("wait", "!!window.activityChartInstance"),
            (
                "eval",
                """(() => {
  const c = window.activityChartInstance;
  if (!c) return JSON.stringify({err: 'no chart'});
  c.options.animation = false;      // deterministic paint
  c.update('none');
  window.__chart0 = c;
  window.__pxFull = document.getElementById('activity-chart').toDataURL();
  return JSON.stringify({ok: true, chips: document.querySelectorAll('#legend-chips button').length});
})()""",
            ),
            (
                "eval",
                """(() => {
  const chip = document.querySelector('#legend-chips button');
  if (!chip) return JSON.stringify({err: 'no chips'});
  chip.click();
  const c = window.activityChartInstance;
  c.update('none');
  window.__pxHidden = document.getElementById('activity-chart').toDataURL();
  return JSON.stringify({vis0: c.isDatasetVisible(0),
    pressed: chip.getAttribute('aria-pressed')});
})()""",
            ),
            ("vt", 35000),  # fast-forward past the 30 s refreshData interval
            ("wait", "window.activityChartInstance && window.activityChartInstance !== window.__chart0"),
            (
                "eval",
                """(() => {
  const c = window.activityChartInstance;
  if (!c) return JSON.stringify({err: 'no chart after rebuild'});
  c.options.animation = false;
  c.update('none');
  const px = document.getElementById('activity-chart').toDataURL();
  const chip = document.querySelector('#legend-chips button');
  return JSON.stringify({
    newInstance: c !== window.__chart0,
    vis0: c.isDatasetVisible(0),
    chipPressed: chip ? chip.getAttribute('aria-pressed') : null,
    pxEqHidden: px === window.__pxHidden,
    pxEqFull: px === window.__pxFull,
    csp: window.__csp,
  });
})()""",
            ),
        ]
        r = self._run("explorer.html", stub, steps)
        self.assertNotIn("err", r, r.get("err"))
        self.assertTrue(r["newInstance"], "rebuild must produce a new chart instance")
        self.assertFalse(r["vis0"], "hidden type visible again after rebuild")
        self.assertEqual("false", r["chipPressed"], "re-rendered chip lost its off state")
        self.assertTrue(r["pxEqHidden"], "repaint differs from the hidden render")
        self.assertFalse(r["pxEqFull"], "hidden render equals the all-visible render")
        self.assertEqual([], r["csp"], f"CSP violations: {r['csp']}")

    # ── 2. Search: tx and block rows land on the right pages ────────────

    _SEARCH_TX_FIXTURE = {
        "transactions": [
            {
                "tx_hash": "0x" + "aa" * 32,
                "type": "BRIDGE_LOCK",
                "sender": "0x" + "cd" * 20,
                "recipient": "0x" + "ef" * 20,
                "value": "5",
                "block_height": 48690,
                "timestamp": "2026-10-15T21:00:00Z",
            }
        ]
    }
    _SEARCH_BLOCKS_FIXTURE = {
        "blocks": [
            {
                "height": 48691,
                "hash": "0x" + "ab" * 32,
                "txCount": 1,
                "proposer": "0x" + "ef" * 20,
                "timestamp": "2026-10-15T21:00:00Z",
            }
        ]
    }

    def test_search_click_tx_lands_on_tx_page(self) -> None:
        stub = _stub_js(
            _fixtures(
                **{
                    "/api/transactions/search": self._SEARCH_TX_FIXTURE,
                    "/api/transactions/": {
                        "tx_hash": "0x" + "aa" * 32,
                        "hash": "0x" + "aa" * 32,
                        "type": "BRIDGE_LOCK",
                        "value": "5",
                        "fee": "0.01",
                        "nonce": 7,
                        "created_at": "2026-10-15T21:00:00Z",
                        "status": "confirmed",
                        "sender": "0x" + "cd" * 20,
                        "recipient": "0x" + "ef" * 20,
                        "block_height": 48690,
                    },
                }
            )
        )
        steps = [
            (
                "eval",
                """(() => {
  const row = document.querySelector('#txs-list [data-href]');
  if (!row) return JSON.stringify({err: 'no tx row'});
  const href = row.getAttribute('data-href');
  row.click();
  return JSON.stringify({href});
})()""",
            ),
            ("wait", "location.pathname === '/tx.html'"),
            ("wait", "(document.getElementById('tx-type-badge') || {textContent: ''}).textContent === 'Bridge lock'"),
            (
                "eval",
                """(() => {
  const u = new URL(location.href);
  const badge = document.getElementById('tx-type-badge');
  const typeCell = [...document.querySelectorAll('td')].map(t => t.textContent)
    .find(t => /Bridge lock/.test(t));
  return JSON.stringify({path: u.pathname, hash: u.searchParams.get('hash'),
    badge: badge ? badge.textContent : null,
    typeCell: typeCell || null, csp: window.__csp});
})()""",
            ),
        ]
        r = self._run("search.html?query=bridge", stub, steps)
        self.assertNotIn("err", r, r.get("err"))
        self.assertEqual("/tx.html", r["path"], "tx row did not land on tx.html")
        self.assertEqual("0x" + "aa" * 32, r["hash"], "landing URL lost the tx hash")
        self.assertEqual("Bridge lock", r["badge"], "tx page type badge not humanized")
        self.assertIsNotNone(r["typeCell"], "tx page type cell not humanized")
        self.assertEqual([], r["csp"], f"CSP violations: {r['csp']}")

    def test_search_click_block_lands_on_block_page(self) -> None:
        stub = _stub_js(_fixtures(**{"/api/blocks/by-address/": self._SEARCH_BLOCKS_FIXTURE}))
        steps = [
            (
                "eval",
                """(() => {
  const row = document.querySelector('#blocks-list [data-href]');
  if (!row) return JSON.stringify({err: 'no block row'});
  const href = row.getAttribute('data-href');
  row.click();
  return JSON.stringify({href});
})()""",
            ),
            ("wait", "location.pathname === '/block.html'"),
            (
                "wait",
                "document.getElementById('block-kind-badge') && document.getElementById('block-kind-badge').textContent.trim() !== ''",
            ),
            (
                "eval",
                """(() => {
  const u = new URL(location.href);
  const badge = document.getElementById('block-kind-badge');
  return JSON.stringify({path: u.pathname, height: u.searchParams.get('height'),
    badge: badge ? badge.textContent : null, csp: window.__csp});
})()""",
            ),
        ]
        r = self._run("search.html?query=bridge", stub, steps)
        self.assertNotIn("err", r, r.get("err"))
        self.assertEqual("/block.html", r["path"], "block row did not land on block.html")
        self.assertEqual("48691", r["height"], "landing URL lost the block height")
        self.assertEqual("Block", r["badge"], "block page badge not humanized")
        self.assertEqual([], r["csp"], f"CSP violations: {r['csp']}")

    # ── 3. Exchange deposit: bridge on / off / error states ──────────────

    _STATUS_READY = {
        "status": "ready",
        "enabled": True,
        "deposit_address": "0x" + "de" * 20,
        "min_deposit": "0.01",
        "fee_rate": 0.02,
        "network": "fixture-net",
    }
    _DEPOSIT_READY = {
        "status": "ready",
        "estimate": {
            "estimated_ait_amount": "1234.5",
            "ait_recipient": "0x" + "aa" * 20,
            "eth_amount": "0.5",
            "fee_eth": "0.01",
            "net_eth": "0.49",
            "eth_usd_price": "-",
            "ait_usd_price": "-",
        },
        "instructions": {
            "send_eth_to": "0x" + "de" * 20,
            "amount_eth": "0.5",
            "transaction_data_hex": "0xdead",
            "min_deposit": "0.01",
        },
    }

    _FORM_STATE_JS = """(() => {
  const ids = ['eth-amount', 'ait-address', 'calculate-deposit-btn'];
  const note = document.getElementById('bridge-offline-note');
  const retry = document.getElementById('bridge-retry-btn');
  const status = document.getElementById('bridge-status-text');
  const shown = el => !!el && !el.hidden && getComputedStyle(el).display !== 'none';
  return JSON.stringify({
    disabled: ids.map(i => document.getElementById(i).disabled),
    noteShown: shown(note), noteText: note ? note.textContent : null,
    retryShown: shown(retry),
    statusText: status ? status.textContent : null,
    depositAddr: (document.getElementById('deposit-address') || {}).textContent,
    csp: window.__csp,
  });
})()"""

    def _bridge_run(self, status_fixture: dict, extra_steps: list | None = None) -> dict:
        stub = _stub_js(
            _fixtures(
                **{
                    "/v1/bridge/status": status_fixture,
                    "/v1/bridge/deposit": self._DEPOSIT_READY,
                }
            )
        )
        steps = [
            ("wait", "(document.getElementById('bridge-status-text') || {textContent: ''}).textContent !== 'Loading...'"),
            ("eval", self._FORM_STATE_JS),
        ] + (extra_steps or [])
        return self._run("exchange.html", stub, steps)

    def test_deposit_form_enabled_when_bridge_ready(self) -> None:
        r = self._bridge_run(self._STATUS_READY)
        self.assertEqual([False, False, False], r["disabled"], "form inert while bridge proven on")
        self.assertFalse(r["noteShown"], "offline note shown while bridge on")
        self.assertFalse(r["retryShown"], "retry shown while bridge on")
        self.assertEqual("0x" + "de" * 20, r["depositAddr"], "deposit address not rendered")
        self.assertEqual([], r["csp"], f"CSP violations: {r['csp']}")

    def test_deposit_calculator_returns_estimate(self) -> None:
        steps = [
            (
                "eval",
                """(() => {
  document.getElementById('eth-amount').value = '0.5';
  document.getElementById('ait-address').value = '0x' + 'aa'.repeat(20);
  document.getElementById('calculate-deposit-btn').click();
  return JSON.stringify({clicked: true});
})()""",
            ),
            (
                "wait",
                "!document.getElementById('deposit-estimate').hidden || !document.getElementById('deposit-error').hidden",
            ),
            (
                "eval",
                """(() => {
  const est = document.getElementById('deposit-estimate');
  const err = document.getElementById('deposit-error');
  const shown = el => !!el && !el.hidden && getComputedStyle(el).display !== 'none';
  return JSON.stringify({
    estShown: shown(est), errShown: shown(err),
    errText: err ? err.textContent : null,
    ait: document.getElementById('estimated-ait').textContent,
    addr: document.getElementById('deposit-address').textContent,
    instr: document.getElementById('deposit-instructions') ? !document.getElementById('deposit-instructions').hidden : null,
    csp: window.__csp,
  });
})()""",
            ),
        ]
        r = self._bridge_run(self._STATUS_READY, steps)
        self.assertTrue(r["estShown"], "estimate panel hidden after a valid deposit calc")
        self.assertFalse(r["errShown"], f"error shown on valid calc: {r['errText']}")
        self.assertEqual("1234.5", r["ait"], "calculated AIT amount wrong or empty")
        self.assertEqual("0x" + "de" * 20, r["addr"], "deposit instruction address wrong or empty")
        self.assertEqual([], r["csp"], f"CSP violations: {r['csp']}")

    def test_deposit_form_inert_when_bridge_disabled(self) -> None:
        r = self._bridge_run({"status": "maintenance", "enabled": False, "message": "deposits disabled for upgrade"})
        self.assertEqual([True, True, True], r["disabled"], "form live while bridge disabled")
        self.assertTrue(r["noteShown"], "offline note hidden while bridge disabled")
        self.assertIn("disabled", r["noteText"] or "", "offline note carries no reason")
        self.assertTrue(r["retryShown"], "no retry offered while bridge disabled")
        self.assertNotIn(r["statusText"], ("", None), "status text empty — bare blank state")
        self.assertEqual([], r["csp"], f"CSP violations: {r['csp']}")

    def test_deposit_form_inert_when_bridge_status_errors(self) -> None:
        r = self._bridge_run({"__status": 500, "body": {}})
        self.assertEqual([True, True, True], r["disabled"], "form live after a 500 status")
        self.assertTrue(r["noteShown"], "offline note hidden after a 500 status")
        self.assertIn("HTTP 500", r["statusText"] or "", "500 not surfaced in the status text")
        self.assertTrue(r["retryShown"], "no retry offered after a 500 status")
        # The trust rule: a failed state must never look like a healthy 0.
        self.assertNotIn((r["statusText"] or "").strip(), ("", "0", "unknown — "), "bare/empty status after 500")
        self.assertEqual([], r["csp"], f"CSP violations: {r['csp']}")


if __name__ == "__main__":
    unittest.main()
