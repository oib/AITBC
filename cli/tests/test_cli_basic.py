#!/usr/bin/env python3
"""Basic CLI tests for the unified AITBC command hierarchy."""

import subprocess
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CLI_DIR.parent
CLI_BIN = Path("/usr/local/bin/aitbc")


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
        assert "blockchain" in result.stdout
        assert "ai" in result.stdout
        assert "market" in result.stdout

    def test_cli_version_output(self):
        result = run_cli("--version")
        assert result.returncode == 0
        assert "2.1.0" in result.stdout

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
        result = run_cli("wallet", "balance")
        assert result.returncode != 0
        assert "Error: Wallet name is required" in result.stdout


class TestCLIConfiguration:
    """Test CLI file presence and launcher availability."""

    def test_cli_bin_exists(self):
        assert CLI_BIN.exists()

    def test_explorer_command_available(self):
        result = run_cli("explorer", "--help")
        assert result.returncode == 0
        assert "Blockchain Explorer" in result.stdout
