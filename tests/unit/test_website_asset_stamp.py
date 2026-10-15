"""Guard: every local website asset reference carries the common ``?v=`` stamp.

``style.css``/``*.js`` are served with ``Cache-Control: max-age=3600`` and the
browser cache key includes the query string, so a shared content-hash stamp is
what actually busts stale assets after a deploy (WEB-FIX-1 W6). This test
asserts:

1. ``scripts/ops/stamp-website-assets.py --check`` exits 0 — the committed
   pages match what the generator would write (no drift).
2. Every ``<script src>``/``<img|source src>``/``<link href>`` reference that
   resolves to a file under ``website/`` carries ``?v=<stamp>`` — and all of
   them use the *same* stamp, equal to the generator's content hash.
3. The stamp is content-derived: perturbing an asset's bytes changes it (a
   deploy that changes ``style.css`` therefore changes every ``?v=``).
4. Anchor ``<a href>`` navigations and external/API URLs are never stamped —
   the stamp is for subresource cache keys, not for mangling links.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"
GENERATOR = REPO / "scripts" / "ops" / "stamp-website-assets.py"

sys.path.insert(0, str(GENERATOR.parent))
import importlib

stamp_mod = importlib.import_module("stamp-website-assets")


class _AssetParser(HTMLParser):
    """Collects subresource references: src= on script/img/source, href= on link."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.subresource_refs: list[tuple[str, str]] = []  # (tag.attr, url)
        self.anchor_refs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag in ("script", "img", "source") and attr.get("src"):
            self.subresource_refs.append((f"{tag}.src", attr["src"]))
        elif tag == "link" and attr.get("href"):
            self.subresource_refs.append(("link.href", attr["href"]))
        elif tag == "a" and attr.get("href"):
            self.anchor_refs.append(attr["href"])


def _is_local(url: str) -> Path | None:
    return stamp_mod._local_asset(WEBSITE, url)


class TestWebsiteAssetStamp(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = {p.name: p for p in sorted(WEBSITE.glob("*.html"))}
        cls.refs: dict[str, list[tuple[str, str]]] = {}
        cls.anchors: dict[str, list[str]] = {}
        for name, path in cls.pages.items():
            parser = _AssetParser()
            parser.feed(path.read_text(encoding="utf-8"))
            cls.refs[name] = parser.subresource_refs
            cls.anchors[name] = parser.anchor_refs
        cls.stamp = stamp_mod.asset_stamp(WEBSITE)

    def test_generator_check_mode_reports_no_drift(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check", "--root", str(REPO)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            0,
            result.returncode,
            f"stamp-website-assets.py --check reported drift:\n{result.stdout}\n{result.stderr}",
        )

    def test_every_local_asset_ref_carries_the_common_stamp(self) -> None:
        want = f"?v={self.stamp}"
        bad: list[str] = []
        seen_values: set[str] = set()
        for name, refs in self.refs.items():
            for where, url in refs:
                if _is_local(url) is None:
                    continue  # external or API path — not stamped
                m = re.search(r"[?&]v=([^&]+)", url)
                if m:
                    seen_values.add(m.group(1))
                if f"?v={self.stamp}" not in url:
                    bad.append(f"{name}: {where}={url!r} (want {want})")
        self.assertEqual([], bad, "local asset refs missing/wrong stamp:\n" + "\n".join(bad))
        self.assertEqual({self.stamp}, seen_values, f"refs carry differing stamps: {seen_values}")

    def test_stamp_changes_when_an_asset_changes(self) -> None:
        # Copy the website dir to a temp tree, perturb one asset, and assert
        # the content hash differs — the mechanism that busts stale caches.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "website"
            tmp.mkdir()
            for p in WEBSITE.rglob("*"):
                if p.is_file() and p.suffix in stamp_mod.STAMP_EXTENSIONS:
                    dest = tmp / p.relative_to(WEBSITE)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(p.read_bytes())
            before = stamp_mod.asset_stamp(tmp)
            victim = tmp / "style.css"
            victim.write_bytes(victim.read_bytes() + b"/* drift */")
            after = stamp_mod.asset_stamp(tmp)
        self.assertNotEqual(before, after, "content hash must change when an asset's bytes change")
        self.assertEqual(self.stamp, before, "temp copy of identical assets must hash identically")

    def test_anchors_and_external_urls_are_not_stamped(self) -> None:
        bad: list[str] = []
        for name, hrefs in self.anchors.items():
            for href in hrefs:
                if "v=" in href:
                    bad.append(f"{name}: <a href={href!r}> carries a stamp")
        self.assertEqual([], bad, "anchor navigations must not carry ?v=:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
