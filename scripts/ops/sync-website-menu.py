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

LEGACY_NAV_RE = re.compile(
    r'^(?P<i>[ \t]*)<div class="header-nav">\s*\n(?P<body>.*?)^(?P=i)</div>[ \t]*\n?',
    re.M | re.S,
)


def own_path(name: str) -> str:
    return "/" if name == "index.html" else f"/{name}"


def nav_block(mark: str, div_class: str, items: list[tuple[str, str]], current: str | None, aria: str) -> str:
    lines = [f"{INDENT}<!-- {mark}:start -->", f'{INDENT}<div class="{div_class}"{aria}>']
    for href, label in items:
        if href == current:
            lines.append(f'{INDENT}    <a href="{href}" class="is-current" aria-current="page">{label}</a>')
        else:
            lines.append(f'{INDENT}    <a href="{href}">{label}</a>')
    lines += [f"{INDENT}</div>", f"{INDENT}<!-- {mark}:end -->"]
    return "\n".join(lines) + "\n"


def marked_region(mark: str) -> re.Pattern[str]:
    return re.compile(
        rf"{INDENT}<!-- {mark}:start -->\n.*?{INDENT}<!-- {mark}:end -->\n?",
        re.S,
    )


def stamp_main_menu(text: str, name: str) -> str:
    block = nav_block(MENU_MARK, "header-nav", MENU, own_path(name), "")
    if marked_region(MENU_MARK).search(text):
        return marked_region(MENU_MARK).sub(block, text, count=1)
    m = LEGACY_NAV_RE.search(text)
    if m:
        return text[: m.start()] + block + text[m.end() :]
    return text


def stamp_dashboard_row(text: str, name: str) -> str:
    block = nav_block(DASH_MARK, "dashboard-nav", DASHBOARD_MENU, own_path(name), ' aria-label="Dashboards"')
    if marked_region(DASH_MARK).search(text):
        return marked_region(DASH_MARK).sub(block, text, count=1)
    if name in DASHBOARD_PAGES:
        end = f"{INDENT}<!-- {MENU_MARK}:end -->\n"
        idx = text.find(end)
        if idx < 0:
            raise ValueError(f"{name}: dashboard page without a stamped main menu")
        return text[: idx + len(end)] + block + text[idx + len(end) :]
    return text


def expected_content(path: Path) -> str:
    name = path.name
    if name in NO_MENU_PAGES:
        return path.read_text(encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    if "header-nav" not in text and f"<!-- {MENU_MARK}:start -->" not in text:
        raise ValueError(f"{name}: no menu and not in NO_MENU_PAGES")
    return stamp_dashboard_row(stamp_main_menu(text, name), name)


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
