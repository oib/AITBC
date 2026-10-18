"""Guard: website markup must stay compatible with ``script-src 'self'``.

A Content-Security-Policy without ``'unsafe-inline'`` for scripts blocks inline
event-handler attributes (``onclick=``, ``onkeydown=`` ...), ``javascript:`` URLs
and inline ``<script>`` blocks. Rows that must be clickable carry ``data-href``
and are wired by one delegated listener (see explorer.js) instead.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

WEBSITE = Path(__file__).resolve().parents[2] / "website"

# on<event>= as an HTML attribute (in static markup or JS template strings),
# not the DOM property assignment ``el.onclick = fn``.
# Pages that still carry inline <script> blocks and/or inline handlers would
# live here as known debt — kept empty: every page was externalized, and a
# re-added entry is a deliberate exemption that must be argued for in review.
KNOWN_DEBT: set[str] = set()

INLINE_HANDLER = re.compile(r"""<[a-zA-Z][^<>]*\s(on[a-z]+)\s*=\s*(?:\\?["'])""")


class TestCspReady(unittest.TestCase):
    def test_no_inline_event_handler_attributes(self) -> None:
        bad = []
        for p in sorted([*WEBSITE.glob("*.html"), *WEBSITE.glob("*.js")]):
            if p.parent.name == "vendor" or p.name in KNOWN_DEBT:
                continue
            src = p.read_text(encoding="utf-8")
            for m in INLINE_HANDLER.finditer(src):
                line = src.count("\n", 0, m.start()) + 1
                bad.append(f"{p.name}:{line}: inline {m.group(1)}= handler")
        self.assertEqual([], bad, "\n".join(bad))

    def test_no_javascript_urls_or_inline_scripts(self) -> None:
        bad = []
        for p in sorted(WEBSITE.glob("*.html")):
            if p.name in KNOWN_DEBT:
                continue
            src = p.read_text(encoding="utf-8")
            if re.search(r"""(?:href|src)\s*=\s*["']\s*javascript:""", src, re.I):
                bad.append(f"{p.name}: javascript: URL")
            for m in re.finditer(r"<script\b([^>]*)>", src, re.I):
                attrs = m.group(1)
                if "src=" not in attrs and not re.search(r"type\s*=\s*[\"']application/(ld\+)?json", attrs, re.I):
                    bad.append(f"{p.name}: inline <script>")
        self.assertEqual([], bad, "\n".join(bad))

    def test_dashboard_tables_keep_value_casing(self) -> None:
        # WEB-DASH-1 payload: .block-list-table's first-column rule is a label
        # style (small/muted/uppercase); data tables emitted by renderTable get
        # the data-table modifier so real values keep their casing and colour.
        js = (WEBSITE / "dashboard.js").read_text(encoding="utf-8")
        css = (WEBSITE / "style.css").read_text(encoding="utf-8")
        self.assertIn('class="block-list-table data-table"', js)
        rule = re.search(r"\.block-list-table\.data-table td:first-child\s*\{([^}]*)\}", css)
        self.assertIsNotNone(rule, "data-table first-column override missing")
        self.assertIn("text-transform: none", rule.group(1))
        btn = re.search(r"button\.endpoint\s*\{([^}]*)\}", css)
        self.assertIsNotNone(btn, "button.endpoint color rule missing")
        self.assertIn("color: var(--text)", btn.group(1))

    def test_dashboard_dates_are_zone_labelled_and_tokens_humanized(self) -> None:
        # WEB-DASH-1 ASK answer: dates are viewer-local with a short zone label
        # (never bare — Explorer's literal " UTC" suffix on local output is the
        # mislabelling this avoids). Machine tokens (settlement_failed,
        # per_audio_min) render as words via humanize().
        js = (WEBSITE / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("timeZoneName", js)
        self.assertIn("function tzLabel", js)
        self.assertIn("function humanize", js)
        self.assertIn("humanize(job.payment_status)", js)
        self.assertIn("humanize(o.price_unit", js)
        self.assertNotIn("toISOString().slice(0, 19)", js, "bare UTC formatting must not come back")

    def test_clickable_rows_use_data_href(self) -> None:
        # nav.js carries the one delegated listener pair; the emitter scripts
        # must only ever emit data-href attributes, never inline handlers.
        src = (WEBSITE / "nav.js").read_text(encoding="utf-8")
        self.assertIn("closest('[data-href]')", src)
        self.assertIn("getAttribute('data-href')", src)
        for emitter in ("explorer.js", "block.js", "search.js"):
            self.assertIn("data-href=", (WEBSITE / emitter).read_text(encoding="utf-8"), f"{emitter} lost its data-href rows")

    def test_nav_js_is_loaded_where_rows_exist(self) -> None:
        # A page emitting data-href rows without nav.js would silently die —
        # pin the pairing, not just the files.
        import re as _re

        nav_pages = set()
        for p in WEBSITE.glob("*.html"):
            if _re.search(r'<script src="nav\.js\?v=[0-9a-f]+" defer>', p.read_text(encoding="utf-8")):
                nav_pages.add(p.name)
        # Every page with scripts must load nav.js; the static notice page
        # (follower-api-key-announcement) has no scripts and is exempt.
        for p in WEBSITE.glob("*.html"):
            has_scripts = '<script src="' in p.read_text(encoding="utf-8")
            self.assertEqual(has_scripts, p.name in nav_pages, f"{p.name}: nav.js loading must match 'has scripts'")


if __name__ == "__main__":
    unittest.main()
