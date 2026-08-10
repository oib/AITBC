"""V23-33 — the CLI entrypoint must import.

The v0.23 remediation commit (`6ce2c7405`) renamed `decrypt_private_key` to
`decode_private_key` **at its call sites only**, leaving the definition in
`aitbc_cli/utils/wallet.py` untouched. `aitbc_cli.commands.operations` is imported
unconditionally by `aitbc_cli.core.main`, so the resulting `ImportError` took down the whole
tool: `aitbc --version` failed, and so did every one of its ~60 command groups.

Seventeen tests reported it. All seventeen were read as an established baseline for weeks,
because they failed with the same opaque `ImportError` and nobody followed it to the cause.
A single test that says "the CLI does not start" is harder to file under scenery.

These tests deliberately import through the package rather than a subprocess, so they run
against the tree under test -- see the `sys.path` note in `tests/conftest.py`.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest


def test_cli_entrypoint_imports() -> None:
    """`python -m aitbc_cli` starts here. If this raises, the CLI does not exist."""
    module = importlib.import_module("aitbc_cli.core.main")
    assert callable(module.main)


def test_cli_exposes_its_command_groups() -> None:
    from aitbc_cli.core.main import cli

    assert len(cli.commands) > 20, f"only {len(cli.commands)} command groups registered"


@pytest.mark.parametrize(
    "name",
    sorted(
        m.name
        for m in pkgutil.iter_modules(importlib.import_module("aitbc_cli.commands").__path__)
        if not m.name.startswith("_")
    ),
)
def test_every_command_module_imports(name: str) -> None:
    """Each command module in turn, so a failure names the module rather than the package.

    `operations` is the one that broke; parametrising means the next one to break is
    identified by name instead of collapsing the whole suite into one opaque error.
    """
    importlib.import_module(f"aitbc_cli.commands.{name}")


def test_wallet_helper_names_match_their_call_sites() -> None:
    """The specific defect: an import of a name the module does not define.

    Asserted directly rather than only implied by the import tests above, because the failure
    mode is a rename applied to one side of a call.
    """
    from aitbc_cli.utils import wallet

    assert hasattr(wallet, "decrypt_private_key")
    # It decrypts -- AES-256-GCM or Fernet over PBKDF2 -- so it must not be called `decode_*`.
    # `decode_value` was renamed from `decrypt_value` in the same commit and that rename was
    # correct: that function was always plain base64. This one is not.
    assert not hasattr(wallet, "decode_private_key")
