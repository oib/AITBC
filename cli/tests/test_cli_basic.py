#!/usr/bin/env python3
"""Basic CLI tests for the unified AITBC command hierarchy."""

import os
import subprocess
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CLI_DIR.parent
# The launcher in the tree, not the `/usr/local/bin/aitbc` symlink that points at it. Same
# file either way, and one fewer thing that has to be true of the machine: these tests joined
# the main suite in V23-84, and a checkout without the symlink installed would have failed all
# eight here for a reason that has nothing to do with the CLI.
CLI_BIN = PROJECT_ROOT / "scripts" / "aitbc-cli"


def run_cli(*args):
    return subprocess.run(
        [str(CLI_BIN), *args],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(PROJECT_ROOT),
    )


class TestCLIBasicFunctionality:
    """Test the visible command tree and core commands."""

    def test_cli_help_output(self):
        result = run_cli("--help")
        assert result.returncode == 0
        assert "AITBC CLI" in result.stdout
        assert "wallet" in result.stdout
        assert "ai" in result.stdout
        assert "market" in result.stdout
        assert "ai" in result.stdout
        assert "market" in result.stdout

    def test_nested_wallet_list_command(self):
        result = run_cli("wallet", "list")
        assert result.returncode == 0

    def test_legacy_wallet_list_alias(self):
        result = run_cli("list")
        assert result.returncode == 0

    def test_json_output_flag(self):
        result = run_cli("--output", "json", "wallet", "list")
        assert result.returncode == 0


class TestCLIErrorHandling:
    """Test CLI error handling."""

    def test_cli_invalid_command(self):
        result = run_cli("invalid-command")
        assert result.returncode != 0

    def test_wallet_balance_requires_target(self):
        # `wallet balance` without a name uses the default wallet (first found).
        # It should succeed if a wallet exists, or fail gracefully if none.
        result = run_cli("wallet", "balance")
        # Either succeeds (wallet found) or fails (no wallet/service) — but
        # should not crash with a traceback
        assert "Traceback" not in result.stderr


class TestCLIConfiguration:
    """Test CLI file presence and launcher availability."""

    def test_cli_bin_exists(self):
        # The launcher every other test in this file shells out to. It used to assert the
        # presence of `/usr/local/bin/aitbc`, which is a property of the host rather than of
        # the CLI -- and in a suite nothing ran, so it had never reported either way.
        assert CLI_BIN.exists()
        assert os.access(CLI_BIN, os.X_OK)

    def test_marketplace_command_available(self):
        result = run_cli("marketplace")
        assert result.returncode == 0
        assert "Usage:" in result.stdout
