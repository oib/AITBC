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
# Pages that still carry inline <script> blocks and/or inline handlers. They must
# be moved to external files (and this set emptied) BEFORE the CSP header is
# switched from Report-Only to enforcing, or these pages will stop working.
KNOWN_DEBT = {
    "block.html",
    "customer-dashboard.html",
    "search.html",
    "shop-dashboard.html",
    "tx.html",
}

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

    def test_clickable_rows_use_data_href(self) -> None:
        src = (WEBSITE / "explorer.js").read_text(encoding="utf-8")
        self.assertIn("data-href=", src)
        self.assertIn("closest('[data-href]')", src)


if __name__ == "__main__":
    unittest.main()
