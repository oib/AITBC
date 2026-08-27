#!/usr/bin/env python3
"""Validate internal links across the AITBC documentation tree.

Covers links to other documents and links into the source tree.

Exit codes:
    0 - all links valid
    1 - one or more broken internal links found
"""

import re
import sys
from pathlib import Path

# Documentation trees excluded from link validation.
#
# docs/archive/ holds retired material, including README-TEMPLATE.md -- a template meant
# to be copied into *other* repos, whose "./AGENTS.md"-style links are deliberate
# placeholders relative to the consuming project. Resolving them against this repo is
# meaningless.
EXCLUDED_DOC_DIRS = ("docs/archive/",)

# Non-.md targets worth resolving.
#
# A link into the source tree is as navigable as a link to another document, and for as
# long as this checker skipped everything that did not end in .md, it could not see them.
# Three scenario docs pointed one level above the repo root for months on that account
# (09ff3b7fe, c6e961ae6). Only extensions that name a file living in this repo belong here.
SOURCE_SUFFIXES = frozenset(
    {
        ".py",
        ".sh",
        ".sol",
        ".circom",
        ".yml",
        ".yaml",
        ".toml",
        ".json",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".cfg",
        ".ini",
        ".txt",
        ".sql",
        ".rs",
        ".go",
        ".html",
        ".css",
        ".conf",
        ".service",
        ".env",
        ".lock",
        ".proto",
    }
)

LINK_RE = re.compile(r"(\[[^\]]*\]\()([^)]+)(\))")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def strip_code_fences(text: str) -> str:
    """Blank out fenced code blocks, preserving line count.

    Links inside fences are illustrative samples (e.g. a skeleton README shown in an
    authoring guide), not navigable links, and must not be resolved against the tree.
    """
    out, in_fence = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    docs_dir = repo / "docs"

    scan_files = [
        p for p in docs_dir.rglob("*.md") if not any(str(p.relative_to(repo)).startswith(d) for d in EXCLUDED_DOC_DIRS)
    ]
    if (repo / "README.md").exists():
        scan_files.append(repo / "README.md")

    broken: list[tuple[str, str]] = []
    checked = 0

    for src in scan_files:
        text = strip_code_fences(src.read_text(errors="ignore"))
        for m in LINK_RE.finditer(text):
            target = m.group(2).strip()
            base = target.split("#", 1)[0]
            if not base:
                continue
            if base.startswith(("http://", "https://", "mailto://", "vscode-remote://")):
                continue
            if not base.endswith(".md"):
                # Root-relative source links are not checked. docs/architecture/7_wallet.md
                # and docs/agent-sdk/ use "/Exchange/", "/explorer/" and
                # "/rpc/messaging/topics/support" as *site* routes served by nginx, not as
                # paths in the tree; resolving those against the repo root would report a
                # dozen links that work exactly as intended.
                if base.startswith("/"):
                    continue
                if Path(base).suffix.lower() not in SOURCE_SUFFIXES:
                    continue

            if base.startswith("/"):
                resolved = repo / base.lstrip("/")
            else:
                resolved = (src.parent / base).resolve()

            checked += 1
            if not resolved.exists():
                broken.append((str(src.relative_to(repo)), target))

    if not broken:
        print(f"Checked {checked} internal link(s). All valid.")
        return 0

    print(f"Checked {checked} internal link(s). Found {len(broken)} broken link(s):\n")
    for src, target in broken:
        print(f"  {src} -> {target}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
