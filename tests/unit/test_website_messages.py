"""MSG-4 — messages.html rendering-safety guard.

Static layer (runs everywhere): chain-sourced text in ``messages.js`` reaches
the DOM only via ``textContent``/attributes — no ``innerHTML`` injection of
chain data — and the sanitizer covers the pinned bidi/zero-width ranges. The
page carries ``noindex`` and stays out of the sitemap (the discoverability
suite computes the same set independently).

Browser layer (skips cleanly without Chromium): hostile fixture messages —
script markup, bidi overrides, zero-width characters, a 4 KiB body, a 64-char
topic — render inert: no script executes, no element is injected, and the
invisible characters appear as visible ``[U+XXXX]`` placeholders.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_website_copy import (  # noqa: E402
    _BROWSER,
    _HAS_WS,
    TestCopyControlBrowser,
)

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"
MSG_JS = WEBSITE / "messages.js"
MSG_HTML = WEBSITE / "messages.html"


class TestMessagesStatic(unittest.TestCase):
    def test_no_chain_data_innerhtml(self) -> None:
        src = MSG_JS.read_text(encoding="utf-8")
        # innerHTML is only acceptable for static, non-chain markup; none
        # should appear at all in messages.js — rendering is DOM-builders.
        self.assertNotIn("innerHTML", src, "messages.js must not use innerHTML")
        for m in re.finditer(r"insertAdjacentHTML\('[^']+',\s*([^)]+)\)", src):
            self.assertIn(
                "aitbcCopyBtn",
                m.group(1),
                "insertAdjacentHTML may only receive the escaped copy-button emitter",
            )

    def test_sanitizer_covers_pinned_ranges(self) -> None:
        src = MSG_JS.read_text(encoding="utf-8")
        self.assertIn("\\u200B-\\u200F", src)
        self.assertIn("\\u202A-\\u202E", src)
        self.assertIn("\\u2066-\\u2069", src)
        self.assertIn("\\uFEFF", src)
        self.assertIn("U+", src, "neutralised chars must render as visible [U+XXXX] placeholders")

    def test_page_is_noindex_and_absent_from_sitemap(self) -> None:
        html = MSG_HTML.read_text(encoding="utf-8")
        self.assertIn('name="robots" content="noindex', html)
        sitemap = (WEBSITE / "sitemap.xml").read_text(encoding="utf-8")
        self.assertNotIn("messages.html", sitemap)

    def test_page_loads_shared_scripts_deferred(self) -> None:
        html = MSG_HTML.read_text(encoding="utf-8")
        for js in ("config.js", "copy.js", "messages.js"):
            m = re.search(rf'<script src="{js}\?v=[0-9a-f]+" defer></script>', html)
            self.assertIsNotNone(m, f"{js} must load deferred with the asset stamp")

    def test_unmoderated_label_present(self) -> None:
        html = MSG_HTML.read_text(encoding="utf-8")
        self.assertIn("Unmoderated", html)
        self.assertIn("on-chain", html.lower())


_HOSTILE_FIXTURE_JS = r"""
window.fetch = ((u, opts) => {
  let p = new URL(u, location.origin).pathname;
  p = p.replace(/^\/explorer-api/, '');
  const hostile = [
    {
      message_id: 'h1', tx_hash: '0x' + 'ab'.repeat(32), block_height: 48865,
      author: '0x' + 'cd'.repeat(20), sender: '0x' + 'cd'.repeat(20),
      topic: 'msg-fix', kind: 'post',
      body: '<script>window.__xss=1</scr' + 'ipt><img src=x onerror="window.__xss=2">',
      parent: null, timestamp: '2026-10-15T22:30:25Z', fee: 360000,
    },
    {
      message_id: 'h2', tx_hash: '0x' + 'ef'.repeat(32), block_height: 48866,
      author: '0x' + 'cd'.repeat(20), sender: '0x' + 'cd'.repeat(20),
      topic: 'msg-fix', kind: 'post',
      body: 'bidi ‮tihs si dessert‬ zero‑width here‌ and there‍ bom﻿end',
      parent: null, timestamp: '2026-10-15T22:31:00Z', fee: 360000,
    },
    {
      message_id: 'h3', tx_hash: '0x' + '12'.repeat(32), block_height: 48867,
      author: '0x' + 'cd'.repeat(20), sender: '0x' + 'cd'.repeat(20),
      topic: 'a'.repeat(64), kind: 'post',
      body: 'x'.repeat(4096),
      parent: null, timestamp: '2026-10-15T22:32:00Z', fee: 360000,
    },
  ];
  const TOPICS = {success: true, chain_id: 'ait-fixture', index_height: 48867,
                  topics: [{topic: 'msg-fix', message_count: 2, last_block_height: 48866,
                            last_timestamp: '2026-10-15T22:31:00Z'},
                           {topic: 'a'.repeat(64), message_count: 1,
                            last_block_height: 48867, last_timestamp: '2026-10-15T22:32:00Z'}],
                  count: 2, total_topics: 2, scan_bounded: false};
  const MSGS = {success: true, chain_id: 'ait-fixture', index_height: 48867,
                messages: hostile, count: hostile.length, next_cursor: null,
                scan_bounded: false};
  if (p === '/api/messages/topics') return Promise.resolve(new Response(JSON.stringify(TOPICS), {headers: {'Content-Type': 'application/json'}}));
  if (p === '/api/messages' || p.startsWith('/api/messages?')) return Promise.resolve(new Response(JSON.stringify(MSGS), {headers: {'Content-Type': 'application/json'}}));
  return Promise.resolve(new Response('{}', {status: 200, headers: {'Content-Type': 'application/json'}}));
});
"""

_PROBE_JS = r"""
(() => {
  const bodies = [...document.querySelectorAll('.msg-body')].map(e => e.textContent);
  const items = document.querySelectorAll('.msg-item').length;
  const scripts = document.querySelectorAll('#messages-container script').length;
  const imgs = document.querySelectorAll('#messages-container img').length;
  const topicBtns = [...document.querySelectorAll('.filter-btn')].map(b => b.textContent);
  return JSON.stringify({
    xss: window.__xss || 0,
    items, scripts, imgs,
    bodies,
    hasPlaceholder: bodies.some(b => /\[U\+20(2E|0B)\]|\[U\+FEFF\]|\[U\+200[DEF]\]/.test(b)),
    topicBtns,
    copyBtns: document.querySelectorAll('#messages-container .copy-btn').length,
  });
})()
"""


@unittest.skipUnless(_BROWSER and _HAS_WS, "skipped: no browser (chromium on PATH) or no websockets package")
class TestMessagesBrowser(TestCopyControlBrowser):
    """Reuses the copy-control CDP harness; each test navigates messages.html
    with the hostile fixture injected on the new document."""

    def _read(self, expr: str = _PROBE_JS, page: str = "messages.html") -> dict:
        return self._click_and_read(_HOSTILE_FIXTURE_JS, page, expr)

    def test_hostile_content_renders_inert(self) -> None:
        r = self._read()
        self.assertNotIn("err", r, r.get("err"))
        self.assertEqual(3, r["items"], "all three hostile fixture messages render")
        self.assertEqual(0, r["xss"], "no chain-supplied script/onerror may execute")
        self.assertEqual(0, r["scripts"], "no <script> element injected from chain text")
        self.assertEqual(0, r["imgs"], "no <img> element injected from chain text")

    def test_invisible_chars_become_visible_placeholders(self) -> None:
        r = self._read()
        self.assertNotIn("err", r, r.get("err"))
        self.assertTrue(
            r["hasPlaceholder"],
            f"bidi/zero-width chars must show as [U+XXXX], bodies: {[b[:60] for b in r['bodies']]}",
        )

    def test_copy_controls_present_for_hashes_and_authors(self) -> None:
        r = self._read()
        self.assertNotIn("err", r, r.get("err"))
        # per message: author address + tx hash = 2 controls
        self.assertEqual(6, r["copyBtns"])


if __name__ == "__main__":
    unittest.main()
