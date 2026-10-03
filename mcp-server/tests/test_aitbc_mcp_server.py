"""Tests for the AITBC MCP server command building."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

# The mcp-server directory is not a package, so add it to the path for tests.
MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server


def _load_isolated_server():
    """Load aitbc_mcp_server as a private module object.

    ``test_aitbc_mcp_cli_tools.py`` replaces ``mcp_server._run_remote`` with a
    recorder at import time and never restores it.  Tests that must exercise
    the real remote-execution path therefore load the server module under a
    private name whose globals are untouched.
    """
    spec = importlib.util.spec_from_file_location("aitbc_mcp_server_isolated", MCP_SERVER_DIR / "aitbc_mcp_server.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestExecutionContext:
    """Tests for _execution_context target/mode resolution."""

    def test_remote_host_reports_ssh_target(self):
        """A non-local host reports the ssh user@host target and mode 'ssh'."""
        with (
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
            mock.patch.object(mcp_server, "_ssh_target", return_value="root@hub.aitbc"),
        ):
            ctx = mcp_server._execution_context("hub.aitbc")
        assert ctx == {"host": "hub.aitbc", "target": "root@hub.aitbc", "mode": "ssh"}

    def test_local_host_reports_local(self):
        """A local host reports target 'local' and mode 'local'."""
        with mock.patch.object(mcp_server, "_is_local_host", return_value=True):
            ctx = mcp_server._execution_context("mcp-host")
        assert ctx == {"host": "mcp-host", "target": "local", "mode": "local"}


class TestRunRemoteTargetVisibility:
    """_run_remote results must name where the command ran."""

    def test_ssh_result_includes_target_and_mode(self):
        """Regression: the 127/zsh failure only showed 'host', not the ssh target."""
        server = _load_isolated_server()
        run = mock.Mock(
            return_value=_completed(
                returncode=127,
                stderr="zsh:1: datei oder Verzeichnis nicht gefunden: /usr/local/bin/aitbc\n",
            )
        )
        with (
            mock.patch.object(server, "_is_local_host", return_value=False),
            mock.patch.object(server, "_ssh_target", return_value="root@hub.aitbc"),
            mock.patch.object(server.subprocess, "run", run),
        ):
            result = server._run_remote(
                "hub.aitbc", "/usr/local/bin/aitbc --output=json system restart --service=aitbc-market"
            )
        assert result["host"] == "hub.aitbc"
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"
        assert result["returncode"] == 127
        argv = run.call_args[0][0]
        assert argv[0] == "ssh"
        assert "root@hub.aitbc" in argv
        assert argv[-1] == "/usr/local/bin/aitbc --output=json system restart --service=aitbc-market"

    def test_local_result_includes_target_and_mode(self):
        server = _load_isolated_server()
        run = mock.Mock(return_value=_completed(stdout="{}"))
        with (
            mock.patch.object(server, "_is_local_host", return_value=True),
            mock.patch.object(server.subprocess, "run", run),
        ):
            result = server._run_remote("localhost", "aitbc blockchain height")
        assert result["host"] == "localhost"
        assert result["target"] == "local"
        assert result["mode"] == "local"
        assert result["returncode"] == 0

    def test_missing_ssh_binary_still_reports_target(self):
        server = _load_isolated_server()
        with (
            mock.patch.object(server, "_is_local_host", return_value=False),
            mock.patch.object(server, "_ssh_target", return_value="root@hub.aitbc"),
            mock.patch.object(server.subprocess, "run", side_effect=FileNotFoundError("ssh")),
        ):
            result = server._run_remote("hub.aitbc", "true")
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"
        assert result["returncode"] == -1


class TestDryRunTargetVisibility:
    """Dry-run and confirmation-required responses must name the resolved target."""

    def test_build_dry_run_includes_context(self):
        with (
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
            mock.patch.object(mcp_server, "_ssh_target", return_value="root@hub.aitbc"),
        ):
            result = mcp_server._build_dry_run("note", "the-command", host="hub.aitbc")
        assert result["dry_run"] is True
        assert result["host"] == "hub.aitbc"
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"
        assert result["command"] == "the-command"
        assert result["note"] == "note"

    def test_require_confirm_dry_run_includes_context(self):
        with (
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
            mock.patch.object(mcp_server, "_ssh_target", return_value="root@hub.aitbc"),
        ):
            result = mcp_server._require_confirm(True, False, "the-command", host="hub.aitbc")
        assert result is not None
        assert result["dry_run"] is True
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"

    def test_require_confirm_unconfirmed_includes_context(self):
        with (
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
            mock.patch.object(mcp_server, "_ssh_target", return_value="root@hub.aitbc"),
        ):
            result = mcp_server._require_confirm(False, False, "the-command", host="hub.aitbc")
        assert result is not None
        assert result["error"] == "Confirmation required"
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"

    def test_dry_run_without_host_keeps_legacy_shape(self):
        result = mcp_server._build_dry_run("note", "the-command")
        assert result == {"dry_run": True, "command": "the-command", "note": "note"}


class TestRestartServiceTargetVisibility:
    """Regression tests for the restart_service-wrong-host incident (2026-10-03).

    The confirmed call ran ``ssh root@hub.aitbc``, which lands on the jump
    host, not the hub container. Neither the dry-run preview nor the failure
    result named the resolved target, so the misrouting was invisible.
    """

    _HOSTS = {
        "roles": {"hub": "hub.aitbc"},
        "default_host": "hub.aitbc",
        "ssh_user": "root",
    }

    def test_dry_run_shows_resolved_ssh_target(self):
        with (
            mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)),
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
        ):
            result = json.loads(mcp_server.restart_service(service="aitbc-market", role="hub"))
        assert result["dry_run"] is True
        assert result["host"] == "hub.aitbc"
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"
        assert "aitbc-market" in result["command"]

    def test_unconfirmed_call_shows_resolved_ssh_target(self):
        with (
            mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)),
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
        ):
            result = json.loads(mcp_server.restart_service(service="aitbc-market", role="hub", dry_run=False))
        assert result["error"] == "Confirmation required"
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"

    def test_executed_result_shows_where_it_ran(self):
        server = _load_isolated_server()
        run = mock.Mock(
            return_value=_completed(
                returncode=127,
                stderr="zsh:1: datei oder Verzeichnis nicht gefunden: /usr/local/bin/aitbc\n",
            )
        )
        with (
            mock.patch.object(server, "_HOSTS_CONFIG", dict(self._HOSTS)),
            mock.patch.object(server, "_is_local_host", return_value=False),
            mock.patch.object(server.subprocess, "run", run),
        ):
            result = json.loads(server.restart_service(service="aitbc-market", role="hub", dry_run=False, confirm=True))
        assert result["host"] == "hub.aitbc"
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"
        assert result["returncode"] == 127
        argv = run.call_args[0][0]
        assert "root@hub.aitbc" in argv

    def test_generated_tool_dry_run_shows_target(self):
        import aitbc_mcp_cli_tools_generated_restart as generated

        with (
            mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)),
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
        ):
            result = json.loads(generated.aitbc_restart(dry_run_opt=None, role_opt=None, role="hub"))
        assert result["dry_run"] is True
        assert result["host"] == "hub.aitbc"
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"

    def test_generated_tool_unconfirmed_shows_target(self):
        import aitbc_mcp_cli_tools_generated_restart as generated

        with (
            mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)),
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
        ):
            result = json.loads(generated.aitbc_restart(dry_run_opt=None, role_opt=None, role="hub", dry_run=False))
        assert result["error"] == "Confirmation required"
        assert result["target"] == "root@hub.aitbc"
        assert result["mode"] == "ssh"


class TestListNodesTargetVisibility:
    def test_list_nodes_shows_ssh_target_per_role(self):
        hosts = {
            "roles": {"hub": "hub.aitbc", "shop": "node2"},
            "default_host": "hub.aitbc",
            "ssh_user": "root",
        }
        with (
            mock.patch.object(mcp_server, "_HOSTS_CONFIG", hosts),
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
        ):
            result = json.loads(mcp_server.list_nodes())
        nodes = {node["role"]: node for node in result["nodes"]}
        assert nodes["hub"]["target"] == "root@hub.aitbc"
        assert nodes["hub"]["mode"] == "ssh"
        assert nodes["shop"]["target"] == "root@node2"
