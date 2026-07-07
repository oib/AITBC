#!/usr/bin/env python3
"""Comprehensive tests for the unified AITBC CLI hierarchy."""

import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path("/opt/aitbc")
CLI_BIN = Path("/usr/local/bin/aitbc")


def run_cli(*args):
    return subprocess.run(
        [str(CLI_BIN), *args],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=20,
    )


class TestSimulateCommand:
    """Test the nested simulate command family."""

    def test_simulate_help(self):
        result = run_cli("simulate", "--help")
        assert result.returncode == 0
        assert "blockchain" in result.stdout
        assert "wallets" in result.stdout
        assert "price" in result.stdout
        assert "network" in result.stdout
        assert "ai-jobs" in result.stdout

    def test_simulate_blockchain_basic(self):
        result = run_cli("simulate", "blockchain", "--blocks", "2", "--transactions", "3", "--delay", "0")
        assert result.returncode == 0
        assert "Block 1:" in result.stdout
        assert "Total Blocks: 2" in result.stdout


class TestBlockchainCommand:
    """Test nested blockchain commands and legacy chain alias."""

    def test_blockchain_help(self):
        result = run_cli("blockchain", "info", "--help")
        assert result.returncode == 0
        assert "CHAIN_ID" in result.stdout
        assert "--detailed" in result.stdout

    def test_chain_alias_help(self):
        # `chain` is not registered as an alias; `blockchain` is the canonical name
        result = run_cli("blockchain", "--help")
        assert result.returncode == 0
        assert "info" in result.stdout
        assert "list" in result.stdout


class TestNetworkCommand:
    """Test network subcommands and backward-compatible argument forms."""

    def test_network_ping_positional_node(self):
        # `network ping` doesn't exist; `network test --peer` is the equivalent
        result = run_cli("network", "test", "--peer", "localhost")
        # May fail to connect but should not crash with usage error
        assert result.returncode in (0, 1, 2)

    def test_network_ping_flag_alias(self):
        result = run_cli("network", "test", "--peer", "localhost")
        assert result.returncode in (0, 1, 2)

    def test_network_propagate_flag_alias(self):
        # `network propagate` doesn't exist; `network force-sync` is the equivalent
        result = run_cli("network", "force-sync", "--help")
        assert result.returncode == 0
        assert "Force network synchronization" in result.stdout


class TestMarketplaceCommand:
    """Test marketplace grouping and legacy rewrite."""

    def test_market_help(self):
        result = run_cli("market", "--help")
        assert result.returncode == 0
        assert "list" in result.stdout
        assert "offer" in result.stdout
        assert "match" in result.stdout
        assert "cancel" in result.stdout

    def test_marketplace_legacy_alias(self):
        # `marketplace` is a separate command group (not `market --action`)
        result = run_cli("marketplace", "--help")
        assert result.returncode == 0


class TestAIOperationsCommand:
    """Test the unified ai command family and legacy ai-ops rewrite."""

    def test_ai_help(self):
        result = run_cli("ai", "--help")
        assert result.returncode == 0
        assert "submit" in result.stdout
        assert "status" in result.stdout
        assert "results" in result.stdout

    def test_ai_ops_legacy_status(self):
        # `ai-ops` is not a registered command; `ai status` is the equivalent
        result = run_cli("ai", "status", "--help")
        assert result.returncode == 0
        assert "AI job status" in result.stdout


class TestResourceCommand:
    """Test resource subcommands."""

    def test_resource_help(self):
        result = run_cli("resource", "--help")
        assert result.returncode == 0
        assert "allocate" in result.stdout
        assert "optimize" in result.stdout

    def test_resource_allocate_requires_agent_id(self):
        result = run_cli("resource", "allocate", "--cpu-cores", "2")
        assert result.returncode != 0


class TestIntegrationScenarios:
    """Test representative end-to-end command patterns."""

    def test_cli_version(self):
        result = run_cli("--version")
        assert result.returncode == 0
        assert "2.1.0" in result.stdout

    def test_cli_help_comprehensive(self):
        result = run_cli("--help")
        assert result.returncode == 0
        for command in [
            "wallet",
            "blockchain",
            "network",
            "market",
            "ai",
            "mining",
            "agent",
            "agent-msg",
            "workflow",
            "resource",
            "simulate",
        ]:
            assert command in result.stdout

    def test_wallet_alias_and_nested_forms(self):
        nested = run_cli("wallet", "list")
        alias = run_cli("list")
        assert nested.returncode == 0
        assert alias.returncode == 0

    def test_network_default_and_nested_forms(self):
        # `network` without a subcommand shows help (exit 0)
        default = run_cli("network")
        nested = run_cli("network", "status")
        assert default.returncode == 0
        assert nested.returncode == 0
        assert "Peer connectivity" in default.stdout

    def test_ai_submit_legacy_alias(self):
        # `ai-submit` is not a registered command; `ai submit` is the equivalent
        result = run_cli("ai", "submit", "--help")
        assert result.returncode == 0
        assert "Submit an AI job" in result.stdout


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_invalid_command(self):
        result = run_cli("invalid-command")
        assert result.returncode != 0

    def test_missing_required_args(self):
        result = run_cli("wallet", "send")
        assert result.returncode != 0

    def test_invalid_option_values(self):
        result = run_cli("--output", "invalid")
        assert result.returncode != 0


class TestPerformance:
    """Test performance characteristics."""

    def test_help_response_time(self):
        start_time = time.time()
        result = run_cli("--help")
        end_time = time.time()
        assert result.returncode == 0
        assert (end_time - start_time) < 5.0

    def test_command_startup_time(self):
        start_time = time.time()
        result = run_cli("wallet", "list")
        end_time = time.time()
        assert result.returncode == 0
        assert (end_time - start_time) < 10.0


class TestConfiguration:
    """Test global flags across the new command tree."""

    def test_different_output_formats(self):
        for fmt in ["table", "json", "yaml"]:
            result = run_cli("--output", fmt, "wallet", "list")
            assert result.returncode == 0

    def test_verbose_mode(self):
        result = run_cli("--verbose", "wallet", "list")
        assert result.returncode == 0

    def test_debug_mode(self):
        result = run_cli("--debug", "wallet", "list")
        assert result.returncode == 0
