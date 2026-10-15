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
        if tag == "div" and self._nav_class is None:
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
        if tag == "div" and self._nav_class is not None:
            # The nav blocks contain no nested divs: the first </div> closes it.
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


if __name__ == "__main__":
    unittest.main()
