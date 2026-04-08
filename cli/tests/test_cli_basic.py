#!/usr/bin/env python3
"""Basic CLI tests for the unified AITBC command hierarchy."""

import importlib.util
import json
import subprocess
from pathlib import Path


CLI_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CLI_DIR.parent
CLI_FILE = CLI_DIR / "aitbc_cli.py"
UNIFIED_FILE = CLI_DIR / "unified_cli.py"
CLI_BIN = PROJECT_ROOT / "aitbc-cli"


def run_cli(*args):
    return subprocess.run(
        [str(CLI_BIN), *args],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(PROJECT_ROOT),
    )


class TestCLIImports:
    """Test direct file-based CLI module imports."""

    def test_cli_main_import(self):
        spec = importlib.util.spec_from_file_location("aitbc_cli_file", CLI_FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert callable(module.main)

    def test_unified_cli_import(self):
        spec = importlib.util.spec_from_file_location("unified_cli_file", UNIFIED_FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert callable(module.run_cli)


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
        json.loads(result.stdout or "[]")


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

    def test_cli_files_exist(self):
        assert CLI_FILE.exists()
        assert UNIFIED_FILE.exists()
        assert CLI_BIN.exists()

    def test_cli_file_contains_main(self):
        content = CLI_FILE.read_text()
        assert len(content) > 1000
        assert "def main" in content
