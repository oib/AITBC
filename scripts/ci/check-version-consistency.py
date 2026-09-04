#!/usr/bin/env python3
"""Verify that all version references in the repository stay in sync.

The single source of truth is aitbc/_version.py. This script checks the
pyproject.toml, CLI package, README badge, and release changelog for the same
value. It is intended to run in CI before any build or publish step.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_canonical_version() -> str:
    text = (REPO_ROOT / "aitbc" / "_version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        print("ERROR: Could not parse __version__ from aitbc/_version.py", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def _check_file(path: Path, pattern: str, expected: str, description: str, *, all_matches: bool = False) -> bool:
    """Check that a file contains the expected version.

    If all_matches is True, every match of the pattern must equal expected; otherwise the
    first match is checked.
    """
    if not path.is_file():
        print(f"ERROR: {description} not found at {path}", file=sys.stderr)
        return False
    text = path.read_text(encoding="utf-8")
    flags = re.MULTILINE if pattern.startswith("^") else 0
    matches = re.findall(pattern, text, flags)
    if not matches:
        print(f"ERROR: Could not find version pattern in {description} ({path})", file=sys.stderr)
        return False
    if all_matches:
        bad = [m for m in matches if m != expected]
        if bad:
            print(
                f"ERROR: Version mismatch in {description} ({path}): "
                f"expected all {expected!r}, found inconsistent {bad[0]!r}",
                file=sys.stderr,
            )
            return False
        print(f"OK: {description} -> {expected} ({len(matches)} references)")
        return True
    found = matches[0]
    if found != expected:
        print(
            f"ERROR: Version mismatch in {description} ({path}): "
            f"expected {expected!r}, found {found!r}",
            file=sys.stderr,
        )
        return False
    print(f"OK: {description} -> {found}")
    return True


def main() -> int:
    expected = _read_canonical_version()
    print(f"Canonical version from aitbc/_version.py: {expected}")
    ok = True

    # pyproject.toml contains version under [project] and [tool.poetry]; both must match.
    ok &= _check_file(
        REPO_ROOT / "pyproject.toml",
        r'^version\s*=\s*"([^"]+)"',
        expected,
        "pyproject.toml",
        all_matches=True,
    )
    ok &= _check_file(
        REPO_ROOT / "cli" / "setup.py",
        r'version\s*=\s*"([^"]+)"',
        expected,
        "cli/setup.py",
    )
    ok &= _check_file(
        REPO_ROOT / "cli" / "aitbc_cli" / "__init__.py",
        r'__version__\s*=\s*"([^"]+)"',
        expected,
        "cli/aitbc_cli/__init__.py",
    )
    ok &= _check_file(
        REPO_ROOT / "cli" / "aitbc_cli" / "core" / "__version__.py",
        r'__version__\s*=\s*"([^"]+)"',
        expected,
        "cli/aitbc_cli/core/__version__.py",
    )
    ok &= _check_file(
        REPO_ROOT / "cli" / "aitbc_cli" / "core" / "main.py",
        r'__version__\s*=\s*"([^"]+)"',
        expected,
        "cli/aitbc_cli/core/main.py",
    )

    # README badge may use a leading 'v' in markdown; accept vX.Y.Z or X.Y.Z
    readme_path = REPO_ROOT / "README.md"
    if readme_path.is_file():
        text = readme_path.read_text(encoding="utf-8")
        match = re.search(r"version-v?([0-9]+\.[0-9]+\.[0-9]+)", text)
        if match and match.group(1) != expected:
            print(
                f"ERROR: README badge version mismatch: expected {expected!r}, found {match.group(1)!r}",
                file=sys.stderr,
            )
            ok = False
        elif not match:
            print("WARNING: README version badge not found", file=sys.stderr)
        else:
            print(f"OK: README badge -> {match.group(1)}")

    if ok:
        print(f"All version references are consistent with aitbc/_version.py ({expected}).")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
