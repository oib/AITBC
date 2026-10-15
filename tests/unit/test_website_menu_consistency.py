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
import re
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
    ("/messages.html", "Messages"),
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
DYNAMIC_PAGES = {"block.html", "tx.html", "search.html", "messages.html"}
# Title exceptions to the "<Page name> — AITBC" pattern (index keeps its
# descriptive title for discovery — operator decision, WEB-2 ASK).
TITLE_EXCEPTIONS = {"index.html"}
DESCRIPTION_ALLOWLIST: set[str] = set()


NGINX_CONF = REPO / "examples" / "nginx" / "nginx-aitbc.conf.example"
STATUS_JS = WEBSITE / "status.js"
EXPECTED_FOOTER = [
    ("https://github.com/oib/AITBC", "GitHub"),
    ("/llms.txt", "llms.txt"),
    ("/openapi.json", "Coordinator API"),
    ("/explorer-api/openapi.json", "Explorer API"),
]


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
        self.status_strips: list[dict] = []
        self.footer_links: list[tuple[str, str]] = []
        self.footer_count = 0
        self._in_footer = False
        self._footer_link: str | None = None
        self._footer_text: list[str] = []
        self.scripts: list[dict] = []
        self.cdn_refs: list[str] = []

    def _meta(self, attr: dict) -> None:
        if attr.get("charset") is not None:
            self.charset = True
        if attr.get("name") == "viewport":
            self.viewport = True
        if attr.get("name") == "description":
            self.description = True
        if attr.get("name") == "robots" and "noindex" in (attr.get("content") or ""):
            self.noindex = True

    def _anchor(self, attr: dict) -> None:
        if "skip-link" in (attr.get("class") or "").split():
            self.skip_links += 1
        if self._in_footer:
            self._footer_link = attr.get("href") or ""
            self._footer_text = []
        if self.first_link is None and attr.get("href"):
            self.first_link = attr

    def _script(self, attr: dict) -> None:
        src = attr.get("src") or ""
        self.scripts.append({"src": src, "defer": "defer" in attr})
        if src.startswith(("http://", "https://", "//")):
            self.cdn_refs.append(src)

    def _link(self, attr: dict) -> None:
        if attr.get("rel") == "canonical":
            self.canonicals.append(attr.get("href") or "")
        href = attr.get("href") or ""
        if attr.get("rel") in ("stylesheet", "preconnect", "preload") and href.startswith(("http://", "https://", "//")):
            self.cdn_refs.append(href)

    def _tag_html(self, attr: dict) -> None:
        self.lang = attr.get("lang", "")

    def _tag_meta(self, attr: dict) -> None:
        self._meta(attr)

    def _tag_title(self, attr: dict) -> None:
        self._in_title = True

    def _tag_link(self, attr: dict) -> None:
        self._link(attr)

    def _tag_main(self, attr: dict) -> None:
        self.mains.append(attr)

    def _tag_nav(self, attr: dict) -> None:
        if attr.get("aria-label") == "Main":
            self.main_navs += 1

    def _tag_a(self, attr: dict) -> None:
        self._anchor(attr)

    def _tag_div(self, attr: dict) -> None:
        if "status-strip" in (attr.get("class") or "").split():
            self.status_strips.append(attr)

    def _tag_footer(self, attr: dict) -> None:
        self.footer_count += 1
        self._in_footer = True

    def _tag_script(self, attr: dict) -> None:
        self._script(attr)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        handler = getattr(self, f"_tag_{tag}", None)
        if handler is not None:
            handler(dict(attrs))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "footer":
            self._in_footer = False
        elif tag == "a" and self._footer_link is not None:
            self.footer_links.append((self._footer_link, "".join(self._footer_text).strip()))
            self._footer_link = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._in_footer and self._footer_link is not None:
            self._footer_text.append(data)


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


class TestStatusStripAndFooter(unittest.TestCase):
    """WEB-3: status strip + footer invariants across every website page."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.parsed: dict[str, _HygieneParser] = {}
        for path in sorted(WEBSITE.glob("*.html")):
            parser = _HygieneParser()
            parser.feed(path.read_text(encoding="utf-8"))
            cls.parsed[path.name] = parser

    def test_status_strip_on_menu_pages(self) -> None:
        for name, p in self.parsed.items():
            if name in NO_MENU_PAGES:
                self.assertEqual(0, len(p.status_strips), f"{name}: menu-less page must not carry the strip")
                continue
            self.assertEqual(1, len(p.status_strips), f"{name}: expected one .status-strip, found {len(p.status_strips)}")
            strip = p.status_strips[0]
            self.assertEqual("status", strip.get("role"), f'{name}: strip lacks role="status"')
            self.assertEqual("polite", strip.get("aria-live"), f'{name}: strip lacks aria-live="polite"')

    def test_status_js_deferred_on_menu_pages(self) -> None:
        for name, p in self.parsed.items():
            status = [s for s in p.scripts if s["src"].split("?")[0].endswith("status.js")]
            if name in NO_MENU_PAGES:
                self.assertEqual([], status, f"{name}: menu-less page must not load status.js")
                continue
            self.assertEqual(1, len(status), f"{name}: expected status.js once, found {len(status)}")
            self.assertTrue(status[0]["defer"], f"{name}: status.js must load with defer")

    def test_no_cdn_resources(self) -> None:
        for name, p in self.parsed.items():
            self.assertEqual([], p.cdn_refs, f"{name}: external script/stylesheet refs found: {p.cdn_refs}")

    def test_identical_footer(self) -> None:
        for name, p in self.parsed.items():
            self.assertEqual(1, p.footer_count, f"{name}: expected exactly one <footer>, found {p.footer_count}")
            self.assertEqual(
                EXPECTED_FOOTER,
                p.footer_links,
                f"{name}: footer links differ\n{_diff(EXPECTED_FOOTER, p.footer_links)}",
            )

    def test_status_js_same_origin_and_paths(self) -> None:
        src = STATUS_JS.read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"https?://|\b\d{1,3}(?:\.\d{1,3}){3}\b", src),
            "status.js must not hard-code hosts or IPs",
        )
        paths = re.findall(r"""getJSON\(\s*['"]([^'"]+)['"]""", src)
        self.assertTrue(paths, "status.js: no getJSON call sites found")
        for pth in paths:
            self.assertTrue(
                pth.startswith("/") and not pth.startswith("//"),
                f"status.js path not same-origin-relative: {pth}",
            )

    def test_status_js_endpoints_exist_in_nginx_map(self) -> None:
        conf = NGINX_CONF.read_text(encoding="utf-8")
        prefixes = re.findall(r"location\s+(?:~\s+\S+\s+|=?\s*)(/\S*)", conf)
        src = STATUS_JS.read_text(encoding="utf-8")
        for pth in re.findall(r"""getJSON\(\s*['"]([^'"]+)['"]""", src):
            self.assertTrue(
                any(pth.startswith(prefix) for prefix in prefixes),
                f"status.js calls {pth} — no matching location prefix in {NGINX_CONF.name}: {prefixes}",
            )


if __name__ == "__main__":
    unittest.main()
