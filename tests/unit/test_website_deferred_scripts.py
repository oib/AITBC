"""Guard: inline <script> blocks must not use deferred names at parse time.

WEB-2 made the per-page scripts ``defer`` (they run after HTML parsing). Two
dashboard pages did ``document.addEventListener('DOMContentLoaded',
loadXDashboard)`` in an inline script — the bare identifier is evaluated at
parse time, before the deferred file has executed, so it throws
``ReferenceError`` and the page never initialises. The safe forms are a
callback (``() => loadXDashboard()`` or ``function () { ... }``) — the name
is only looked up when the event fires — or an inline-defined name.
(WEB-CSP-1 later removed inline scripts entirely; this guard now pins the
zero-debt state so a reintroduced block fails at parse-time review.)

This test parses every ``website/*.html`` and fails when an inline script
references, outside any function/callback body, a name declared at top level
in one of the page's deferred scripts (including ``config.js`` and the known
vendor globals ``lucide``/``Chart``).

Heuristic limits — this is a lexical scan, not a JavaScript parser:

- Comments and string/template literals are blanked before scanning, so a
  name inside a quoted string does not count as a reference.
- "Inside a callback" is approximated by protected ranges: the body of a
  ``function ... { ... }`` and the body of an ``=>`` arrow (braced or
  expression form, ended by ``,``/``)``/``;`` at depth 0). A reference inside
  either is considered safe.
- Top-level declarations are matched at column 0
  (``^(async )?function name`` / ``^(const|let|var|class) name``), which is
  how the repo's scripts are written. Minified vendor files yield nothing;
  their globals come from ``_VENDOR_GLOBALS`` instead.
- ``typeof``-guarded references (which are genuinely safe at parse time) are
  still flagged — conservative on purpose; wrap the lookup in a callback.
- Non-deferred external scripts are ignored: their names are assumed safe
  (they execute in document order; an inline script *above* a sync script
  could still break, but no page does that).
- ``<script type=...>`` blocks that are not JavaScript (e.g. ``ld+json``)
  are skipped.
"""

from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"

# Minified vendor files expose these globals; extracting declarations from
# them is hopeless, so they are listed per filename instead.
_VENDOR_GLOBALS = {
    "lucide.min.js": ("lucide",),
    "chart.umd.min.js": ("Chart",),
}

_NON_JS_TYPES = {
    "application/ld+json",
    "application/json",
    "importmap",
    "speculationrules",
}

_DECL_RE = re.compile(
    r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"
    r"|^(?:const|let|var|class)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
_IDENT = r"[A-Za-z_$][\w$]*"


class _ScriptScanner(HTMLParser):
    """Collect external <script src> tags (with defer flag) and inline bodies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.external: list[tuple[str, bool]] = []
        self.inline: list[tuple[str, str]] = []  # (type, body)
        self._cur_type: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        a = dict(attrs)
        if a.get("src"):
            self.external.append((a["src"], "defer" in a))
        else:
            self._cur_type = (a.get("type") or "").strip().lower()
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._cur_type is not None:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._cur_type is not None:
            self.inline.append((self._cur_type, "".join(self._buf)))
            self._cur_type = None


def _top_level_names(js: str) -> set[str]:
    return {m.group(1) or m.group(2) for m in _DECL_RE.finditer(js)}


def _blank(out: list[str], start: int, end: int) -> None:
    for k in range(start, end):
        if out[k] != "\n":
            out[k] = " "


def _string_end(js: str, i: int, out: list[str]) -> int:
    """Blank a string/template literal starting at js[i]; return end offset."""
    q = js[i]
    n = len(js)
    out[i] = " "
    i += 1
    while i < n:
        if js[i] == "\\":
            _blank(out, i, min(i + 2, n))
            i += 2
            continue
        if js[i] == q:
            out[i] = " "
            return i + 1
        if js[i] != "\n":
            out[i] = " "
        i += 1
    return n


def _scrub(js: str) -> str:
    """Blank comments and string/template literals, preserving offsets."""
    out = list(js)
    i, n = 0, len(js)
    while i < n:
        start = i
        if js[i : i + 2] == "//":
            j = js.find("\n", i)
            i = n if j < 0 else j
            _blank(out, start, i)
        elif js[i : i + 2] == "/*":
            j = js.find("*/", i + 2)
            i = n if j < 0 else j + 2
            _blank(out, start, i)
        elif js[i] in "'\"`":
            i = _string_end(js, i, out)
        else:
            i += 1
    return "".join(out)


def _match_brace(js: str, open_pos: int) -> int:
    depth = 0
    for k in range(open_pos, len(js)):
        if js[k] == "{":
            depth += 1
        elif js[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    return len(js)


def _arrow_body_end(js: str, i: int) -> int:
    """End offset of a braceless ``=>`` expression body starting at ``i``."""
    depth = 0
    while i < len(js):
        ch = js[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and ch in ",;}\n":
            break
        i += 1
    return i


def _callback_ranges(js: str) -> list[tuple[int, int]]:
    """Approximate ranges of function/arrow bodies in scrubbed JS text."""
    ranges: list[tuple[int, int]] = []

    for m in re.finditer(r"\bfunction\b", js):
        brace = js.find("{", m.end())
        if brace >= 0:
            ranges.append((m.start(), _match_brace(js, brace) + 1))

    for m in re.finditer(r"=>", js):
        i = m.end()
        while i < len(js) and js[i].isspace():
            i += 1
        if i >= len(js):
            break
        end = _match_brace(js, i) + 1 if js[i] == "{" else _arrow_body_end(js, i)
        ranges.append((m.start(), end))
    return ranges


def _resolve_src(src: str) -> Path | None:
    path = src.split("?", 1)[0].lstrip("/")
    p = (WEBSITE / path).resolve()
    return p if p.is_file() and WEBSITE.resolve() in p.parents else None


def _page_deferred_names(external: list[tuple[str, bool]]) -> set[str]:
    names: set[str] = set()
    for src, deferred in external:
        if not deferred:
            continue
        names.update(_VENDOR_GLOBALS.get(Path(src).name, ()))
        p = _resolve_src(src)
        if p is not None:
            names.update(_top_level_names(p.read_text(encoding="utf-8")))
    return names


class TestDeferredScriptReferences(unittest.TestCase):
    def test_inline_scripts_do_not_reference_deferred_names_at_top_level(
        self,
    ) -> None:
        violations: list[str] = []
        for page in sorted(WEBSITE.glob("*.html")):
            scanner = _ScriptScanner()
            scanner.feed(page.read_text(encoding="utf-8"))
            deferred = _page_deferred_names(scanner.external)
            if not deferred:
                continue
            for _type, body in scanner.inline:
                if _type in _NON_JS_TYPES:
                    continue
                inline_defined = _top_level_names(body)
                scrubbed = _scrub(body)
                ranges = _callback_ranges(scrubbed)
                for name in deferred - inline_defined:
                    for m in re.finditer(rf"(?<![\w$.]){re.escape(name)}\b", scrubbed):
                        if any(s <= m.start() < e for s, e in ranges):
                            continue
                        line = body.count("\n", 0, m.start()) + 1
                        violations.append(
                            f"{page.name}: inline script references deferred name '{name}' at top level (~line {line})"
                        )
        self.assertEqual(
            violations,
            [],
            "inline scripts must wrap deferred-script names in a callback:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
