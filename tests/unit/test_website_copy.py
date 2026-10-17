"""WEB-FIX-2 — shared copy control guard, in two layers.

``TestCopyControlStatic`` runs everywhere, offline: there is exactly one
copy implementation (``website/copy.js``), every page that emits a copy
control loads it deferred and stamped, every inventoried truncation site
carries the control, no legacy ``copyValue``/``copyToClipboard``/
``copyAddress`` machinery survives, and the markup/CSS contracts are
pinned.

``TestCopyControlBrowser`` is the behavioural layer: a real Chromium via
CDP clicks a ``.copy-btn`` on a fixture-populated page and asserts the
*full* value reaches ``navigator.clipboard.writeText``, the outcome is
announced in the shared ``#sr-announcer`` region, and the failure path
surfaces "press Ctrl+C" instead of failing silently. It detects the
browser the same way as the 375px layout guard and **skips cleanly with
"no browser" otherwise** — so it is never enforced in CI until a browser
host exists.
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
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"
STYLE = WEBSITE / "style.css"
COPY_JS = WEBSITE / "copy.js"

# Pages whose markup/JS can emit a copy control — each must load copy.js.
PAGES_WITH_COPY = [
    "index.html",
    "explorer.html",
    "block.html",
    "tx.html",
    "search.html",
    "bridges.html",
    "marketplace.html",
    "exchange.html",
    "customer-dashboard.html",
    "shop-dashboard.html",
    "messages.html",
]

# Inventoried truncation sites — (source file, regex that must carry an
# aitbcCopyBtn call). Copying a truncated value is the whole point of the
# control, so each truncation emit site is pinned individually.
TRUNCATION_SITES = [
    # explorer.js — the block-hash row in renderBlockCard. The search-result
    # sites were removed with the dead search functions (WEB-DEADCODE-1).
    ("explorer.js", r"aitbcCopyBtn\(blockHash, 'block hash'\)"),
    # detail pages — inline emitters inside <script> blocks.
    ("block.html", r"aitbcCopyBtn\(data\.hash \|\| '', 'block hash'\)"),
    ("block.html", r"aitbcCopyBtn\(data\.proposer \|\| '', 'proposer address'\)"),
    ("block.html", r"aitbcCopyBtn\(data\.stateRoot \|\| '', 'state root'\)"),
    ("block.html", r"aitbcCopyBtn\(tx\.tx_hash, 'transaction hash'\)"),
    ("tx.html", r"aitbcCopyBtn\(data\.hash, 'transaction hash'\)"),
    ("tx.html", r"aitbcCopyBtn\(data\.from \|\| data\.sender \|\| '', 'sender address'\)"),
    ("tx.html", r"aitbcCopyBtn\(data\.to \|\| data\.recipient \|\| '', 'recipient address'\)"),
    ("search.html", r"aitbcCopyBtn\(b\.hash \|\| '', 'block hash'\)"),
    ("search.html", r"aitbcCopyBtn\(tx\.tx_hash \|\| '', 'transaction hash'\)"),
    # join flow — the peer key is shown once and must be storable.
    ("index.js", r"aitbcCopyBtn\(data\.peer_key, 'peer key'\)"),
    # bridges — truncated sender/recipient and the transfer-id link.
    ("bridges.js", r"aitbcCopyBtn\(a, 'address'\)"),
    ("bridges.js", r"aitbcCopyBtn\(d\.transfer_id, 'transaction hash'\)"),
    # marketplace — truncated tx/block hash links.
    ("marketplace.js", r"aitbcCopyBtn\(hash, 'transaction hash'\)"),
    ("marketplace.js", r"aitbcCopyBtn\(hash, 'block hash'\)"),
    # dashboards — settlement tx link and escrow contract id.
    ("dashboard.js", r"aitbcCopyBtn\(hash, 'transaction hash'\)"),
    ("dashboard.js", r"aitbcCopyBtn\(job\.escrow_contract_id, 'escrow contract id'\)"),
    # exchange — deposit tracking rows.
    ("exchange.js", r"aitbcCopyBtn\(deposit\.ait_tx_hash, 'transaction hash'\)"),
    ("exchange.js", r"aitbcCopyBtn\(deposit\.eth_from_address, 'sender address'\)"),
    # exchange.html — static controls resolved from live element text.
    ("exchange.html", r'data-copy-from="deposit-address"'),
    ("exchange.html", r'data-copy-from="tx-data-hex"'),
    ("exchange.html", r'data-copy-from="eth-tx-hash"'),
    # messages — author address and tx hash per rendered post.
    ("messages.js", r"aitbcCopyBtn\(author, 'author address'\)"),
    ("messages.js", r"aitbcCopyBtn\(m\.tx_hash, 'transaction hash'\)"),
]

# Legacy implementations the shared control retires — none may survive.
LEGACY = [
    "copyValue",
    "copyToClipboard",
    "copyAddress",
    "copyTxDataHex",
    "announceCopy",
]


def _site_src(name: str) -> str:
    return (WEBSITE / name).read_text(encoding="utf-8")


class TestFaucetAnnouncementCopy(unittest.TestCase):
    """WEB-FAUCET-NOTE-1: the paused-faucet notice must name the real route.

    `coin-requests/*/execute` is a wildcard placeholder that resolves to 404 —
    the real route takes no path parameter. The 503 pause claim itself stays:
    verified live on 17 Oct 2026 (GENESIS_PRIVATE_KEY absent on hub).
    """

    def test_announcement_names_real_execute_route(self) -> None:
        src = _site_src("follower-api-key-announcement.html")
        self.assertNotIn("coin-requests/*/execute", src)
        self.assertIn("coin-requests/execute", src)
        self.assertIn("paused", src.lower())


class TestExchangeFaucetCard(unittest.TestCase):
    """EXCH-FAUCET-CARD-1: the Early Adopter card must not promise automatic
    payout while the faucet is paused (503 since 2026-09-09). Scoped to the
    card: the ETH→AIT deposit flow legitimately says "automatically"."""

    def test_card_states_pause_not_automatic(self) -> None:
        src = _site_src("exchange.html")
        card = src[src.index("Early Adopter Program") : src.index("Value Model Documentation")]
        self.assertNotIn("automatically", card)
        self.assertIn("paused", card.lower())


class TestExchangeBridgeBanner(unittest.TestCase):
    """EXCH-FAILSTATES-1: the page-level bridge banner must exist and its
    render path must cover all four states — green only on a proven reply."""

    def test_banner_element_and_states(self) -> None:
        html = _site_src("exchange.html")
        self.assertIn('id="bridge-health"', html)
        self.assertIn('role="status"', html)
        js = _site_src("exchange.js")
        for cls in ("is-loading", "is-healthy", "is-attention", "is-unknown"):
            self.assertIn(cls, js)
        self.assertIn("setInterval(fetchBridgeStatus, 60000)", js)
        self.assertIn("setDepositFormEnabled", js)
        self.assertIn('id="bridge-retry-btn"', html)


class TestHomeFactsStrip(unittest.TestCase):
    """WEB-HOME-1: the live network facts strip must keep honest state —
    green only for a proven reply from both endpoints; a failed or
    unreadable read says unknown with a reason, never loading."""

    def test_strip_element_and_states(self) -> None:
        html = _site_src("index.html")
        self.assertIn('id="facts-strip"', html)
        self.assertIn('role="status"', html)
        for fid in ("fact-node", "fact-island", "fact-height", "fact-validators"):
            self.assertIn(f'id="{fid}"', html)
        self.assertIn('id="facts-retry-btn"', html)

    def test_load_facts_proves_both_legs(self) -> None:
        js = _site_src("index.js")
        self.assertIn("function renderFactsState", js)
        self.assertIn("'facts-strip is-'", js)  # class built from state
        for state in ("'live'", "'unknown'", "'loading'"):
            self.assertIn(state, js)
        self.assertIn("/rpc/network-info", js)
        self.assertIn("/rpc/head", js)
        self.assertIn("setInterval(loadFacts, 60000)", js)
        # green requires proven fields, not just a 200
        self.assertIn("Array.isArray(info.validators)", js)
        self.assertIn("Number.isFinite(Number(head.height))", js)

    def test_sentence_follows_the_proven_read(self) -> None:
        """WEB-HOME-2: one shared path — a proven read updates the join
        sentence and meta block too, and a later failure keeps the last
        good values (loadNetworkInfo is folded into loadFacts)."""
        js = _site_src("index.js")
        self.assertIn("function applyNetworkInfo(data)", js)
        self.assertIn("applyNetworkInfo(info)", js)
        self.assertIn("networkInfoGood", js)
        self.assertIn("function markNetworkInfoUnknown()", js)
        self.assertNotIn("async function loadNetworkInfo", js)


class TestHomeJoinStepperAndAnswers(unittest.TestCase):
    """WEB-HOME-1: the join steps are a numbered <ol> with a paused gift
    step, and the key request keeps its three answers apart — issued,
    already-has-a-key (server answered), could-not-request."""

    def test_stepper_and_paused_gift(self) -> None:
        html = _site_src("index.html")
        self.assertIn('<ol class="join-steps">', html)
        self.assertIn('aria-current="step"', html)
        step4 = html[html.index("join-step-4") : html.index("</ol>")]
        self.assertIn("step-paused", step4)
        self.assertIn("Faucet paused", step4)
        self.assertIn("paid once the hub faucet resumes", step4)

    def test_three_answers_kept_apart(self) -> None:
        html = _site_src("index.html")
        self.assertIn('id="join-retry-btn"', html)
        js = _site_src("index.js")
        self.assertIn("function setJoinRetry(visible)", js)
        self.assertIn("join-neutral", js)  # server answered, nothing issued
        self.assertIn("join-failed", js)  # could-not-request, retry follows
        self.assertIn("response.status === 409", js)
        self.assertIn("requestSubmit", js)


class TestExchangeChipAndTokens(unittest.TestCase):
    """EXCH-BUYFIRST-2: the testnet chip must shrink and wrap — flex 0 0 auto
    pushed the page to 450 px at 375 — and every var(--token) the
    .exchange-* rules use must be defined in :root (--accent was not;
    older undefined tokens in non-exchange rules are listed in the
    progress note, not fixed here)."""

    def test_testnet_chip_can_shrink_and_wrap(self) -> None:
        css = STYLE.read_text(encoding="utf-8")
        rule = re.search(r"\.exchange-header \.ob-banner\s*\{([^}]*)\}", css)
        self.assertIsNotNone(rule, "chip rule missing")
        body = rule.group(1)
        self.assertNotIn("flex: 0 0 auto", body)
        self.assertIn("min-width: 0", body)
        self.assertIn("max-width: 100%", body)

    def test_exchange_rules_use_defined_tokens(self) -> None:
        css = STYLE.read_text(encoding="utf-8")
        root = re.search(r":root\s*\{([^}]*)\}", css)
        self.assertIsNotNone(root, ":root block missing")
        defined = set(re.findall(r"--([\w-]+)(?=\s*:)", root.group(1)))
        used: set[str] = set()
        for m in re.finditer(r"\.exchange-[^{]*\{([^}]*)\}", css):
            used.update(re.findall(r"var\(--([\w-]+)", m.group(1)))
        self.assertEqual(set(), used - defined)


class TestExchangeTrackRetry(unittest.TestCase):
    """EXCH-TRACKRETRY-1: the track Try again button must not outlive its
    could-not-query error line; and exchange-book.js may only rely on
    errReason because exchange.js loads first — both pinned."""

    def test_script_load_order(self) -> None:
        html = _site_src("exchange.html")
        self.assertLess(
            html.index('src="exchange.js'),
            html.index('src="exchange-book.js'),
            "exchange-book.js calls errReason() defined in exchange.js",
        )

    def test_retry_button_follows_error_line(self) -> None:
        js = _site_src("exchange.js")
        self.assertIn("function setTrackRetry(visible)", js)
        # shown only on could-not-query outcomes (queryFailed + catch)
        self.assertEqual(js.count("setTrackRetry(true)"), 2)
        # hidden on every other outcome: trackDeposit entry, hash 404,
        # address empty-list, address 404, input help, and the good-poll branch
        self.assertGreaterEqual(js.count("setTrackRetry(false)"), 6)

    def test_200_reply_requires_expected_shape(self) -> None:
        """EXCH-TRACKRETRY-1 item 3: a 200 body without the expected arrays
        (e.g. {} or {detail:"Not Found"}) must fail the read, not read empty."""
        book = _site_src("exchange-book.js")
        self.assertIn("Array.isArray(book.sells)", book)
        self.assertIn("Array.isArray(book.buys)", book)
        self.assertIn("Array.isArray(tape.trades)", book)
        self.assertEqual(book.count("reply was not the expected shape"), 2)
        html = _site_src("exchange.html")
        self.assertIn("The book and the trade list", html)


class TestExchangeBuySteps(unittest.TestCase):
    """EXCH-BUYFIRST-1: the step indicator is presentational — aria-current
    marks the step in progress, updated by the existing handlers."""

    def test_steps_markup_and_updates(self) -> None:
        html = _site_src("exchange.html")
        self.assertIn('class="exchange-steps"', html)
        for step in ("step-amount", "step-review", "step-send", "step-track"):
            self.assertIn(f'id="{step}"', html)
        js = _site_src("exchange.js")
        self.assertIn("function updateExchangeStep()", js)
        self.assertIn("aria-current", js)
        self.assertGreaterEqual(js.count("updateExchangeStep();"), 4)
        css = _site_src("style.css")
        self.assertIn("grid-template-areas", css)
        self.assertIn(".exchange-steps li.is-active", css)


class TestExplorerPanelsSearchFeed(unittest.TestCase):
    """WEB-EXPLORER-1: search-first layout; three kept-apart search answers;
    per-panel source lines (live / stale-with-last-good / failed+retry);
    a named feed-disconnect threshold with latest-known block + Reconnect;
    and top-addresses keeping its last good table on failure."""

    def test_search_card_is_first(self) -> None:
        html = _site_src("explorer.html")
        search = html.index('id="search-input"')
        for panel in ("activity-chart", "live-feed-list", "top-addresses-container"):
            self.assertLess(search, html.index(f'id="{panel}"'), f"{panel} must come after search")
        self.assertIn('id="results-section"', html)
        self.assertIn('id="search-retry-btn"', html)

    def test_three_search_answers_kept_apart(self) -> None:
        js = _site_src("explorer.js")
        self.assertIn("Search could not be completed", js)
        self.assertIn("does not mean nothing exists", js)
        self.assertIn("Nothing found", js)
        self.assertIn("function searchFound(", js)
        self.assertIn("function setSearchRetry(visible)", js)
        # a 404 is the only path to not-found for direct lookups
        self.assertIn("r.status === 404", js)
        # the dedicated search-page routes are retained
        self.assertIn("/api/transactions/search?address=", js)
        self.assertIn("/api/blocks/by-address/", js)
        self.assertIn("/api/messages/search?q=", js)
        # a degraded messages leg cannot masquerade as a proven empty
        self.assertIn("msgLegFailed", js)

    def test_per_panel_source_lines(self) -> None:
        html = _site_src("explorer.html")
        for sid in ("chart-source", "feed-source", "ta-source"):
            self.assertIn(f'id="{sid}"', html)
            self.assertIn("panel-src-text", html)
        js = _site_src("explorer.js")
        self.assertIn("function renderPanelSource(id, state, detail)", js)
        for state in ("'live'", "'stale'", "'failed'"):
            self.assertIn(state, js)
        self.assertIn("last good read", js)
        self.assertIn("dataset.lastGoodAt", js)
        css = _site_src("style.css")
        self.assertIn(".panel-source.is-stale", css)
        self.assertIn(".panel-source.is-failed", css)

    def test_feed_disconnect_state(self) -> None:
        html = _site_src("explorer.html")
        self.assertIn('id="feed-disconnect"', html)
        self.assertIn('id="feed-stopped-ago"', html)
        self.assertIn('id="feed-last-block"', html)
        self.assertIn('id="feed-reconnect-btn"', html)
        self.assertIn("Disconnected", html)
        self.assertIn("feed stopped", html)
        js = _site_src("explorer.js")
        self.assertIn("FEED_DISCONNECT_MS", js)  # named threshold constant
        self.assertIn("function checkFeedDisconnected()", js)
        self.assertIn("setInterval(checkFeedDisconnected", js)
        self.assertIn("feedLastOkAt", js)
        self.assertIn("latest known block", js)
        self.assertIn("wire('feed-reconnect-btn'", js)

    def test_top_addresses_keeps_last_good(self) -> None:
        js = _site_src("explorer.js")
        # the destroy-on-fail body must stay gone
        self.assertNotIn("Failed to load top addresses", js)
        self.assertIn("dataset.taLoaded", js)
        self.assertIn("could not load top addresses", js)
        # every panel retry button is wired to its loader
        self.assertIn("wire('ta-retry-btn'", js)
        self.assertIn("wire('chart-retry-btn'", js)
        self.assertIn("wire('feed-retry-btn'", js)


class TestCopyControlStatic(unittest.TestCase):
    def test_single_shared_implementation(self) -> None:
        src = _site_src("copy.js")
        self.assertEqual(1, src.count("window.aitbcCopyBtn"), "copy.js must define aitbcCopyBtn once")
        self.assertIn("window.aitbcCopy", src)
        self.assertIn("document.addEventListener('click'", src, "shared control must use delegation")
        for fname in os.listdir(WEBSITE):
            if fname in {"copy.js"} or not fname.endswith((".js", ".html")):
                continue
            text = _site_src(fname)
            for name in LEGACY:
                self.assertNotIn(f"function {name}", text, f"{fname}: legacy {name} still defined")

    def test_no_inline_copy_handlers(self) -> None:
        """Copy affordances must not carry onclick — delegation replaces them."""
        for fname in os.listdir(WEBSITE):
            if not fname.endswith((".js", ".html")):
                continue
            for m in re.finditer(r'onclick="[^"]*"', _site_src(fname)):
                self.assertNotIn("copy", m.group(0).lower(), f"{fname}: inline copy handler {m.group(0)[:60]}")
        # navigator.clipboard may only be reached through the shared script.
        for fname in os.listdir(WEBSITE):
            if fname == "copy.js" or not fname.endswith((".js", ".html")):
                continue
            self.assertNotIn("navigator.clipboard", _site_src(fname), f"{fname}: direct clipboard call")

    def test_button_accessibility_contract(self) -> None:
        src = _site_src("copy.js")
        self.assertIn('<button type="button" class="copy-btn"', src)
        self.assertIn('aria-label="Copy ', src, "accessible name must name the copied value")
        self.assertIn('" data-copy="', src)
        self.assertIn("aria-live", src)
        # visible label is the word "copy" — contained in "Copy <what>" for
        # WCAG label-in-name.
        self.assertIn('">copy</button>', src)
        self.assertIn("1500", src, "label must restore after ~1.5s")

    def test_shared_announcer(self) -> None:
        src = _site_src("copy.js")
        self.assertIn("sr-announcer", src)
        self.assertIn("aria-live", src)
        self.assertIn("polite", src)
        self.assertIn("Copied to clipboard", src)
        self.assertIn("Copy failed", src)

    def test_capture_phase_listener(self) -> None:
        """Copy buttons live inside rows with inline onclick navigation — a
        bubble-phase document handler runs AFTER the row's handler, so the
        stop must happen on capture, plus preventDefault for <a> ancestors."""
        src = _site_src("copy.js")
        self.assertRegex(
            src,
            r"addEventListener\(\s*'click'[\s\S]*?,\s*true\s*\)",
            "delegated click handler must be capture-phase",
        )
        self.assertIn("preventDefault", src)
        self.assertIn("stopPropagation", src)

    def test_fallback_path(self) -> None:
        src = _site_src("copy.js")
        self.assertIn("execCommand('copy')", src)
        self.assertIn("Ctrl+C", src, "total failure must point at manual copy")
        self.assertIn("copy-fallback", src)

    def test_script_loaded_deferred_and_stamped(self) -> None:
        for page in PAGES_WITH_COPY:
            text = _site_src(page)
            m = re.search(r'<script src="copy\.js\?v=[0-9a-f]+" defer></script>', text)
            self.assertIsNotNone(m, f"{page}: copy.js must be loaded deferred with the asset stamp")
            # copy.js must precede the page's own emitter script so
            # aitbcCopyBtn exists when the page script runs (defer keeps
            # document order).
            emitters = {
                "index.html": "index.js",
                "explorer.html": "explorer.js",
                "block.html": None,
                "tx.html": None,
                "search.html": None,
                "bridges.html": "bridges.js",
                "marketplace.html": "marketplace.js",
                "exchange.html": "exchange.js",
                "customer-dashboard.html": "dashboard.js",
                "shop-dashboard.html": "dashboard.js",
                "messages.html": "messages.js",
            }
            emitter = emitters[page]
            if emitter:
                self.assertLess(m.start(), text.index(f'src="{emitter}'), f"{page}: copy.js must load before {emitter}")

    def test_every_truncation_site_has_control(self) -> None:
        missing = [f"{fname}: {pat}" for fname, pat in TRUNCATION_SITES if not re.search(pat, _site_src(fname))]
        self.assertEqual([], missing, "truncation sites missing the shared control:\n" + "\n".join(missing))

    def test_css_contract(self) -> None:
        css = STYLE.read_text(encoding="utf-8")
        base = re.search(r"\.copy-btn\s*\{([^}]*)\}", css)
        self.assertIsNotNone(base)
        self.assertIn("border:", base.group(1), "the control must be visibly a control")
        # >=44px hit area under the coarse/mobile block, with the
        # compensating negative margin so rows do not grow.
        media = css[css.index("@media (pointer: coarse)") :]
        m = re.search(r"\.copy-btn\s*\{([^}]*)\}", media)
        self.assertIsNotNone(m, "media block must size .copy-btn")
        self.assertIn("min-height: 44px", m.group(1))
        self.assertIn("min-width: 44px", m.group(1))
        self.assertRegex(m.group(1), r"margin:\s*-", "compensating margin must keep row heights")
        # fallback textarea rules; retired per-site machinery.
        self.assertIn(".copy-fallback", css)
        self.assertIn(".copy-ok", css)
        self.assertNotIn(".copy-hint", css)
        self.assertNotIn(".copy-feedback", css)


# ---------------------------------------------------------------------------
# Browser layer — same env detection as the 375px layout guard.

_HEX = "ab" * 32
_FIXTURES = {
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
    # search.html — real .block-item rows carrying inline onclick navigation
    # with a copy button inside (the WEB-FIX-2b defect class).
    "/api/transactions/search": {"transactions": []},
    "/api/blocks/by-address/": {
        "blocks": [
            {
                "height": 48691,
                "hash": "0x" + _HEX,
                "proposer": "0x" + "ef" * 20,
                "txCount": 2,
                "timestamp": "2026-10-15T21:00:00Z",
            }
        ]
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

# Clipboard spy: records what writeText receives. The failure variant also
# makes writeText reject and execCommand fail, exercising the visible
# "press Ctrl+C" fallback.
_SPY_OK_JS = """
window.__copied = [];
Object.defineProperty(navigator, 'clipboard', {value: {writeText: t => {
  window.__copied.push(t); return Promise.resolve();
}}});
"""
_SPY_FAIL_JS = """
window.__copied = [];
Object.defineProperty(navigator, 'clipboard', {value: {writeText: t =>
  Promise.reject(new Error('denied'))}});
document.execCommand = () => false;
"""

_CLICK_JS = """
new Promise(resolve => {
  const btn = document.querySelector('.copy-btn[aria-label="Copy transaction hash"]');
  if (!btn) { resolve(JSON.stringify({err: 'no .copy-btn in DOM'})); return; }
  btn.click();
  setTimeout(() => resolve(JSON.stringify({
    label: btn.getAttribute('aria-label'),
    copied: window.__copied,
    btnText: btn.textContent,
    ann: (document.getElementById('sr-announcer') || {}).textContent || ''
  })), 300);
})
"""

# WEB-FIX-2b: the real defect site — a .copy-btn inside a row whose inline
# onclick navigates (search.html block/tx result rows). The row's own
# handler is instrumented to count rather than navigate; on the unfixed
# bubble-phase handler the row fires first (nav=1), on the fix the capture
# listener stops the event before it reaches the row (nav stays 0).
_CLICK_IN_ROW_JS = """
new Promise(resolve => {
  const rows = document.querySelectorAll('.block-item[onclick]');
  const btn = document.querySelector('.block-item button.copy-btn');
  if (!rows.length || !btn) {
    resolve(JSON.stringify({err: 'no clickable row with copy button'}));
    return;
  }
  rows.forEach(el => el.setAttribute('onclick', 'window.__nav=(window.__nav||0)+1'));
  btn.click();
  setTimeout(() => resolve(JSON.stringify({
    copied: window.__copied,
    nav: window.__nav || 0,
    btnText: btn.textContent,
    ann: (document.getElementById('sr-announcer') || {}).textContent || ''
  })), 300);
})
"""


def _find_browser() -> str | None:
    env = os.environ.get("AITBC_WEBSITE_BROWSER")
    if env and shutil.which(env):
        return shutil.which(env)
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        hit = shutil.which(name)
        if hit:
            return hit
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
class TestCopyControlBrowser(unittest.TestCase):
    """Real-click assertion: full value reaches the clipboard, outcome is announced."""

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

    def _click_and_read(self, spy_js: str, page: str = "bridges.html", expr: str = _CLICK_JS) -> dict:
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
                await send("Page.addScriptToEvaluateOnNewDocument", {"source": _STUB_JS})
                await send("Page.addScriptToEvaluateOnNewDocument", {"source": spy_js})
                await send("Page.navigate", {"url": f"http://127.0.0.1:{self.port}/{page}"})
                await asyncio.sleep(2.5)
                res = await send(
                    "Runtime.evaluate",
                    {"expression": expr, "returnByValue": True, "awaitPromise": True},
                )
                val = res.get("result", {}).get("result", {}).get("value")
                self.assertIsNotNone(val, "click evaluation produced no result")
                return json.loads(val)

        return asyncio.run(go())

    def test_click_copies_full_value_and_announces(self) -> None:
        r = self._click_and_read(_SPY_OK_JS)
        self.assertNotIn("err", r, r.get("err"))
        self.assertTrue(r["label"].startswith("Copy "), f"accessible name names the value: {r['label']}")
        self.assertEqual(["0x" + _HEX], r["copied"], "must copy the FULL value, not the truncated text")
        self.assertNotIn("...", r["copied"][0])
        self.assertEqual("Copied to clipboard", r["ann"])
        self.assertEqual("copied", r["btnText"], "visible label must flip to 'copied'")

    def test_failure_is_shown_not_swallowed(self) -> None:
        r = self._click_and_read(_SPY_FAIL_JS)
        self.assertNotIn("err", r, r.get("err"))
        self.assertIn("Ctrl+C", r["btnText"], "total failure must point at manual copy")
        self.assertIn("Copy failed", r["ann"])

    def test_click_inside_nav_row_does_not_navigate(self) -> None:
        """Real .block-item onclick row (search.html results): the copy click
        must copy the full value and must NOT reach the row's navigation."""
        r = self._click_and_read(_SPY_OK_JS, "search.html?query=0x" + "cd" * 20, _CLICK_IN_ROW_JS)
        self.assertNotIn("err", r, r.get("err"))
        self.assertEqual(["0x" + _HEX], r["copied"], "must copy the FULL block hash")
        self.assertEqual(0, r["nav"], "row navigation handler must not fire on a copy click")
        self.assertEqual("Copied to clipboard", r["ann"])


if __name__ == "__main__":
    unittest.main()
