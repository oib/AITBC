#!/usr/bin/env python3
"""Fail when a file contains committed merge-conflict markers.

The repository already runs pre-commit's `check-merge-conflict`, which has been passing on
every commit while `docs/releases/v0.23/release.log` carried a full conflict block —
`<<<<<<< HEAD`, `=======`, `>>>>>>> f9d378797` — in the middle of the second-pass totals.

The reason is in the hook's source:

    if not is_in_merge() and not args.assume_in_merge:
        return 0

It only looks while git is *mid-merge*. The moment a bad resolution is committed the markers
become ordinary text and the hook never examines them again. It catches the mistake you are
about to make and is blind to the one already in the tree — which is the wrong half, because
the second is the one nobody notices.

`--assume-in-merge` would make it always run, but it flags a bare `=======` line, and
`docs/scenarios/07_ai_job_submission.md:110` has one inside a fenced code block as a heading
underline. A rule that cries wolf on legitimate documentation gets turned off.

So: require the *pair*. `<<<<<<< ` or `>>>>>>> ` at the start of a line is unambiguous — no
markup uses them — and a bare `=======` is only reported when the file also carries one of
those. Zero false positives on this tree, and it runs on every commit rather than only during
a merge.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

UNAMBIGUOUS = (b"<<<<<<< ", b">>>>>>> ")
AMBIGUOUS = (b"=======\n", b"=======\r\n", b"======= ")


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def _scan(path: Path) -> list[tuple[int, str]]:
    """Return (line number, marker) for each conflict marker in the file."""
    try:
        data = path.read_bytes()
    except (OSError, IsADirectoryError):
        return []

    if b"<<<<<<< " not in data and b">>>>>>> " not in data:
        # No unambiguous marker, so a lone `=======` is a heading underline, not a conflict.
        return []

    found: list[tuple[int, str]] = []
    for number, line in enumerate(data.splitlines(keepends=True), start=1):
        for pattern in UNAMBIGUOUS + AMBIGUOUS:
            if line.startswith(pattern):
                found.append((number, pattern.strip().decode()))
                break
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="*", help="files to check; defaults to all tracked files")
    args = parser.parse_args(argv)

    targets = args.filenames or _tracked_files()

    failed = False
    for name in targets:
        path = Path(name)
        if not path.is_absolute():
            path = REPO_ROOT / name
        for number, marker in _scan(path):
            print(f"{name}:{number}: merge conflict marker {marker!r}")
            failed = True

    if failed:
        print(
            "\n  A conflict was resolved by committing the markers. Fix the content, do not "
            "just delete the marker lines -- both sides of the conflict are still in the file "
            "and one of them is wrong.\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
