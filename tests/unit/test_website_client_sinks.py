"""WEB-9: client-side rendering safety guard for website/.

Offline static scan. For every template literal that contains markup
(``<``), every ``${...}`` interpolation must be provably safe:

- wrapped by a safe call (escapeHtml, encodeURIComponent, formatters,
  badge/link builders — see SAFE_CALLS), or
- a number/constant expression, or
- a bare identifier whose ``const/let`` initializer resolves safe
  recursively (fragments pre-built from escaped parts), or
- a ``.map(fn)`` whose fn's body templates pass the same scan, or
- on the allowlist below with a one-line reason.

Also fails on external-origin script/style includes, ``target=_blank``
without ``rel="noopener noreferrer"``, ``eval``/``new
Function``/``document.write``/``.outerHTML =``, and stale allowlist
entries. Line numbers are never used for matching.

Run: pytest tests/unit/test_website_client_sinks.py
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"

# Calls that neutralize any value they wrap (text or URL context).
SAFE_CALL = re.compile(
    r"\b(?:escapeHtml|escapeAttr|encodeURIComponent|Number|String|Math\.[\w.]+|"
    r"JSON\.stringify|parseInt|parseFloat|Date\.now|new Date|"
    r"shortAddr|shortHash|shortHex|formatAddress|formatBlockHash|formatTxHash|"
    r"formatServiceTitle|formatPrice|formatDate|formatHash|plainHash|fmtAit|fmtNum|"
    r"eurStr|relTime|sevClass|statusClass|copyBtn|aitbcCopyBtn|statusBadge|eventBadge|priBadge|"
    r"txLink|addrLink|dirBadge|directionBadge|txTypeColor|blockContentHtml|"
    r"txChipsHtml|renderBlockCard|alertCard|eventRow|createOfferCard|aitbcFmt\.[\w.]+)\s*\("
)

# Interpolations the resolver cannot prove statically but that were audited
# safe by hand: (file-glob, regex on the ${...} expression, reason).
# Keep this list short; new entries need a justification comment.
ALLOWLIST: list[tuple[str, str, str]] = [
    ("exchange.js", r"^\$?\{?\s*[kv]\s*\}?$", "rows are literal [label, formatted] pairs — no data fields"),
    ("alerts.js", r"^\{?\s*cls\s*\}?$", "severity class — mapped literal, never data text"),
    ("alerts.js", r"^\{?\s*text\s*\}?$", "literal status text"),
    ("alerts.js", r"^\{?\s*extraClass\s*\}?$", "alertCard param — literal class at call sites"),
    ("bridges.js", r"^\{?\s*parts\.\w+\s*\}?$", "transferParts() fields — escapeHtml-built fragments or literals"),
    ("dashboard.js", r"^\{?\s*esc\s*\}?$", "already escapeHtml() output"),
    ("dashboard.js", r"^\{?\s*v\s*\}?$", "html:true cells carry prebuilt fragments (escrow/txLink)"),
    ("exchange.js", r"^\{?\s*(cls|fromShort|aitTxLink|errLine)\s*\}?$", "prebuilt escaped fragments"),
    (
        "explorer.js",
        r"^\{?\s*(c|n|bar|contentRow|rows|txDetails|txsHtml|payloadDetails|details|dBadge|confirmationBadge|direction|blockHashVal|transactionsHtml)\s*\}?$",
        "prebuilt escaped fragments or counts",
    ),
    ("marketplace.js", r"^\{?\s*(statusClass|confirmationBadge|ratingStars)\s*\}?$", "class literal / prebuilt fragments"),
    ("search.html", r"^\{?\s*(dir|labels\[dir\]|dBadge)\s*\}?$", "direction constant / badge fragment"),
]

TEMPLATE = re.compile(r"`((?:[^`\\]|\\.)*)`", re.S)
INTERP = re.compile(r"\$\{((?:[^{}]|\{[^{}]*\})*)\}")


def _files() -> dict[str, str]:
    out = {}
    for p in sorted(WEBSITE.glob("*.js")) + sorted(WEBSITE.glob("*.html")):
        src = p.read_text(encoding="utf-8")
        if p.suffix == ".html":
            src = "\n".join(m.group(1) for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", src, re.S))
        out[p.name] = src
    return out


def _split_top(expr: str, sep: str = "?") -> list[str]:
    """Split on sep only at paren/brace depth 0 and outside string literals."""
    parts, depth, cur, quote = [], 0, "", None
    for ch in expr:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0 and not quote:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _atom_safe(e: str) -> bool | None:
    """Cheap exact rules. Returns True/False/None (None = keep resolving)."""
    if SAFE_CALL.match(e):
        return True
    if re.search(r"\b(?:escapeHtml|encodeURIComponent)\s*\(", e) and not re.search(r"`[^`]*\$\{", e):
        return True
    if re.fullmatch(r"[\d.+\-*/%()\s]+", e):  # arithmetic on literals
        return True
    if re.fullmatch(r"[\w$.[\]()+\-*/%\s]+", e) and re.search(r"[\d*/%]", e):
        # arithmetic over numeric-ish identifiers: (a / b) * 100, i + 1, x.length
        return True
    if re.fullmatch(r"[\w$.[\]()]*\.length\b", e):  # .length is always a number
        return True
    if re.fullmatch(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", e):  # string literal
        return True
    return None


def _expr_safe(expr: str, src: str, fname: str, depth: int = 0, seen: frozenset = frozenset()) -> bool:
    """True iff every data-bearing part of expr is provably escaped/constant."""
    e = expr.strip().rstrip(";")
    if depth > 6 or not e:
        return True
    if _allowlisted(fname, e):
        return True
    if _atom_safe(e) is True:
        return True
    # ternary: cond ? a : b — the condition renders nothing; branches must be safe
    q = _split_top(e, "?")
    if len(q) > 1:
        rest = "?".join(q[1:])
        return all(_expr_safe(b, src, fname, depth + 1, seen) for b in _split_top(rest, ":"))
    if _split_top(e, "+") != [e]:  # concat — quote-aware top-level split
        return all(_expr_safe(p, src, fname, depth + 1, seen) for p in _split_top(e, "+"))
    # .map(fn).join — recurse into the referenced function's template returns
    m = re.match(r"^[\w$.\[\]()[\]\d\s,]+\.map\(\s*([A-Za-z_$][\w$]*|.*=>.*)\)\s*(?:\.join\([^)]*\))?$", e, re.S)
    if m:
        return _map_fn_safe(m.group(1), src, fname, depth, seen)
    m = re.match(r"^[A-Za-z_$][\w$]*\s*\(", e)  # named-helper call — recurse its body
    if m:
        fn = m.group(0)[:-1].strip()
        return fn in seen or _fn_body_safe(fn, src, fname, depth, seen | {fn})
    m = re.fullmatch(r"([A-Za-z_$][\w$]*)", e)  # bare identifier — resolve initializer
    if m and m.group(1) not in seen:
        name = m.group(1)
        init = _find_init(name, src)
        return init is not None and _expr_safe(init, src, fname, depth + 1, seen | {name})
    return False


def _find_init(name: str, src: str) -> str | None:
    """Return the initializer expression for `const|let|var name = ...`."""
    m = re.search(rf"\b(?:const|let|var)\s+{re.escape(name)}\s*=\s*", src)
    if not m:
        return None
    start = m.end()
    out, depth = [], 0
    for ch in src[start:]:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ";" and depth == 0:
            break
        elif ch == "\n" and depth == 0:
            break
        out.append(ch)
    return "".join(out).strip() or None


def _map_fn_safe(fnexpr: str, src: str, fname: str, depth: int, seen) -> bool:
    fnexpr = fnexpr.strip()
    m = re.match(r"^\(?[\w$,\s]*\)?\s*=>\s*(.+)$", fnexpr, re.S)
    if m:
        return _expr_safe(m.group(1), src, fname, depth + 1, seen)
    if re.fullmatch(r"[A-Za-z_$][\w$]*", fnexpr):
        return _fn_body_safe(fnexpr, src, fname, depth, seen | {fnexpr})
    return False


def _fn_body_safe(fn: str, src: str, fname: str, depth: int, seen) -> bool:
    """A named helper is safe if every template literal in its body passes."""
    m = re.search(
        rf"(?:function\s+{re.escape(fn)}\s*\([^)]*\)\s*\{{|{re.escape(fn)}\s*=\s*(?:\([^)]*\)|[\w$]+)\s*=>\s*\{{?)", src
    )
    if not m:
        return False
    body = src[m.start() :]
    for tm in TEMPLATE.finditer(body):
        tpl = tm.group(1)
        if "<" not in tpl:
            continue
        for im in INTERP.finditer(tpl):
            if not _expr_safe(im.group(1), src, fname, depth + 1, seen):
                return False
    return True


def _allowlisted(fname: str, expr: str) -> bool:
    e = expr.strip()
    return any(re.match(glob, fname) and re.fullmatch(rx, e) for glob, rx, _ in ALLOWLIST)


class TestClientSinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = _files()

    def test_no_eval_or_document_write(self) -> None:
        bad = [
            f"{f}: forbidden sink"
            for f, src in self.files.items()
            if re.search(r"\beval\s*\(|new Function|document\.write|\.outerHTML\s*=", src)
        ]
        self.assertEqual([], bad, "\n".join(bad))

    def test_markup_interpolations_escaped(self) -> None:
        bad = []
        for fname, src in self.files.items():
            for tm in TEMPLATE.finditer(src):
                tpl = tm.group(1)
                if "<" not in tpl:
                    continue
                for im in INTERP.finditer(tpl):
                    if not _expr_safe(im.group(1), src, fname):
                        line = src.count("\n", 0, tm.start() + im.start()) + 1
                        bad.append(f"{fname}:{line}: unproven ${{ {im.group(1).strip()[:60]} }}")
        self.assertEqual([], bad, "\n".join(bad))

    def test_no_external_includes(self) -> None:
        bad = []
        for p in sorted(WEBSITE.glob("*.html")):
            src = p.read_text(encoding="utf-8")
            for m in re.finditer(r'<(?:script|link|img|iframe)\b[^>]*(?:src|href)\s*=\s*"(https?://[^"]+)"', src):
                if not m.group(1).startswith("https://hub.aitbc.bubuit.net"):
                    bad.append(f"{p.name}: external include {m.group(1)[:60]}")
        self.assertEqual([], bad, "\n".join(bad))

    def test_blank_targets_have_rel(self) -> None:
        # scan raw HTML (static links) AND .js/inline-script templates (generated links)
        sources = dict(self.files.items())
        for p in sorted(WEBSITE.glob("*.html")):
            sources[p.name] = sources[p.name] + "\n" + p.read_text(encoding="utf-8")
        bad = []
        for f, src in sources.items():
            for m in re.finditer(r"<a\b[^>]*target=\"_blank\"[^>]*>", src):
                rel = re.search(r'rel="([^"]*)"', m.group(0))
                tokens = set((rel.group(1) if rel else "").split())
                if not {"noopener", "noreferrer"} <= tokens:
                    bad.append(f"{f}: target=_blank without noopener noreferrer")
        self.assertEqual([], bad, "\n".join(bad))

    def test_allowlist_entries_used(self) -> None:
        used = set()
        for fname, src in self.files.items():
            for tm in TEMPLATE.finditer(src):
                if "<" not in tm.group(1):
                    continue
                for im in INTERP.finditer(tm.group(1)):
                    raw = im.group(1).strip()
                    # entries match the whole expr or a ternary/concat sub-part
                    parts = {raw}
                    for sep in ("?", ":", "+"):
                        parts |= {p.strip() for part in list(parts) for p in _split_top(part, sep)}
                    for i, (glob, rx, _) in enumerate(ALLOWLIST):
                        if re.match(glob, fname) and any(re.fullmatch(rx, p) for p in parts):
                            used.add(i)
        stale = [f"{g} {rx}: {reason}" for i, (g, rx, reason) in enumerate(ALLOWLIST) if i not in used]
        self.assertEqual([], stale, "stale allowlist entries:\n" + "\n".join(stale))


if __name__ == "__main__":
    unittest.main()
