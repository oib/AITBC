#!/usr/bin/env python3
"""Stamp the canonical header menu into every website page.

The pages under ``website/`` are static files served by nginx straight from
the checkout; crawlers and agents read the raw HTML, so the menu must exist
in the markup itself — no JS rendering. This script keeps every page's menu
byte-identical by rewriting marked regions only:

    <!-- aitbc-menu:start -->            main menu (every page with a menu)
    ...generated block...
    <!-- aitbc-menu:end -->

    <!-- aitbc-dashboard-menu:start -->  secondary row (dashboard pages only)
    ...generated block...
    <!-- aitbc-dashboard-menu:end -->

    <!-- aitbc-skip:start -->            skip link (every page, incl. menu-less)
    ...generated block...
    <!-- aitbc-skip:end -->

To change the menu: edit ``MENU`` (or ``DASHBOARD_MENU``) below and run this
script once; commit the resulting diff. The guard test
``tests/unit/test_website_menu_consistency.py`` runs ``--check`` and fails
when any page drifts from the canonical block.

Modes:
    (default)   rewrite marked regions in place; print changed files
    --check     exit non-zero and print a per-page diff when the committed
                files differ from what the script would write; writes nothing

Migration: a page with a legacy hand-written ``<div class="header-nav">``
block (no markers) has that block replaced wholesale. A dashboard page with
no secondary-row markers gets the row inserted right after the main menu.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

INDENT = " " * 12  # header children sit at this depth on every page

MENU = [
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
DASHBOARD_PAGES = {"customer-dashboard.html", "shop-dashboard.html"}
NO_MENU_PAGES = {"follower-api-key-announcement.html"}

MENU_MARK = "aitbc-menu"
DASH_MARK = "aitbc-dashboard-menu"
SKIP_MARK = "aitbc-skip"
STATUS_MARK = "aitbc-status"
FOOTER_MARK = "aitbc-footer"

FOOTER_LINKS = [
    ("https://github.com/oib/AITBC", "GitHub"),
    ("/llms.txt", "llms.txt"),
    ("/openapi.json", "Coordinator API"),
    ("/explorer-api/openapi.json", "Explorer API"),
]

LEGACY_NAV_RE = re.compile(
    r'^(?P<i>[ \t]*)<div class="header-nav">\s*\n(?P<body>.*?)^(?P=i)</div>[ \t]*\n?',
    re.M | re.S,
)

BODY_RE = re.compile(r"^(?P<i>[ \t]*)<body[^>]*>\s*\n(?P<next>[ \t]*)\S", re.M)


def own_path(name: str) -> str:
    return "/" if name == "index.html" else f"/{name}"


def nav_block(mark: str, div_class: str, items: list[tuple[str, str]], current: str | None) -> str:
    label = "Main" if mark == MENU_MARK else "Dashboards"
    lines = [
        f"{INDENT}<!-- {mark}:start -->",
        f'{INDENT}<nav class="{div_class}" aria-label="{label}">',
    ]
    for href, text in items:
        if href == current:
            lines.append(f'{INDENT}    <a href="{href}" class="is-current" aria-current="page">{text}</a>')
        else:
            lines.append(f'{INDENT}    <a href="{href}">{text}</a>')
    lines += [f"{INDENT}</nav>", f"{INDENT}<!-- {mark}:end -->"]
    return "\n".join(lines) + "\n"


def skip_block(indent: str) -> str:
    return (
        f"{indent}<!-- {SKIP_MARK}:start -->\n"
        f'{indent}<a href="#main" class="skip-link">Skip to content</a>\n'
        f"{indent}<!-- {SKIP_MARK}:end -->\n"
    )


def status_block(indent: str) -> str:
    return (
        f"{indent}<!-- {STATUS_MARK}:start -->\n"
        f'{indent}<div class="status-strip" role="status" aria-live="polite"></div>\n'
        f"{indent}<!-- {STATUS_MARK}:end -->\n"
    )


def footer_block(indent: str) -> str:
    lines = [f"{indent}<!-- {FOOTER_MARK}:start -->", f'{indent}<footer class="site-footer">']
    for href, label in FOOTER_LINKS:
        lines.append(f'{indent}    <a href="{href}">{label}</a>')
    lines += [f"{indent}</footer>", f"{indent}<!-- {FOOTER_MARK}:end -->"]
    return "\n".join(lines) + "\n"


def marked_region(mark: str, indent: str = INDENT) -> re.Pattern[str]:
    return re.compile(
        rf"{indent}<!-- {mark}:start -->\n.*?{indent}<!-- {mark}:end -->\n?",
        re.S,
    )


def stamp_main_menu(text: str, name: str) -> str:
    block = nav_block(MENU_MARK, "header-nav", MENU, own_path(name))
    if marked_region(MENU_MARK).search(text):
        return marked_region(MENU_MARK).sub(block, text, count=1)
    m = LEGACY_NAV_RE.search(text)
    if m:
        return text[: m.start()] + block + text[m.end() :]
    return text


def stamp_dashboard_row(text: str, name: str) -> str:
    block = nav_block(DASH_MARK, "dashboard-nav", DASHBOARD_MENU, own_path(name))
    if marked_region(DASH_MARK).search(text):
        return marked_region(DASH_MARK).sub(block, text, count=1)
    if name in DASHBOARD_PAGES:
        end = f"{INDENT}<!-- {MENU_MARK}:end -->\n"
        idx = text.find(end)
        if idx < 0:
            raise ValueError(f"{name}: dashboard page without a stamped main menu")
        return text[: idx + len(end)] + block + text[idx + len(end) :]
    return text


def stamp_skip_link(text: str, name: str) -> str:
    m = re.search(r"(?P<i>[ \t]*)<!-- " + SKIP_MARK + r":start -->", text)
    if m:
        region = marked_region(SKIP_MARK, re.escape(m.group("i")))
        return region.sub(skip_block(m.group("i")), text, count=1)
    body = BODY_RE.search(text)
    if not body:
        raise ValueError(f"{name}: no <body> tag found for the skip link")
    line_end = text.find("\n", body.start()) + 1
    return text[:line_end] + skip_block(body.group("next")) + text[line_end:]


def stamp_status_strip(text: str, name: str) -> str:
    if marked_region(STATUS_MARK, "[ \t]*").search(text):
        m = re.search(r"(?P<i>[ \t]*)<!-- " + STATUS_MARK + ":start -->", text)
        region = marked_region(STATUS_MARK, re.escape(m.group("i")))
        return region.sub(status_block(m.group("i")), text, count=1)
    if name in NO_MENU_PAGES:
        return text
    m = re.search(r"(?P<i>[ \t]*)<main id=\"main\"", text)
    if not m:
        raise ValueError(f'{name}: page with a menu needs <main id="main"> before the status strip')
    return text[: m.start()] + status_block(m.group("i")) + "\n" + text[m.start() :]


def stamp_footer(text: str, name: str) -> str:
    m = re.search(r"(?P<i>[ \t]*)<!-- " + FOOTER_MARK + r":start -->", text)
    if m:
        region = marked_region(FOOTER_MARK, re.escape(m.group("i")))
        return region.sub(footer_block(m.group("i")), text, count=1)
    main_close = re.search(r"(?P<i>[ \t]*)</main>\n", text)
    if not main_close:
        raise ValueError(f"{name}: no </main> to hang the footer on")
    indent = main_close.group("i")
    return text[: main_close.end()] + footer_block(indent) + text[main_close.end() :]


def expected_content(path: Path) -> str:
    name = path.name
    text = stamp_skip_link(path.read_text(encoding="utf-8"), name)
    if name in NO_MENU_PAGES:
        return stamp_footer(text, name)
    if "header-nav" not in text and f"<!-- {MENU_MARK}:start -->" not in text:
        raise ValueError(f"{name}: no menu and not in NO_MENU_PAGES")
    return stamp_footer(stamp_status_strip(stamp_dashboard_row(stamp_main_menu(text, name), name), name), name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report drift, change nothing")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = ap.parse_args()

    website = args.root / "website"
    drift: list[str] = []
    for page in sorted(website.glob("*.html")):
        name = page.name
        try:
            new = expected_content(page)
        except ValueError as e:
            drift.append(f"{name}: {e}")
            continue
        old = page.read_text(encoding="utf-8")
        if new == old:
            continue
        if args.check:
            diff = difflib.unified_diff(
                old.splitlines(), new.splitlines(), fromfile=name, tofile=f"{name} (expected)", lineterm=""
            )
            drift.append("\n".join(diff))
        else:
            page.write_text(new, encoding="utf-8")
            drift.append(f"{name}: stamped")

    if drift:
        print("\n".join(drift))
        return 1 if args.check else 0
    print("All website menus up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
