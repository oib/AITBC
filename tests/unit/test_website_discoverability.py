"""WEB-8: content-accuracy / discoverability guard for the public hub site.

Offline checks over website/*.html, *.js, llms.txt, sitemap.xml, robots.txt:

1. Every internal link (href/src/action, same-origin relative or canonical
   host) resolves to an existing file in website/ or a path the reference
   nginx config would route to a backend (WEB-4's nginx model is reused).
2. Every URL in llms.txt exists under that model / as a file, and no page
   listed there is robots-disallowed.
3. sitemap.xml locs are on the canonical host, resolve to real files, and
   the sitemap set equals the set of pages carrying a canonical tag and no
   noindex robots meta.
4. Deny-list scan over shipped files: retired hostnames, gitea, RFC1918
   addresses, 64-hex strings, and 0x+40-hex strings outside an explicit
   allowlist.

Run: pytest tests/unit/test_website_discoverability.py
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_website_api_contract as api_contract

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"

CANONICAL_HOST = "https://hub.aitbc.bubuit.net"

DENY_RES = {
    "retired hostname hub2": re.compile(r"hub2\.aitbc", re.I),
    "gitea endpoint": re.compile(r"gitea\.bubuit\.net", re.I),
    "RFC1918 / loopback address": re.compile(
        r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b|\b127\.\d{1,3}\."
    ),
    "64-hex string": re.compile(r"\b(?:0x)?[0-9a-fA-F]{64}\b"),
    "ethereum-style address": re.compile(r"\b0x[0-9a-fA-F]{40}\b"),
}

# 0x+40-hex allowlist (value<TAB>reason). Public, documented constants only —
# never a wallet the operator controls unless already published as such.
HEX_ALLOWLIST: dict[str, str] = {}

SKIP_SCHEMES = ("mailto:", "javascript:", "data:", "tel:")


def _html_pages() -> list[Path]:
    return sorted(WEBSITE.glob("*.html"))


def _shipped_files() -> list[Path]:
    return [p for p in WEBSITE.iterdir() if p.is_file() and p.suffix in (".html", ".js", ".txt", ".xml", ".svg", ".css")]


def _nginx_locs():
    text = api_contract.NGINX_CONF.read_text(encoding="utf-8")
    locs, _default = api_contract.parse_nginx(text)
    return locs


def _link_targets(src: str):
    """(attr, value, line) for every href/src/action in HTML source."""
    for m in re.finditer(r'\b(href|src|action)\s*=\s*"([^"]*)"', src):
        yield m.group(1), m.group(2), src.count("\n", 0, m.start()) + 1


def _is_external_or_special(url: str) -> bool:
    if url.startswith(SKIP_SCHEMES) or url.startswith("#") or "${" in url:
        return True
    return bool(re.match(r"^https?://", url) and not url.startswith(CANONICAL_HOST))


def _canonical_path(url: str) -> str:
    """Strip canonical-host prefix and query; return the path part."""
    if url.startswith(CANONICAL_HOST):
        url = url[len(CANONICAL_HOST) :]
    return url.split("?", 1)[0].split("#", 1)[0] or "/"


def _robots_disallow(robots: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^Disallow:\s*(\S+)", robots, re.M)]


def _robots_allow(robots: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^Allow:\s*(\S+)", robots, re.M)]


def _path_exists(path: str, locs) -> bool:
    """True when the URL path maps to a shipped file or a routed nginx location."""
    if path == "/":
        return (WEBSITE / "index.html").exists()
    if (WEBSITE / path.lstrip("/")).exists():
        return True
    loc = api_contract.nginx_match(path, locs)
    if loc is None or loc.denied or loc.return_code is not None:
        return False
    return loc.proxy_upstream is not None or loc.static_root is not None


class TestWebsiteDiscoverability(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.locs = _nginx_locs()
        cls.robots = (WEBSITE / "robots.txt").read_text(encoding="utf-8")

    def test_internal_links_resolve(self) -> None:
        bad = []
        for page in _html_pages():
            src = page.read_text(encoding="utf-8")
            for attr, url, line in _link_targets(src):
                if _is_external_or_special(url):
                    continue
                path = _canonical_path(url)
                if not _path_exists(path, self.locs):
                    bad.append(f"{page.name}:{line}: {attr}={url} -> unrouted {path}")
        self.assertEqual([], bad, "internal links that resolve nowhere:\n" + "\n".join(bad))

    def test_llms_txt_entries_exist_and_crawlable(self) -> None:
        src = (WEBSITE / "llms.txt").read_text(encoding="utf-8")
        disallow = _robots_disallow(self.robots)
        allow = _robots_allow(self.robots)
        bad = []
        for m in re.finditer(r"\((https://hub\.aitbc\.bubuit\.net[^)]+)\)", src):
            url = m.group(1)
            path = _canonical_path(url)
            if not _path_exists(path, self.locs):
                bad.append(f"llms.txt links {path} which resolves nowhere")
            # Markdown-linked pages must not be robots-disallowed (unless an
            # explicit Allow overrides, e.g. the openapi.json trio).
            disallowed = any(path.startswith(d) for d in disallow)
            allowed = any(path == a or path.startswith(a) for a in allow)
            if disallowed and not allowed:
                bad.append(f"llms.txt links {path} which robots.txt disallows")
        # Backticked API paths must route somewhere public — a loopback-only
        # or unrouted path (e.g. /v1/bridge/deposits) is not agent-usable.
        for m in re.finditer(r"`(/[^`\s{]+)`", src):
            path = m.group(1)
            # Prefix descriptors ("under /v1/bridge", "over /explorer-api")
            # match their location with a trailing slash.
            if not _path_exists(path, self.locs) and not _path_exists(path + "/", self.locs):
                bad.append(f"llms.txt mentions {path} which resolves nowhere")
        self.assertEqual([], bad, "\n".join(bad))

    def test_sitemap_matches_indexable_pages(self) -> None:
        xml = (WEBSITE / "sitemap.xml").read_text(encoding="utf-8")
        locs = re.findall(r"<loc>([^<]+)</loc>", xml)
        problems = [f"sitemap loc not on canonical host: {u}" for u in locs if not u.startswith(CANONICAL_HOST)]
        sitemap_paths = {_canonical_path(u) for u in locs}
        for p in sitemap_paths:
            if not (WEBSITE / p.lstrip("/")).exists() and not (p == "/" and (WEBSITE / "index.html").exists()):
                problems.append(f"sitemap loc has no file: {p}")
        indexable = set()
        for page in _html_pages():
            src = page.read_text(encoding="utf-8")
            canonical = re.search(r'rel="canonical" href="([^"]+)"', src)
            noindex = re.search(r'name="robots" content="[^"]*noindex', src)
            if canonical and not noindex:
                indexable.add(_canonical_path(canonical.group(1)))
        missing = indexable - sitemap_paths
        extra = sitemap_paths - indexable
        problems += [f"indexable page missing from sitemap: {p}" for p in sorted(missing)]
        problems += [f"sitemap entry is not an indexable page: {p}" for p in sorted(extra)]
        self.assertEqual([], problems, "\n".join(problems))

    def test_no_leaked_hosts_or_secrets(self) -> None:
        bad = []
        for f in _shipped_files():
            src = f.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(src.splitlines(), 1):
                for label, rx in DENY_RES.items():
                    for m in rx.finditer(line):
                        if label == "ethereum-style address" and m.group(0) in HEX_ALLOWLIST:
                            continue
                        bad.append(f"{f.name}:{line_no}: {label}")
        self.assertEqual([], bad, "\n".join(sorted(set(bad))))

    def test_social_meta_on_indexable_pages(self) -> None:
        problems = []
        for page in _html_pages():
            src = page.read_text(encoding="utf-8")
            if 'name="robots" content="noindex' in src or 'rel="canonical"' not in src:
                continue
            for tag in ("og:title", "og:description", "og:type", "og:url"):
                if f'property="{tag}"' not in src:
                    problems.append(f"{page.name}: missing {tag}")
            if 'name="twitter:card"' not in src:
                problems.append(f"{page.name}: missing twitter:card")
        self.assertEqual([], problems, "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
