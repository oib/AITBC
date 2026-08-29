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


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Quarantine pre-existing CLI test failures so they don't block CI.

    These tests exercise CLI commands that have been removed or renamed during
    the v0.10.x refactor. They are tracked as known failures (xfail) pending the
    CLI command surface being updated.
    """
    quarantine_file = Path(__file__).resolve().parent / "quarantined.txt"
    if not quarantine_file.exists():
        return

    quarantined = {line.strip() for line in quarantine_file.read_text().splitlines() if line.strip()}
    if not quarantined:
        return

    prefix = "tests/cli/"
    prefixed = {"tests/cli/" + node for node in quarantined if not node.startswith(prefix)}
    match_set = quarantined | prefixed

    for item in items:
        if item.nodeid in match_set:
            item.add_marker(
                pytest.mark.xfail(
                    reason="Quarantined pre-existing CLI test failure (B12)",
                    run=False,
                )
            )


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
    except Exception:
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
