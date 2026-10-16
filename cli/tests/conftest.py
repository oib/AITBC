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


# Dead endpoints so any code path that skips the mocks fails fast instead of
# waiting on a wallet daemon or node that CI does not run. Scoped to this
# suite via monkeypatch (restored per test) — the required gate runs every
# suite in one pytest process, so a module-level setdefault would leak into
# other suites or silently lose to an earlier conftest's value.
import pytest as _pytest_dead


@_pytest_dead.fixture(autouse=True)
def _dead_rpc_endpoints(monkeypatch):
    monkeypatch.setenv("WALLET_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:1")


# Signing-related env vars must not leak into CLI tests: a developer machine
# with AITBC_DEFAULT_WALLET set would otherwise flip unsigned-path tests into
# wallet loads and abort them.
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _clean_signing_env(monkeypatch):
    for var in (
        "AITBC_DEFAULT_WALLET",
        "AITBC_MARKET_WALLET",
        "AITBC_WALLET_PASSWORD",
        "SHOP_WALLET_ADDRESS",
        "AGENT_ID",
        # Modules such as aitbc_cli.commands.coin_requests load /etc/aitbc/*.env
        # into os.environ at import time — on a live node that leaks the real
        # CHAIN_ID into tests that exercise chain-id resolution.
        "CHAIN_ID",
    ):
        monkeypatch.delenv(var, raising=False)
