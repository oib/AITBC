"""
Conftest for CLI tests.

Auto-uses the shared CLI mock fixtures so that the 70+ stubbed CLI test files
can be converted incrementally without each one re-declaring the same
fixtures.  Importing this module makes every fixture in
``tests/fixtures/cli_mocks.py`` available to all CLI tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_credential_store(monkeypatch, tmp_path):
    """Keep the host's real ``~/.aitbc`` credential store out of the suite.

    ``AuthManager()`` resolves the operator's stored admin/client JWTs — an
    expired credential raises ``ExpiredAdminToken`` inside unrelated command
    tests, and a live one would leak a real bearer into mocked calls (#2940).
    Force the file backend at an empty tmp path; tests that exercise auth
    pass ``store_path`` or patch the methods themselves.
    """
    monkeypatch.setattr("aitbc_cli.auth._DEFAULT_STORE", tmp_path / "credentials.json")
    monkeypatch.setattr("aitbc_cli.auth._resolve_keyring", lambda: None)


@pytest.fixture(autouse=True)
def _dead_rpc_endpoints(monkeypatch):
    """Dead endpoints so unmocked wallet/RPC lookups fail fast.

    Scoped to this suite via monkeypatch (restored per test) — the required
    gate runs every suite in one pytest process, so a module-level
    ``setdefault`` would leak into other suites or silently lose to an
    earlier conftest's value. Replicates the old workflow's step-level env.
    """
    monkeypatch.setenv("WALLET_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:1")
    # Other suites' conftests pin CHAIN_ID at import to satisfy the strict
    # resolver (#307); that pin must not leak in here, where tests stub
    # get_chain_id and expect it to win over an unset env.
    monkeypatch.delenv("CHAIN_ID", raising=False)

# Make the shared fixtures importable.
_FIXTURES_DIR = str(Path(__file__).resolve().parent.parent / "fixtures")
if _FIXTURES_DIR not in sys.path:
    sys.path.insert(0, _FIXTURES_DIR)

from cli_mocks import (  # noqa: E402  # type: ignore[import-not-found]
    cli_obj,
    make_cli_obj,
    mock_blockchain_rpc,
    mock_click_context,
    mock_config,
    mock_eth_utils,
    mock_subprocess,
    mock_wallet,
    parse_json_output,
)

# Re-export so tests can request them by name.
__all__ = [
    "cli_obj",
    "make_cli_obj",
    "mock_blockchain_rpc",
    "mock_click_context",
    "mock_config",
    "mock_eth_utils",
    "mock_subprocess",
    "mock_wallet",
    "parse_json_output",
]


@pytest.fixture
def runner():
    """Create a Click ``CliRunner`` for invoking commands."""
    return CliRunner()


@pytest.fixture(autouse=True)
def _mock_payment_wallet(monkeypatch):
    """Provide a deterministic default wallet for payment commands.

    Commands such as ``aitbc ai submit`` and ``aitbc market escrow create`` call
    :func:`aitbc_cli.utils.wallet_loader.load_wallet_for_payment` and need a
    usable signing key.  This fixture intercepts that call and returns a
    temporary secp256k1 keypair so the tests never hit the wallet daemon.
    """
    try:
        from eth_account import Account

        _account = Account.create()
        _address = _account.address
        _private_key = _account.key.hex()
    except ImportError:
        _address = "0x" + "ab" * 20
        _private_key = "ab" * 32

    def _load_wallet_for_payment(ctx, *args, **kwargs):
        # ``wallet_name`` and ``wallet_path`` are ignored; the tests only need
        # a canonical address and a private key that can sign transactions.
        return _address, _private_key, kwargs.get("wallet_name") or "default"

    # The commands import ``load_wallet_for_payment`` at module load time, so
    # patching the definition is not enough: we patch the bound names in each
    # command module that uses it.
    targets = [
        "aitbc_cli.utils.wallet_loader.load_wallet_for_payment",
        "aitbc_cli.utils.load_wallet_for_payment",
        "aitbc_cli.commands.ai.load_wallet_for_payment",
        "aitbc_cli.commands.market.escrow.load_wallet_for_payment",
        "aitbc_cli.commands.market.load_wallet_for_payment",
        "aitbc_cli.commands.exchange_island.load_wallet_for_payment",
        "aitbc_cli.commands.ipfs.load_wallet_for_payment",
        "aitbc_cli.commands.cross_chain.load_wallet_for_payment",
    ]
    for target in targets:
        try:
            monkeypatch.setattr(target, _load_wallet_for_payment)
        except AttributeError:
            pass


@pytest.fixture(autouse=True)
def _cli_default_obj(monkeypatch):
    """Auto-use fixture that patches ``CliRunner.invoke`` to set ``ctx.obj``.

    Extends the root ``tests/conftest.py`` patch with the full standard field
    set (``output_format`` in addition to ``output``) so commands that read
    ``ctx.obj.get("output_format", ...)`` receive a consistent value.
    """
    original_invoke = CliRunner.invoke

    def patched_invoke(self, cli, args=None, **kwargs):
        if kwargs.get("obj") is None:
            kwargs["obj"] = make_cli_obj()
        return original_invoke(self, cli, args, **kwargs)

    monkeypatch.setattr(CliRunner, "invoke", patched_invoke)


# market's once-per-process mismatch warnings (#2444) and config's ambient
# warning dedupe must not leak their sets across tests in one pytest process.
@pytest.fixture(autouse=True)
def _reset_warning_dedupes():
    try:
        from aitbc_cli.commands import market as _market_mod
    except ImportError:
        _market_mod = None
    if _market_mod is not None:
        _market_mod._MISMATCH_WARNED.clear()
    try:
        from aitbc_cli import config as _config_mod
    except ImportError:
        _config_mod = None
    if _config_mod is not None:
        _config_mod._AMBIENT_CONFIG_WARNED.clear()
    yield
    if _market_mod is not None:
        _market_mod._MISMATCH_WARNED.clear()
    if _config_mod is not None:
        _config_mod._AMBIENT_CONFIG_WARNED.clear()
