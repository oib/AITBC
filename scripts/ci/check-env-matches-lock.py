#!/usr/bin/env python3
"""Fail when the installed environment does not match poetry.lock.

V23-20 found `starlette` 1.2.1 installed against a 1.3.1 pin, and V23-21 found `truffleHog`
`pip install`ed into the Poetry venv, dragging `GitPython` 3.0.6 below the floor that
`detect-secrets` declares.

Those are not cosmetic. Of the 68 vulnerabilities `pip-audit` reported for v0.23:

  * 31 came from packages that are **not in poetry.lock at all** — GitPython (24, via
    truffleHog), pyasn1 (4, via python-jose/rsa), mcp (3, orphaned)
  * 5 came from declared packages whose *installed* version was stale, where the pinned
    version already carried the fix

So 36 of 68 were properties of one machine rather than of this repository. An audit that
cannot tell those apart is measuring the wrong thing, and "the tests pass" means less than it
appears to when the code under test is not the code that was declared.

Run with --strict in CI. Without it, extras are reported and the exit code stays 0, which is
what you want locally where a developer may have deliberately installed a tool.
"""

from __future__ import annotations

import argparse
import re
import sys
from importlib.metadata import distributions
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK = REPO_ROOT / "poetry.lock"

# Bootstrap and packaging machinery: present in every venv, not resolved by the lock.
IGNORED = {
    "pip",
    "poetry",
    "setuptools",
    "wheel",
    "distribute",
    "pkg-resources",
}


def _normalise(name: str) -> str:
    """PEP 503 normalisation — `truffleHog` and `trufflehog` are the same project."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _locked_versions() -> dict[str, str]:
    """Map normalised package name to the version poetry.lock pins."""
    text = LOCK.read_text(encoding="utf-8")
    locked: dict[str, str] = {}
    for block in text.split("[[package]]")[1:]:
        name = re.search(r'^name = "([^"]+)"', block, re.M)
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        if name and version:
            locked[_normalise(name.group(1))] = version.group(1)
    return locked


def _installed_versions() -> dict[str, str]:
    installed: dict[str, str] = {}
    for dist in distributions():
        name = dist.metadata["Name"]
        if name:
            installed[_normalise(name)] = dist.version
    return installed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit non-zero on any drift or extra package")
    args = parser.parse_args()

    if not LOCK.is_file():
        print(f"error: {LOCK} not found", file=sys.stderr)
        return 2

    locked = _locked_versions()
    installed = _installed_versions()

    # Path dependencies (the repo's own packages) are installed as editable, and their
    # recorded version need not match the lock's. Found by their pyproject rather than by
    # listing packages/ -- they live at two depths (packages/aitbc-shared and
    # packages/py/aitbc-sdk), and missing one would report the repo's own code as foreign.
    local_packages = {_normalise(p.parent.name) for p in (REPO_ROOT / "packages").rglob("pyproject.toml")}
    local_packages |= {"aitbc", "aitbc-cli"}

    drifted: list[str] = []
    extra: list[str] = []

    for name, version in sorted(installed.items()):
        if name in IGNORED or name in local_packages:
            continue
        if name not in locked:
            extra.append(f"  {name}=={version}")
        elif locked[name] != version:
            drifted.append(f"  {name}: locked {locked[name]}, installed {version}")

    if drifted:
        print("Installed versions differ from poetry.lock:")
        print("\n".join(drifted))
        print("\n  Fix: poetry install --sync\n")

    if extra:
        print("Installed but not in poetry.lock (nothing in this repo declares them):")
        print("\n".join(extra))
        print(
            "\n  These were installed outside Poetry. They can hold shared dependencies below\n"
            "  the floor the lock resolved -- truffleHog pinned GitPython to 3.0.6, which is\n"
            "  below the >=3.1.30 that detect-secrets declares, and carried 24 advisories.\n"
            "  Fix: poetry install --sync, or declare the tool in a dependency group.\n"
        )

    if not drifted and not extra:
        print(f"Environment matches poetry.lock ({len(installed)} distributions checked).")
        return 0

    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
