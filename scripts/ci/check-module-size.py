#!/usr/bin/env python3
"""Ratchet: no NEW module over the line-count ceiling.

A file that grows past ``CEILING`` lines is almost always several modules
wearing one filename — harder to review, harder to split later, and the
shape every "this file is too big" refactor starts from. The existing
offenders are grandfathered in ``scripts/ci/module-size-baseline.txt``;
this gate fails only on the *delta*:

* a non-baselined file crosses the ceiling            -> fail
* a baselined file grows past its recorded line count -> fail
* a baselined file shrinks                            -> note (run --update)

Same "baseline + gate the delta" mechanism as
``check-c901-ratchet.sh`` / ``check-except-ratchet.sh``, but the scan is
pure stdlib (``git ls-files`` + line counts) so it needs no repo venv.

Scope — tracked ``*.py`` files, minus:

* tests: any ``tests`` path component, ``test_*.py``, ``*_test.py``
* generated: ``*generated*`` in the file name (the MCP wrapper modules are
  emitted by ``scripts/dev/generate_mcp_cli_tools.py``) and alembic
  ``versions/`` directories
* vendored: ``vendor``/``vendored``/``third_party`` path components

Usage:

    scripts/ci/check-module-size.py            # check (pre-push hook / CI)
    scripts/ci/check-module-size.py --update   # regenerate the baseline
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "scripts" / "ci" / "module-size-baseline.txt"
CEILING = 2000

_EXCLUDED_PARTS = {"tests", "vendor", "vendored", "third_party"}


def _excluded(rel: str) -> bool:
    parts = Path(rel).parts
    name = parts[-1]
    if _EXCLUDED_PARTS & set(parts):
        return True
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if "generated" in name:
        return True
    # Alembic migration files are generated scaffolding, not hand-maintained
    # modules — a 5k-line initial migration is expected, not debt.
    if "alembic" in parts and "versions" in parts:
        return True
    return False


def _tracked_py() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ln for ln in out.stdout.splitlines() if ln and not _excluded(ln)]


def _line_count(path: Path) -> int:
    # splitlines() counts a final unterminated line too — deterministic and
    # within one of `wc -l`, which is all a ceiling needs.
    return len(path.read_bytes().splitlines())


def _scan() -> dict[str, int]:
    """repo-relative path -> line count, for every in-scope file over CEILING."""
    offenders: dict[str, int] = {}
    for rel in _tracked_py():
        n = _line_count(REPO_ROOT / rel)
        if n > CEILING:
            offenders[rel] = n
    return offenders


def _load_baseline() -> dict[str, int]:
    """path -> tolerated line count (``lines<TAB>path`` or ``lines path``)."""
    out: dict[str, int] = {}
    if not BASELINE.exists():
        return out
    for ln in BASELINE.read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        count_s, _, path = ln.partition("\t")
        if not path:
            count_s, _, path = ln.partition(" ")
        if count_s.isdigit() and path:
            out[path.strip()] = int(count_s)
    return out


def _update_baseline(current: dict[str, int]) -> int:
    lines = [
        "# module-size ratchet baseline — regenerate: check-module-size.py --update",
        f"# files over {CEILING} lines grandfathered at their current size;",
        "# the gate fails on NEW offenders and on growth of these.",
    ]
    lines += [f"{n}\t{path}" for path, n in sorted(current.items())]
    BASELINE.write_text("\n".join(lines) + "\n")
    print(f"module-size baseline updated: {len(current)} files over {CEILING} lines")
    return 0


def _check(current: dict[str, int]) -> int:
    baseline = _load_baseline()
    status = 0
    for path in sorted(current):
        n = current[path]
        prev = baseline.get(path)
        if prev is None:
            print(f"module-size regression: {path} has {n} lines (ceiling: {CEILING}, no baseline entry)")
            status = 1
        elif n > prev:
            print(f"module-size regression: {path} grew to {n} lines (baseline: {prev})")
            status = 1
        elif n < prev:
            print(
                f"module-size improvement: {path} shrank to {n} lines "
                f"(baseline: {prev}) — run scripts/ci/check-module-size.py --update"
            )
    for path in sorted(set(baseline) - set(current)):
        print(f"module-size stale baseline: {path} no longer exceeds {CEILING} — run scripts/ci/check-module-size.py --update")
    if status == 0:
        print(f"module-size ratchet: no growth ({len(baseline)} baselined files over {CEILING} lines)")
    else:
        print(
            "\nA new module crossed the line ceiling or a grandfathered file grew. "
            "Split the module instead of growing it — do NOT regenerate the "
            "baseline to hide growth. Re-run with --update only after a "
            "deliberate refactor that actually shrank a file:\n"
            "\n"
            "    scripts/ci/check-module-size.py --update",
            file=sys.stderr,
        )
    return status


def main(argv: list[str]) -> int:
    current = _scan()
    if "--update" in argv:
        return _update_baseline(current)
    return _check(current)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
