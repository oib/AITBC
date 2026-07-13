#!/usr/bin/env python3
"""Verify that the package version, source version, and CLI version agree."""

import importlib.metadata
import subprocess
import sys
import tomllib
from pathlib import Path

import aitbc._version

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        expected = tomllib.load(f)["tool"]["poetry"]["version"]

    errors = []
    if aitbc._version.__version__ != expected:
        errors.append(f"aitbc._version.__version__ = {aitbc._version.__version__} != {expected}")
    if importlib.metadata.version("aitbc") != expected:
        errors.append(f"importlib.metadata.version('aitbc') = {importlib.metadata.version('aitbc')} != {expected}")

    result = subprocess.run(
        [sys.executable, "-m", "aitbc_cli", "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        errors.append(f"aitbc_cli --version failed: {result.stderr}")
    elif f"version {expected}" not in result.stdout:
        errors.append(f"aitbc_cli --version = {result.stdout.strip()} != {expected}")

    if errors:
        for err in errors:
            print(f"version mismatch: {err}")
        return 1
    print(f"version consistency OK: {expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
