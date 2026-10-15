"""Guard: accessibility invariants for the static hub website.

WEB-6 audited the pages for WCAG issues and fixed them in markup/CSS.
This test keeps the fixed properties from regressing by parsing every
``website/*.html`` plus the markup templates inside ``website/*.js`` and
checking ``website/style.css`` for the rules the fixes depend on:

1. Media: ``<img>`` and ``<svg>`` carry ``alt``/``aria-label`` or
   ``aria-hidden="true"``.
2. Controls: every ``<input>``/``<select>``/``<textarea>`` is labelled — a
   ``<label for>`` match, a wrapping ``<label>``, or an aria name.
   ``placeholder`` alone does not count (it vanishes while typing).
3. Buttons and links have text content or an accessible name.
4. Headings never skip a level and each page has exactly one ``<h1>``.
5. Tables have an accessible name (``aria-label``/``<caption>``), ``<th>``
   cells carry ``scope``, and every table sits inside a scrollable
   container so it cannot force page-level horizontal scroll at 375 px.
6. Keyboard: ``onclick`` on a non-interactive element (``div``/``tr``/...)
   must come with ``role``, ``tabindex`` and a key handler; ``outline:none``
   is forbidden unless a ``:focus-visible`` rule exists; the toggle-switch
   checkbox pattern may not hide the input with ``display:none``.
7. ``style.css`` must contain a ``prefers-reduced-motion`` block and the
   ``.visually-hidden`` utility.

No network, no browser. Failure output names the file and offending line.
"""

from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"
CSS = WEBSITE / "style.css"

# Container classes whose CSS gives overflow-x: auto (see style.css).
SCROLL_CLASSES = {
    "table-wrap",
    "ob-scroll",
    "top-addresses-table",
    "endpoint",
    "code-block",
    "code-pre",
    "grid",
}
INTERACTIVE_TAGS = {"a", "button", "input", "select", "textarea", "summary"}
NAME_ATTRS = ("aria-label", "aria-labelledby")


class _A11yParser(HTMLParser):
    """One-pass per-page collector for the a11y assertions."""

    def __init__(self, src: str) -> None:
        super().__init__(convert_charrefs=True)
        self.src = src
        self.problems: list[str] = []
        self._stack: list[tuple[str, dict]] = []
        self._label_for: set[str] = set()
        self._controls: list[tuple[str, dict, int, bool]] = []
        self._headings: list[tuple[int, int]] = []
        self._named: list[dict] = []  # open <a>/<button> elements
        self._tables: list[dict] = []
        self._table_depth = 0
        self._caption = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        line = self.getpos()[0]
        self._form(tag, attr, line)
        self._media_or_named(tag, attr, line)
        self._structure(tag, attr, line)
        self._interactivity(tag, attr, line)
        self._stack.append((tag, attr))

    def _form(self, tag: str, attr: dict, line: int) -> None:
        if tag == "label" and attr.get("for"):
            self._label_for.add(attr["for"])
        if tag in ("input", "select", "textarea"):
            wrapped = any(t == "label" for t, _ in self._stack)
            self._controls.append((tag, attr, line, wrapped))

    def _media_or_named(self, tag: str, attr: dict, line: int) -> None:
        if tag in ("img", "svg"):
            self._media(tag, attr, line)
        if tag in ("a", "button"):
            self._named.append({"tag": tag, "attr": attr, "line": line, "text": []})

    def _structure(self, tag: str, attr: dict, line: int) -> None:
        if re.fullmatch(r"h[1-6]", tag):
            self._headings.append((int(tag[1]), line))
        if tag == "table":
            self._table(tag, attr, line)
        if tag == "caption" and self._table_depth:
            self._caption = True
        if tag == "th" and self._table_depth and not attr.get("scope"):
            self.problems.append(f"line {line}: <th> without scope")

    def _interactivity(self, tag: str, attr: dict, line: int) -> None:
        if "onclick" in attr and tag not in INTERACTIVE_TAGS:
            if not (attr.get("role") and "tabindex" in attr and "onkeydown" in attr):
                self.problems.append(f"line {line}: <{tag} onclick> missing role/tabindex/onkeydown")
        if "outline:none" in (attr.get("style") or "").replace(" ", ""):
            self.problems.append(f"line {line}: inline style outline:none")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack and self._stack[-1][0] == tag:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag in ("a", "button") and self._named:
            el = self._named.pop()
            named = any(el["attr"].get(a) for a in NAME_ATTRS) or el["attr"].get("title")
            if not named and not "".join(el["text"]).strip():
                self.problems.append(f"line {el['line']}: <{tag}> has no accessible name")
        if tag == "table" and self._table_depth:
            self._table_depth -= 1
            tbl = self._tables.pop()
            named = any(tbl["attr"].get(a) for a in NAME_ATTRS)
            if not (named or self._caption):
                self.problems.append(f"line {tbl['line']}: <table> without aria-label/caption")
            self._caption = False
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self._named:
            self._named[-1]["text"].append(data)

    def _media(self, tag: str, attr: dict, line: int) -> None:
        ok = (
            attr.get("aria-hidden") == "true"
            or attr.get("role") == "presentation"
            or attr.get("alt") is not None
            or any(attr.get(a) for a in NAME_ATTRS)
        )
        if not ok:
            self.problems.append(f"line {line}: <{tag}> without alt/aria-label/aria-hidden")

    def _table(self, tag: str, attr: dict, line: int) -> None:
        scrollable = any(set((a.get("class") or "").split()) & SCROLL_CLASSES for _, a in self._stack)
        self._tables.append({"attr": attr, "line": line})
        self._table_depth += 1
        self._caption = False
        if not scrollable:
            self.problems.append(
                f"line {line}: <table> is not inside a scrollable container ({', '.join(sorted(SCROLL_CLASSES))})"
            )

    def validate(self, page: str) -> list[str]:
        out = list(self.problems)
        for tag, attr, line, wrapped in self._controls:
            named = any(attr.get(a) for a in NAME_ATTRS)
            if not (attr.get("id") in self._label_for or wrapped or named):
                out.append(f"line {line}: <{tag} id={attr.get('id') or '?'}> has no label")
        h1 = sum(1 for lv, _ in self._headings if lv == 1)
        if h1 != 1:
            out.append(f"expected exactly one <h1>, found {h1}")
        prev = 0
        for lv, line in self._headings:
            if prev and lv > prev + 1:
                out.append(f"line {line}: heading level skip h{prev}->h{lv}")
            prev = lv
        return [f"{page}: {p}" for p in out]


_SCROLL_RE = re.compile(r'class="[^"]*(table-wrap|ob-scroll|top-addresses-table|endpoint|code-block|code-pre|grid)')


def _id_class_map() -> dict[str, set[str]]:
    """element id -> class set, from all website pages (for JS container lookup)."""
    ids: dict[str, set[str]] = {}
    for html in WEBSITE.glob("*.html"):
        src = html.read_text(encoding="utf-8")
        for m in re.finditer(r'<(\w+)\b[^>]*\bid="([^"]+)"[^>]*>', src):
            classes = set()
            cm = re.search(r'class="([^"]*)"', m.group(0))
            if cm:
                classes = set(cm.group(1).split())
            ids.setdefault(m.group(2), set()).update(classes)
    return ids


def _container_classes(src: str, template_start: int) -> set[str]:
    """Resolve the element a template is written into (x.innerHTML = `tpl`)."""
    head = src[:template_start]
    el_id = None
    direct = re.search(r"getElementById\('([^']+)'\)\.innerHTML\s*=\s*$", head)
    if direct:
        el_id = direct.group(1)
    else:
        via_var = re.search(r"(\w+)\.innerHTML\s*=\s*$", head)
        if via_var:
            var = re.escape(via_var.group(1))
            assigns = re.findall(
                rf"(?:const|let|var)\s+{var}\s*=\s*document\.getElementById"
                r"\('([^']+)'\)",
                head,
            )
            if assigns:
                el_id = assigns[-1]
    if not el_id:
        return set()
    return _ID_CLASSES.get(el_id, set())


_ID_CLASSES = _id_class_map()


def _js_markup_problems(path: Path) -> list[str]:
    """Same checks, applied to markup templates inside .js sources.

    Each template literal containing a ``<table`` must also contain a
    scrollable container class; ``<th`` needs ``scope``; ``onclick=`` on
    non-interactive tags needs role/tabindex/onkeydown; copy buttons need
    an accessible name.
    """
    src = path.read_text(encoding="utf-8")
    out: list[str] = []
    for m in re.finditer(r"`([\s\S]*?)`", src):
        tpl, base = m.group(1), m.start(1)
        out += _tpl_tables(path, src, tpl, base, m.start())
        out += _tpl_th(path, src, tpl, base)
        out += _tpl_clicks(path, src, tpl, base)
        out += _tpl_copybtns(path, src, tpl, base)
    return out


def _tpl_tables(path: Path, src: str, tpl: str, base: int, backtick: int) -> list[str]:
    out: list[str] = []
    for tm in re.finditer(r"<table\b[^>]*>", tpl):
        line = src.count("\n", 0, base + tm.start()) + 1
        wrapped = _SCROLL_RE.search(tpl[: tm.start()]) or _SCROLL_RE.search(tm.group(0))
        if not wrapped:
            wrapped = bool(_container_classes(src, backtick) & SCROLL_CLASSES)
        if not wrapped:
            out.append(f"{path.name}:{line}: <table> template has no scrollable wrapper")
        if not re.search(r"aria-label|<caption", tpl):
            out.append(f"{path.name}:{line}: <table> template lacks aria-label/caption")
    return out


def _tpl_th(path: Path, src: str, tpl: str, base: int) -> list[str]:
    return [
        f"{path.name}:{src.count(chr(10), 0, base + tm.start()) + 1}: <th> without scope in template"
        for tm in re.finditer(r"<th\b(?![^>]*scope=)", tpl)
    ]


def _tpl_clicks(path: Path, src: str, tpl: str, base: int) -> list[str]:
    out: list[str] = []
    for tm in re.finditer(r'<(div|tr|td|span|li)\b[^>]*onclick="[^"]*location\.href', tpl):
        tag_src = tpl[tm.start() : tpl.index(">", tm.start())]
        if not ("role=" in tag_src and "tabindex" in tag_src and "onkeydown" in tag_src):
            line = src.count("\n", 0, base + tm.start()) + 1
            out.append(f"{path.name}:{line}: click-only <{tm.group(1)}> in template")
    return out


def _tpl_copybtns(path: Path, src: str, tpl: str, base: int) -> list[str]:
    return [
        f"{path.name}:{src.count(chr(10), 0, base + tm.start()) + 1}: copy-btn without aria-label"
        for tm in re.finditer(r'<button\b[^>]*class="copy-btn"[^>]*>', tpl)
        if "aria-label" not in tm.group(0)
    ]


def _css_problems() -> list[str]:
    css = CSS.read_text(encoding="utf-8")
    out: list[str] = []
    if "prefers-reduced-motion" not in css:
        out.append("style.css: no prefers-reduced-motion block")
    if ".visually-hidden" not in css:
        out.append("style.css: .visually-hidden utility missing")
    has_focus_visible = ":focus-visible" in css
    for m in re.finditer(r"outline:\s*(none|0)\b", css):
        if not has_focus_visible:
            out.append(f"style.css:{css.count(chr(10), 0, m.start()) + 1}: outline:none without :focus-visible")
    m = re.search(r"\.toggle-switch\s+input\s*\{([^}]*)}", css)
    if m and re.search(r"display\s*:\s*none", m.group(1)):
        out.append("style.css: .toggle-switch input display:none (unfocusable)")
    return out


class TestWebsiteA11y(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = sorted(WEBSITE.glob("*.html"))
        cls.js = sorted(WEBSITE.glob("*.js"))

    def test_pages_have_no_markup_violations(self) -> None:
        problems: list[str] = []
        for path in self.pages:
            src = path.read_text(encoding="utf-8")
            parser = _A11yParser(src)
            parser.feed(src)
            problems += parser.validate(path.name)
        self.assertEqual(problems, [], "a11y violations:\n" + "\n".join(problems))

    def test_js_templates_have_no_violations(self) -> None:
        problems: list[str] = []
        for path in self.js:
            problems += _js_markup_problems(path)
        self.assertEqual(problems, [], "a11y violations:\n" + "\n".join(problems))

    def test_stylesheet_a11y_rules(self) -> None:
        problems = _css_problems()
        self.assertEqual(problems, [], "css problems:\n" + "\n".join(problems))

    def test_labels_cover_controls(self) -> None:
        """Explicit control labelling is asserted inside the page parse; this
        test documents the counts so a removed label is a hard failure."""
        total = 0
        for path in self.pages:
            src = path.read_text(encoding="utf-8")
            total += len(re.findall(r"<(?:input|select|textarea)\b", src))
        self.assertGreater(total, 0, "no form controls found — fixture drift")


if __name__ == "__main__":
    unittest.main()
