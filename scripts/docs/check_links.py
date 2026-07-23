#!/usr/bin/env python3
"""Validate internal markdown links across the AITBC documentation tree.

Exit codes:
    0 - all links valid
    1 - one or more broken internal .md links found
"""

import re
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    docs_dir = repo / "docs"

    exclude_prefixes = {
        str(repo / ".git"),
        str(repo / "venv"),
        str(repo / ".mypy_cache"),
        str(repo / ".pytest_cache"),
        str(repo / ".ruff_cache"),
        str(repo / "htmlcov"),
        str(repo / ".hypothesis"),
    }

    [p for p in repo.rglob("*.md") if not any(str(p).startswith(prefix) for prefix in exclude_prefixes)]

    scan_files = list(docs_dir.rglob("*.md"))
    if (repo / "README.md").exists():
        scan_files.append(repo / "README.md")

    link_re = re.compile(r"(\[[^\]]*\]\()([^)]+)(\))")
    broken: list[tuple[str, str]] = []
    checked = 0

    for src in scan_files:
        text = src.read_text(errors="ignore")
        for m in link_re.finditer(text):
            target = m.group(2).strip()
            base = target.split("#", 1)[0]
            if not base:
                continue
            if base.startswith(("http://", "https://", "mailto://", "vscode-remote://")):
                continue
            if not base.endswith(".md"):
                continue
            checked += 1
            if base.startswith("/"):
                resolved = repo / base.lstrip("/")
            else:
                resolved = (src.parent / base).resolve()
            if not resolved.exists():
                broken.append((str(src.relative_to(repo)), target))

    if not broken:
        print(f"Checked {checked} internal .md link(s). All valid.")
        return 0

    print(f"Checked {checked} internal .md link(s). Found {len(broken)} broken link(s):\n")
    for src, target in broken:
        print(f"  {src} -> {target}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
