#!/usr/bin/env python3
"""Require `set -euo pipefail` in shell scripts, on the ones being touched.

V23-23: of 266 tracked scripts, 210 have `set -e`, and only 44 have either `set -u` or
`pipefail`. So a mistyped variable name expands to empty and the script carries on
confidently -- which is the mechanism that made V23-22's `rm -rf` on a defaulted path
dangerous rather than merely untidy.

The finding is explicit that a sweep is the wrong move:

    applied when a script is touched rather than in one sweep -- turning it on wholesale
    will surface genuine latent failures, and doing that across 166 scripts at once gives
    no way to tell which break was real. A pre-commit check on new scripts stops the count
    growing.

So this is a ratchet, not a migration. Run from pre-commit it receives only the scripts in
the current commit: touch a script, bring it up to standard. Existing scripts nobody is
editing are left alone, and the count cannot grow.

`--all` audits the whole tree and always exits 0 -- for seeing where the number stands
without blocking anything.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# `set -e`, `set -eu`, `set -euo pipefail`, `set -o errexit`, and the same split across
# several lines all count. What matters is that the three properties are switched on
# somewhere near the top, not that they are spelled one particular way.
ERREXIT = re.compile(r"^\s*set\s+-[a-zA-Z]*e|^\s*set\s+-o\s+errexit", re.M)
NOUNSET = re.compile(r"^\s*set\s+-[a-zA-Z]*u|^\s*set\s+-o\s+nounset", re.M)
# `set -euo pipefail` is the canonical spelling and does not contain `-o pipefail` as its
# own token -- the `o` belongs to the `-euo` bundle. An earlier version of this pattern
# required `-o\s+pipefail` and so reported the repository's one fully-strict script as
# non-compliant, which is the sort of wrong number that gets a check deleted.
PIPEFAIL = re.compile(r"^\s*set\s+[-\w\s]*\bpipefail\b", re.M)

# Sourced fragments define variables for a parent shell; `set -u` in them changes the
# caller's shell, which is not this check's business.
SKIP_SUFFIXES = (".bashrc", ".profile", ".env")


def _is_shell(path: Path) -> bool:
    if path.suffix == ".sh":
        return True
    try:
        first = path.read_bytes().split(b"\n", 1)[0]
    except (OSError, IndexError):
        return False
    return first.startswith(b"#!") and (b"bash" in first or b"sh" in first)


def _missing(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    gaps = []
    if not ERREXIT.search(text):
        gaps.append("set -e")
    if not NOUNSET.search(text):
        gaps.append("set -u")
    if not PIPEFAIL.search(text):
        gaps.append("set -o pipefail")
    return gaps


def _tracked_shell_scripts() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line and (REPO_ROOT / line).is_file()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="*")
    parser.add_argument("--all", action="store_true", help="audit every tracked script; never fails")
    args = parser.parse_args(argv)

    if args.all:
        candidates = [p for p in _tracked_shell_scripts() if _is_shell(p)]
        incomplete = {p: gaps for p in candidates if (gaps := _missing(p))}
        print(f"{len(candidates)} shell scripts, {len(candidates) - len(incomplete)} with full strict mode")
        for path, gaps in sorted(incomplete.items()):
            print(f"  {path.relative_to(REPO_ROOT)}: missing {', '.join(gaps)}")
        return 0

    failed = False
    for name in args.filenames:
        path = Path(name)
        if not path.is_absolute():
            path = REPO_ROOT / name
        if not path.is_file() or path.name.endswith(SKIP_SUFFIXES) or not _is_shell(path):
            continue

        gaps = _missing(path)
        if gaps:
            print(f"{name}: missing {', '.join(gaps)}")
            failed = True

    if failed:
        print(
            "\n  Add `set -euo pipefail` near the top. This is required only of scripts in\n"
            "  this commit -- V23-23 found 166 without it, and the fix note says to convert\n"
            "  them as they are touched, because turning it on wholesale surfaces latent\n"
            "  failures with no way to tell which break was real.\n"
            "\n"
            "  If a script genuinely needs unset variables to expand empty, scope it:\n"
            "    set -euo pipefail\n"
            "    ...\n"
            "    set +u; source ./thing-that-needs-it; set -u\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
