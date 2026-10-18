#!/usr/bin/env python3
"""Dead docs-path reference check — non-docs files that name missing docs/*.md.

Tracked files outside `docs/` sometimes carry repo-root-relative paths like
`docs/fleet-roles.md` in comments, strings, docs-reads or messages. The
markdown link checker only looks at `](...)` targets inside docs/, so a moved
or deleted doc leaves those references silently pointing nowhere — as happened
when tests and scripts kept reading `docs/blockchain/ENVIRONMENT_CONFIGURATION.md`
after it moved (DOCS-FIXUP-1).

This checker scans every tracked non-docs file for `docs/...md` path strings
and fails on any that do not resolve. Pattern files (`.gitignore`,
`.gitattributes`, `*ignore`) are skipped — their entries are globs, not
references. Scripts that deliberately probe a path's existence
(`test -f`, `if [ -f ]`) still name the path and are baselined per file,
so the list only shrinks.

Usage:
    check_docs_path_refs.py                  # verify against the baseline
    check_docs_path_refs.py --write-baseline # regenerate the baseline
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("docs-path-refs-baseline.txt")

PATTERN_FILES = {".gitignore", ".gitattributes", ".dockerignore", ".prettierignore"}

# The checker and its own baseline necessarily carry dead-path strings.
SELF = {
    "scripts/docs/check_docs_path_refs.py",
    "scripts/docs/docs-path-refs-baseline.txt",
}

PATH_RE = re.compile(r"docs/[A-Za-z0-9_./-]+\.md")


def tracked_non_docs_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    return [f for f in out if not f.startswith("docs/") and Path(f).name not in PATTERN_FILES and f not in SELF]


def dead_refs() -> list[str]:
    """Return 'file: docs/path.md' entries for path strings that do not resolve."""
    dead: list[str] = []
    for f in tracked_non_docs_files():
        try:
            text = (ROOT / f).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        seen = set()
        for m in PATH_RE.finditer(text):
            ref = m.group(0).rstrip(".,);'\"")
            if ref in seen:
                continue
            seen.add(ref)
            if not (ROOT / ref).exists():
                dead.append(f"{f}: {ref}")
    return sorted(dead)


def read_baseline() -> list[str]:
    if not BASELINE.exists():
        return []
    return sorted(ln for ln in (ln.strip() for ln in BASELINE.read_text().splitlines()) if ln)


def main() -> int:
    dead = dead_refs()
    if "--write-baseline" in sys.argv:
        BASELINE.write_text("".join(f"{d}\n" for d in dead))
        print(f"wrote {len(dead)} baseline entr{'y' if len(dead) == 1 else 'ies'}")
        return 0

    baseline = set(read_baseline())
    new = [d for d in dead if d not in baseline]
    stale = [b for b in baseline if b not in dead]

    for b in stale:
        print(f"STALE BASELINE (path exists again or ref removed — prune): {b}")
    if new:
        print("Non-docs files reference docs paths that do not exist:")
        for n in new:
            print(f"  {n}")
        print(
            "\nRepoint the reference, or add it to the baseline with --write-baseline if it is a deliberate existence probe."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
