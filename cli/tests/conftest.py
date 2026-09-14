"""Pytest configuration for CLI tests.

Ensures both the CLI directory and the project root are on sys.path so
that imports like `aitbc_cli.commands.explorer` and `aitbc.aitbc_logging`
resolve correctly.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CLI_DIR = Path(__file__).resolve().parent.parent

for p in (str(PROJECT_ROOT), str(CLI_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


# Signing-related env vars must not leak into CLI tests: a developer machine
# with AITBC_DEFAULT_WALLET set would otherwise flip unsigned-path tests into
# wallet loads and abort them.
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _clean_signing_env(monkeypatch):
    for var in ("AITBC_DEFAULT_WALLET", "AITBC_MARKET_WALLET", "AITBC_WALLET_PASSWORD", "AGENT_ID"):
        monkeypatch.delenv(var, raising=False)
