#!/usr/bin/env python3
"""Stamp one common ``?v=<content hash>`` on every local website asset reference.

``.css``/``.js`` references carrying a full 16-hex stamp are served with
``Cache-Control: max-age=31536000, immutable`` (one year); a bare, short or
malformed ``?v`` falls back to ``max-age=3600``. The browser cache key
includes the query string, so changing ``?v`` is what
busts a stale stylesheet or script after a deploy. The pages historically
carried a mix of hand-bumped versions (``?v=11`` .. ``?v=13``) and
unversioned references — a visitor could get yesterday's JS against today's
HTML. This script keeps every local asset reference on every page carrying
the *same* ``?v=<stamp>``, where ``<stamp>`` is a content hash of the
stampable asset surface under ``website/``:

- hashed files: ``website/**/*.css``, ``website/**/*.js``,
  ``website/**/*.svg`` — anything whose bytes reach the browser as a
  subresource. Editing any of them changes the stamp, so all pages restamp
  together (one deploy = one new cache key).
- stamped references: ``src=`` on ``<script>/<img>/<source>`` and ``href=``
  on ``<link>`` — i.e. subresource *loads* — whose target resolves to a
  file under ``website/``. Anchor ``<a href>`` navigations, API paths and
  absolute ``https://`` URLs are never touched.

Same contract as ``sync-website-menu.py``:

    (default)   rewrite ``?v=`` in place; print changed files
    --check     exit non-zero and print a per-page diff when the committed
                files differ from what the script would write

The guard test ``tests/unit/test_website_asset_stamp.py`` runs ``--check``
and verifies the shared value. To restamp after an asset change: run this
script once, commit the diff.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import sys
from pathlib import Path

STAMP_EXTENSIONS = {".css", ".js", ".svg"}
STAMP_LEN = 16
STAMPED_TAGS = ("script", "img", "source")

TAG_RE = re.compile(r"<(?P<tag>script|img|source|link)\b[^>]*>", re.I)
ATTR_RE = re.compile(r'(?P<attr>src|href)=(?P<q>["\'])(?P<url>[^"\']*)(?P=q)', re.I)
V_RE = re.compile(r"([?&])v=[^&]*")


def asset_stamp(website: Path) -> str:
    """Content hash of the stampable asset surface under ``website/``."""
    h = hashlib.sha256()
    files = sorted(p for p in website.rglob("*") if p.is_file() and p.suffix in STAMP_EXTENSIONS)
    for p in files:
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:STAMP_LEN]


def _local_asset(website: Path, url: str) -> Path | None:
    """Resolve a reference target to a file under ``website/``, or None."""
    if url.startswith(("http://", "https://", "//", "data:", "#", "mailto:")):
        return None
    path = url.split("?", 1)[0].split("#", 1)[0].lstrip("/")
    if not path:
        return None
    parts = Path(path).parts
    if ".." in parts:
        return None
    cand = website / path
    # is_file() follows symlinks on purpose: website/favicon.svg is a
    # committed relative symlink to AITBC.svg and stays inside the checkout —
    # the link is the repo object, the web path is local either way.
    return cand if cand.is_file() else None


def _stamp_url(url: str, stamp: str) -> str:
    if "?" in url:
        return V_RE.sub(rf"\g<1>v={stamp}", url, count=1) if V_RE.search(url) else url + f"&v={stamp}"
    return url + f"?v={stamp}"


def _stamp_tag(tag_html: str, tag: str, website: Path, stamp: str) -> str:
    def repl(m: re.Match[str]) -> str:
        attr = m.group("attr").lower()
        if tag == "link" and attr != "href":
            return m.group(0)
        if tag != "link" and attr != "src":
            return m.group(0)
        url = m.group("url")
        if _local_asset(website, url) is None:
            return m.group(0)
        return f"{m.group('attr')}={m.group('q')}{_stamp_url(url, stamp)}{m.group('q')}"

    return ATTR_RE.sub(repl, tag_html)


def expected_content(path: Path, website: Path, stamp: str) -> str:
    text = path.read_text(encoding="utf-8")
    return TAG_RE.sub(lambda m: _stamp_tag(m.group(0), m.group("tag").lower(), website, stamp), text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report drift, change nothing")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = ap.parse_args()

    website = args.root / "website"
    stamp = asset_stamp(website)
    drift: list[str] = []
    for page in sorted(website.glob("*.html")):
        old = page.read_text(encoding="utf-8")
        new = expected_content(page, website, stamp)
        if new == old:
            continue
        if args.check:
            diff = difflib.unified_diff(
                old.splitlines(),
                new.splitlines(),
                fromfile=page.name,
                tofile=f"{page.name} (expected)",
                lineterm="",
            )
            drift.append("\n".join(diff))
        else:
            page.write_text(new, encoding="utf-8")
            drift.append(f"{page.name}: restamped")

    if drift:
        print("\n".join(drift))
        return 1 if args.check else 0
    print(f"All website asset references at v={stamp}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
