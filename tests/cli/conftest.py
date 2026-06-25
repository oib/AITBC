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

from cli_mocks import (  # noqa: E402
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
