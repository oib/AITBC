"""Ensure core version sources agree with each other and the CLI."""

import importlib.metadata
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import aitbc._version


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _expected_version() -> str:
    """Read the canonical version from pyproject.toml."""
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data["project"].get("version") or data["tool"]["poetry"]["version"]


def test_package_version_matches_source() -> None:
    """``importlib.metadata`` agrees with ``aitbc._version``."""
    expected = _expected_version()
    assert aitbc._version.__version__ == expected
    assert importlib.metadata.version("aitbc") == expected


def test_cli_version_matches_source() -> None:
    """``aitbc --version`` agrees with the package version.

    The subprocess does not inherit the ``sys.path`` that ``tests/conftest.py`` builds, so
    without an explicit ``PYTHONPATH`` it resolves ``aitbc_cli`` through the editable install
    -- which points at the primary checkout. Run from a git worktree, this asserted against a
    different tree than the one under test.
    """
    expected = _expected_version()
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(PROJECT_ROOT / "cli"), str(PROJECT_ROOT), os.environ.get("PYTHONPATH", "")]).rstrip(
            os.pathsep
        ),
    }
    result = subprocess.run(
        [sys.executable, "-m", "aitbc_cli", "--version"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert f"version {expected}" in result.stdout
