"""Guard: every website page carries the same canonical header menu.

The pages under ``website/`` are served statically by nginx straight from the
checkout. Each page used to hand-write its own ``header-nav`` block and omit
the link to itself, so the menu's order and membership drifted between pages.
This test parses every ``website/*.html`` and asserts:

1. Every page has exactly one ``header-nav`` block whose links match the
   canonical menu (same items, same order) — unless the page is in
   ``NO_MENU_PAGES`` (explicit allowlist for menu-less pages).
2. ``aria-current="page"`` appears exactly once on a page when that page is
   part of the canonical menu or owns a secondary nav (the two dashboards),
   and the marked link points at the page's own path. Pages that are not
   represented in either nav (explorer sub-pages like block/tx/search/blocks)
   must carry no ``aria-current`` — marking another item would misreport the
   current page.
3. ``scripts/ops/sync-website-menu.py --check`` exits 0 — the stamped marker
   regions have not drifted from the generator's canonical output.

Failure messages print the page name and a unified diff of the link lists.
"""

from __future__ import annotations

import difflib
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"
GENERATOR = REPO / "scripts" / "ops" / "sync-website-menu.py"

# Keep in sync with sync-website-menu.py — the script is the source of truth
# for what gets stamped; this list is what gets asserted.
CANONICAL_MENU = [
    ("/", "Home"),
    ("/exchange.html", "Exchange"),
    ("/explorer.html", "Explorer"),
    ("/marketplace.html", "Marketplace"),
    ("/bridges.html", "Bridges"),
    ("/alerts.html", "Alerts"),
]
DASHBOARD_MENU = [
    ("/customer-dashboard.html", "Customer Dashboard"),
    ("/shop-dashboard.html", "Shop Dashboard"),
]
NO_MENU_PAGES = {"follower-api-key-announcement.html"}
DASHBOARD_PAGES = {"customer-dashboard.html", "shop-dashboard.html"}


def own_path(page: str) -> str:
    return "/" if page == "index.html" else f"/{page}"


class _NavParser(HTMLParser):
    """Collects <a> elements grouped by the nav block that contains them."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[str] = []  # element names, innermost last
        self._nav_class: str | None = None  # class of the nav block we're inside
        self.navs: dict[str, list[dict]] = {"header-nav": [], "dashboard-nav": []}
        self.aria_currents: list[str] = []
        self._in_a = False
        self._a_href = ""
        self._a_current = False
        self._a_classes: list[str] = []
        self._a_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack.append(tag)
        attr = dict(attrs)
        classes = (attr.get("class") or "").split()
        if tag in ("div", "nav") and self._nav_class is None:
            for nav in self.navs:
                if nav in classes:
                    self._nav_class = nav
                    break
        if tag == "a":
            self._in_a = True
            self._a_href = attr.get("href") or ""
            self._a_current = attr.get("aria-current") == "page"
            self._a_classes = classes
            self._a_text = []
            if self._a_current:
                self.aria_currents.append(self._a_href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_a:
            self._in_a = False
            if self._nav_class is not None:
                self.navs[self._nav_class].append(
                    {
                        "href": self._a_href,
                        "text": "".join(self._a_text).strip(),
                        "current": self._a_current,
                        "classes": self._a_classes,
                    }
                )
        if tag in ("div", "nav") and self._nav_class is not None:
            # The nav blocks contain no nested containers: the first close
            # tag of the same name ends the block.
            self._nav_class = None
        while self._stack and self._stack.pop() != tag:
            pass

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._a_text.append(data)


def _diff(expected: list[tuple[str, str]], got: list[tuple[str, str]]) -> str:
    exp = [f"{href}  {label}" for href, label in expected]
    act = [f"{href}  {label}" for href, label in got]
    return "\n".join(difflib.unified_diff(exp, act, fromfile="canonical", tofile="page", lineterm=""))


class TestWebsiteMenuConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = {p.name: p for p in sorted(WEBSITE.glob("*.html"))}
        cls.parsed: dict[str, _NavParser] = {}
        for name, path in cls.pages.items():
            parser = _NavParser()
            parser.feed(path.read_text(encoding="utf-8"))
            cls.parsed[name] = parser

    def test_every_page_has_the_menu_unless_allowlisted(self) -> None:
        for name, parser in self.parsed.items():
            links = [(a["href"], a["text"]) for a in parser.navs["header-nav"]]
            if name in NO_MENU_PAGES:
                self.assertEqual([], links, f"{name} is allowlisted as menu-less but has a header-nav: {links}")
                continue
            self.assertEqual(
                CANONICAL_MENU,
                links,
                f"{name}: menu drifted\n{_diff(CANONICAL_MENU, links)}",
            )

    def test_exactly_one_aria_current_marking_the_own_page(self) -> None:
        for name, parser in self.parsed.items():
            if name in NO_MENU_PAGES:
                continue
            currents = parser.aria_currents
            if name in {p for p in self.pages if own_path(p) in dict(CANONICAL_MENU)}:
                self.assertEqual(
                    [own_path(name)],
                    currents,
                    f"{name}: expected aria-current on its own menu link {own_path(name)!r}, found {currents}",
                )
            elif name in DASHBOARD_PAGES:
                # The main menu holds no dashboard item; the current marker
                # lives in the secondary dashboard-nav row.
                main = parser.navs["header-nav"]
                self.assertFalse(
                    any(a["current"] for a in main),
                    f"{name}: main menu must not mark a dashboard as current",
                )
                dash = parser.navs["dashboard-nav"]
                self.assertEqual(
                    [(a["href"], a["text"]) for a in dash],
                    DASHBOARD_MENU,
                    f"{name}: dashboard-nav drifted\n" + _diff(DASHBOARD_MENU, [(a["href"], a["text"]) for a in dash]),
                )
                self.assertEqual(
                    [own_path(name)],
                    currents,
                    f"{name}: expected aria-current on {own_path(name)!r} in dashboard-nav, found {currents}",
                )
            else:
                # Explorer sub-pages etc.: not represented in the menu, so no
                # item may claim to be the current page.
                self.assertEqual(
                    [],
                    currents,
                    f"{name}: aria-current without a matching menu item: {currents}",
                )

    def test_current_link_carries_is_current_class(self) -> None:
        for name, parser in self.parsed.items():
            for nav, links in parser.navs.items():
                for a in links:
                    if a["current"]:
                        self.assertIn(
                            "is-current",
                            a["classes"],
                            f"{name}: aria-current link lacks .is-current in {nav}",
                        )
                    elif a["href"] == own_path(name):
                        self.fail(f"{name}: own link in {nav} is not marked aria-current")

    def test_generator_check_mode_reports_no_drift(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check", "--root", str(REPO)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            0,
            result.returncode,
            f"sync-website-menu.py --check reported drift:\n{result.stdout}\n{result.stderr}",
        )


# Pages listed in website/sitemap.xml get a <link rel="canonical">; dynamic
# detail pages are deliberately excluded and carry noindex instead.
SITEMAP_PAGES = {
    "index.html": "https://hub.aitbc.bubuit.net/",
    "explorer.html": "https://hub.aitbc.bubuit.net/explorer.html",
    "blocks.html": "https://hub.aitbc.bubuit.net/blocks.html",
    "marketplace.html": "https://hub.aitbc.bubuit.net/marketplace.html",
    "exchange.html": "https://hub.aitbc.bubuit.net/exchange.html",
    "bridges.html": "https://hub.aitbc.bubuit.net/bridges.html",
    "alerts.html": "https://hub.aitbc.bubuit.net/alerts.html",
    "customer-dashboard.html": "https://hub.aitbc.bubuit.net/customer-dashboard.html",
    "shop-dashboard.html": "https://hub.aitbc.bubuit.net/shop-dashboard.html",
    "follower-api-key-announcement.html": "https://hub.aitbc.bubuit.net/follower-api-key-announcement.html",
}
DYNAMIC_PAGES = {"block.html", "tx.html", "search.html"}
# Title exceptions to the "<Page name> — AITBC" pattern (index keeps its
# descriptive title for discovery — operator decision, WEB-2 ASK).
TITLE_EXCEPTIONS = {"index.html"}
DESCRIPTION_ALLOWLIST: set[str] = set()


class _HygieneParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.viewport = False
        self.charset = False
        self.lang = ""
        self.description = False
        self.noindex = False
        self.canonicals: list[str] = []
        self.mains: list[dict] = []
        self.main_navs = 0
        self.first_link: dict | None = None
        self.skip_links = 0

    def _meta(self, attr: dict) -> None:
        if attr.get("charset") is not None:
            self.charset = True
        if attr.get("name") == "viewport":
            self.viewport = True
        if attr.get("name") == "description":
            self.description = True
        if attr.get("name") == "robots" and "noindex" in (attr.get("content") or ""):
            self.noindex = True

    def _link(self, attr: dict) -> None:
        if attr.get("rel") == "canonical":
            self.canonicals.append(attr.get("href") or "")

    def _anchor(self, attr: dict) -> None:
        if "skip-link" in (attr.get("class") or "").split():
            self.skip_links += 1
        if self.first_link is None and attr.get("href"):
            self.first_link = attr

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "html":
            self.lang = attr.get("lang", "")
        elif tag == "meta":
            self._meta(attr)
        elif tag == "title":
            self._in_title = True
        elif tag == "link":
            self._link(attr)
        elif tag == "main":
            self.mains.append(attr)
        elif tag == "nav" and attr.get("aria-label") == "Main":
            self.main_navs += 1
        elif tag == "a":
            self._anchor(attr)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


class TestWebsiteHygiene(unittest.TestCase):
    """WEB-2: landmark/head hygiene across every website page."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.parsed: dict[str, _HygieneParser] = {}
        for path in sorted(WEBSITE.glob("*.html")):
            parser = _HygieneParser()
            parser.feed(path.read_text(encoding="utf-8"))
            cls.parsed[path.name] = parser

    def test_head_basics(self) -> None:
        for name, p in self.parsed.items():
            self.assertEqual("en", p.lang, f"{name}: <html lang> is {p.lang!r}, expected 'en'")
            self.assertTrue(p.charset, f"{name}: missing <meta charset>")
            self.assertTrue(p.viewport, f'{name}: missing <meta name="viewport">')

    def test_one_main_with_id_and_tabindex(self) -> None:
        for name, p in self.parsed.items():
            self.assertEqual(1, len(p.mains), f"{name}: expected exactly one <main>, found {len(p.mains)}")
            self.assertEqual("main", p.mains[0].get("id"), f'{name}: <main> lacks id="main"')
            self.assertEqual("-1", p.mains[0].get("tabindex"), f'{name}: <main> lacks tabindex="-1"')

    def test_one_main_nav_unless_allowlisted(self) -> None:
        for name, p in self.parsed.items():
            expected = 0 if name in NO_MENU_PAGES else 1
            self.assertEqual(
                expected, p.main_navs, f'{name}: expected {expected} <nav aria-label="Main">, found {p.main_navs}'
            )

    def test_skip_link_is_first_focusable(self) -> None:
        for name, p in self.parsed.items():
            self.assertEqual(1, p.skip_links, f"{name}: expected exactly one .skip-link, found {p.skip_links}")
            self.assertIsNotNone(p.first_link, f"{name}: no <a href> at all")
            self.assertEqual(
                "#main",
                p.first_link.get("href"),
                f"{name}: first focusable link is {p.first_link.get('href')!r}, expected '#main' (skip link first)",
            )
            self.assertIn(
                "skip-link",
                (p.first_link.get("class") or "").split(),
                f"{name}: first link is not the skip link",
            )

    def test_meta_description(self) -> None:
        for name, p in self.parsed.items():
            if name in DESCRIPTION_ALLOWLIST:
                continue
            self.assertTrue(p.description, f'{name}: missing <meta name="description">')

    def test_title_pattern(self) -> None:
        for name, p in self.parsed.items():
            if name in TITLE_EXCEPTIONS:
                continue
            self.assertRegex(
                p.title.strip(),
                r"^\S.* — AITBC$",
                f"{name}: title {p.title.strip()!r} does not match '<Page name> — AITBC'",
            )

    def test_canonical_exactly_on_sitemap_pages(self) -> None:
        for name, p in self.parsed.items():
            if name in SITEMAP_PAGES:
                self.assertEqual(
                    [SITEMAP_PAGES[name]],
                    p.canonicals,
                    f"{name}: expected canonical {SITEMAP_PAGES[name]!r}, found {p.canonicals}",
                )
            else:
                self.assertEqual([], p.canonicals, f"{name}: dynamic page must not carry canonical: {p.canonicals}")

    def test_noindex_on_dynamic_pages(self) -> None:
        for name, p in self.parsed.items():
            if name in DYNAMIC_PAGES:
                self.assertTrue(p.noindex, f'{name}: dynamic page missing <meta name="robots" content="noindex">')
            else:
                self.assertFalse(p.noindex, f"{name}: unexpected noindex")


if __name__ == "__main__":
    unittest.main()
