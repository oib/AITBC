"""Tests for the AITBC MCP server command building."""

from __future__ import annotations

import sys
from pathlib import Path

# The mcp-server directory is not a package, so add it to the path for tests.
MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server


class TestBuildAitbcCliCommand:
    """Tests for _build_aitbc_cli_command."""

    def test_null_option_emits_bare_flag(self):
        """A null option value becomes a bare flag."""
        command = mcp_server._build_aitbc_cli_command("ai", "cancel", None, {"refund": None}, "json")
        assert "--refund" in command
        assert "--refund=''" not in command
        assert "--refund=None" not in command

    def test_empty_string_option_emits_bare_flag(self):
        """An empty-string option value becomes a bare flag."""
        command = mcp_server._build_aitbc_cli_command("ai", "cancel", None, {"refund": ""}, "json")
        assert "--refund" in command
        assert "--refund=''" not in command

    def test_value_option_is_quoted(self):
        """A non-empty option value is emitted as --key=value with shlex quoting."""
        command = mcp_server._build_aitbc_cli_command("exchange-island", "orderbook", ["AIT/ETH"], {"limit": "10"}, "json")
        assert "--limit=10" in command

    def test_positional_args_are_included(self):
        """Positional arguments appear after the subcommand."""
        command = mcp_server._build_aitbc_cli_command("node", "info", ["node-1"], {}, "json")
        assert "node-1" in command


class TestAitbcGroupWhitelist:
    """Tests for the CLI group allowlist."""

    def test_exchange_island_group_allowed(self):
        """run_aitbc_cli should accept the exchange-island group."""
        assert "exchange-island" in mcp_server.ALL_AITBC_GROUPS

    def test_gpu_group_allowed(self):
        """run_aitbc_cli should accept the gpu group."""
        assert "gpu" in mcp_server.ALL_AITBC_GROUPS

    def test_governance_group_allowed(self):
        """run_aitbc_cli should accept the governance group."""
        assert "governance" in mcp_server.ALL_AITBC_GROUPS


class TestManageAiJobCommand:
    """Tests for manage_ai_job command string construction."""

    def test_accept_action_builds_command(self):
        """action=accept builds the ai accept command."""
        command = mcp_server._build_aitbc_cli_command("ai", "accept", None, {"job-id": "abc"}, "json")
        assert "aitbc" in command
        assert "ai accept" in command
        assert "--job-id=abc" in command

    def test_cancel_action_builds_command(self):
        """action=cancel with refund builds the ai cancel --refund command."""
        command = mcp_server._build_aitbc_cli_command("ai", "cancel", None, {"job-id": "abc", "refund": None}, "json")
        assert "ai cancel" in command
        assert "--refund" in command
        assert "--refund=''" not in command

    def test_refund_action_builds_command(self):
        """action=refund builds the ai refund command."""
        command = mcp_server._build_aitbc_cli_command("ai", "refund", None, {"job-id": "abc", "reason": "test"}, "json")
        assert "ai refund" in command
        assert "--reason=test" in command
