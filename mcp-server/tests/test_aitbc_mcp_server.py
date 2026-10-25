"""Tests for the AITBC MCP server command building."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

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


_GENERATED_MODULE_PREFIX = "aitbc_mcp_cli_tools_generated_"
# Metadata module carrying GENERATED_AITBC_GROUPS — it holds the group list
# itself, not tools for a CLI group named "groups".
_GROUPS_LIST_MODULE_STEM = "aitbc_mcp_cli_tools_generated_groups"


def _generated_tool_groups() -> set[str]:
    """Top-level CLI groups that have a generated per-group tool module."""
    names: set[str] = set()
    for path in MCP_SERVER_DIR.glob(f"{_GENERATED_MODULE_PREFIX}*.py"):
        stem = path.stem
        if stem in {_GROUPS_LIST_MODULE_STEM, "aitbc_mcp_cli_tools_generated"}:
            continue
        names.add(stem[len(_GENERATED_MODULE_PREFIX) :].replace("_", "-"))
    return names


class TestGeneratedGroupAllowlist:
    """The pivot allow-list must cover every group with generated MCP tools.

    SM-06/MCP-GROUPS-1: ten groups (incl. ``dispute`` and ``energy``) had
    registered generated tools whose read variants died at the
    ``ALL_AITBC_GROUPS`` gate with ``unknown aitbc group``.  The set is now
    derived from the generator-emitted group list so it cannot drift again;
    these tests pin the three-way consistency
    ``tool modules == GENERATED_AITBC_GROUPS ⊆ ALL_AITBC_GROUPS == CLI tree``.
    """

    def test_every_generated_group_is_allowed(self):
        missing = _generated_tool_groups() - set(mcp_server.ALL_AITBC_GROUPS)
        assert not missing, f"groups with generated MCP tools missing from ALL_AITBC_GROUPS: {sorted(missing)}"

    def test_group_list_matches_tool_modules(self):
        """The emitted group list agrees with the emitted per-group modules."""
        import aitbc_mcp_cli_tools_generated_groups as groups_mod

        assert set(groups_mod.GENERATED_AITBC_GROUPS) == _generated_tool_groups()

    def test_allowlist_matches_cli_tree(self):
        """The allow-list is exactly the real top-level CLI group set."""
        from aitbc_cli.core.main import cli

        cli_groups = set(cli.commands)
        unknown = set(mcp_server.ALL_AITBC_GROUPS) - cli_groups
        assert not unknown, f"ALL_AITBC_GROUPS names that are not CLI groups: {sorted(unknown)}"
        missing = cli_groups - set(mcp_server.ALL_AITBC_GROUPS)
        assert not missing, (
            f"CLI groups not reachable through the MCP pivot: {sorted(missing)} — emit tools for them "
            "or add a curated-only entry deliberately"
        )


class TestPivotNewlyAllowedGroups:
    """The pivot must reach groups that were missing from the allow-list."""

    @staticmethod
    def _fake_run_remote(host: str, command: str, timeout: int = 60) -> dict[str, object]:
        return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

    def test_run_pivot_dispute_active_executes(self):
        with mock.patch.object(mcp_server, "_run_remote", self._fake_run_remote):
            result = json.loads(mcp_server.run_aitbc_cli(group="dispute", subcommand="active", host="node0", dry_run=False))
        assert "error" not in result
        assert "dispute active" in str(result["command"])

    def test_read_pivot_energy_leaf_executes(self):
        with mock.patch.object(mcp_server, "_run_remote", self._fake_run_remote):
            result = json.loads(mcp_server.read_aitbc_cli(group="energy", subcommand=["floor"], host="node0"))
        assert "error" not in result
        assert "energy floor" in str(result["command"])

    def test_list_group_help_dispute(self):
        with mock.patch.object(mcp_server, "_run_remote", self._fake_run_remote):
            result = json.loads(mcp_server.list_aitbc_cli_group(group="dispute", host="node0"))
        assert "error" not in result
        assert "dispute --help" in str(result["command"])


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
            mock.patch.object(mcp_server, "_role_for_host", return_value="hub"),
        ):
            ctx = mcp_server._execution_context("hub.aitbc")
        assert ctx == {
            "host": "hub.aitbc",
            "resolved_host": "hub.aitbc",
            "role_used": "hub",
            "target": "root@hub.aitbc",
            "mode": "ssh",
        }

    def test_local_host_reports_local(self):
        """A local host reports target 'local' and mode 'local'."""
        with (
            mock.patch.object(mcp_server, "_is_local_host", return_value=True),
            mock.patch.object(mcp_server, "_role_for_host", return_value=None),
        ):
            ctx = mcp_server._execution_context("mcp-host")
        assert ctx == {
            "host": "mcp-host",
            "resolved_host": "mcp-host",
            "role_used": None,
            "target": "local",
            "mode": "local",
        }


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

    def test_local_run_remote_detaches_stdin(self):
        """WAL-1 F1: the CLI child must not inherit the server's stdio stream."""
        server = _load_isolated_server()
        run = mock.Mock(return_value=_completed(stdout="{}"))
        with (
            mock.patch.object(server, "_is_local_host", return_value=True),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("localhost", "aitbc blockchain height")
        assert run.call_args.kwargs["stdin"] is subprocess.DEVNULL

    def test_ssh_run_remote_detaches_stdin(self):
        server = _load_isolated_server()
        run = mock.Mock(return_value=_completed(stdout="{}"))
        with (
            mock.patch.object(server, "_is_local_host", return_value=False),
            mock.patch.object(server, "_ssh_target", return_value="root@hub.aitbc"),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("hub.aitbc", "true")
        assert run.call_args.kwargs["stdin"] is subprocess.DEVNULL

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


class TestSshMux:
    """Connection-reuse options in _ssh_opts / _run_remote (SSH-MUX-1)."""

    def test_mux_opts_default_on(self, monkeypatch):
        """Default: ControlMaster=auto + ControlPersist + ControlPath are added."""
        monkeypatch.delenv("AITBC_SSH_MUX", raising=False)
        opts = mcp_server._ssh_opts("hub.aitbc")
        assert "ControlMaster=auto" in opts
        assert f"ControlPersist={mcp_server.SSH_MUX_PERSIST}" in opts
        control_path = next(opt for opt in opts if opt.startswith("ControlPath="))
        assert ".ssh" in control_path
        assert "%C" in control_path

    def test_mux_opts_disabled_by_env(self, monkeypatch):
        """AITBC_SSH_MUX=0 removes every Control* option."""
        monkeypatch.setenv("AITBC_SSH_MUX", "0")
        opts = mcp_server._ssh_opts("hub.aitbc")
        assert not any(opt.startswith("Control") for opt in opts)

    def test_mux_opts_reach_run_remote_argv(self, monkeypatch):
        server = _load_isolated_server()
        monkeypatch.delenv("AITBC_SSH_MUX", raising=False)
        run = mock.Mock(return_value=_completed(stdout="{}"))
        with (
            mock.patch.object(server, "_is_local_host", return_value=False),
            mock.patch.object(server, "_ssh_target", return_value="root@hub.aitbc"),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("hub.aitbc", "true")
        argv = run.call_args[0][0]
        assert "ControlMaster=auto" in argv

    def test_mux_opts_absent_in_run_remote_argv_when_off(self, monkeypatch):
        server = _load_isolated_server()
        monkeypatch.setenv("AITBC_SSH_MUX", "0")
        run = mock.Mock(return_value=_completed(stdout="{}"))
        with (
            mock.patch.object(server, "_is_local_host", return_value=False),
            mock.patch.object(server, "_ssh_target", return_value="root@hub.aitbc"),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("hub.aitbc", "true")
        argv = run.call_args[0][0]
        assert not any(arg.startswith("Control") for arg in argv)

    def test_fake_ssh_records_mux_args(self, monkeypatch, tmp_path):
        """End-to-end through a real spawn: a fake `ssh` on PATH logs its argv."""
        log = tmp_path / "ssh-argv.log"
        fake_ssh = tmp_path / "ssh"
        fake_ssh.write_text('#!/bin/sh\nfor a in "$@"; do printf \'%s\\n\' "$a" >> "$FAKE_SSH_LOG"; done\nexit 0\n')
        fake_ssh.chmod(0o755)
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_SSH_LOG", str(log))
        monkeypatch.delenv("AITBC_SSH_MUX", raising=False)
        server = _load_isolated_server()
        with (
            mock.patch.object(server, "_is_local_host", return_value=False),
            mock.patch.object(server, "_ssh_target", return_value="root@hub.aitbc"),
        ):
            first = server._run_remote("hub.aitbc", "true")
            second = server._run_remote("hub.aitbc", "true")
        assert first["returncode"] == 0 and second["returncode"] == 0
        args = log.read_text().splitlines()
        assert "ControlMaster=auto" in args
        # Both calls to the same target name the same control socket, which is
        # what lets the second call share the first call's connection.
        control_paths = [a for a in args if a.startswith("ControlPath=")]
        assert len(control_paths) == 2 and control_paths[0] == control_paths[1]


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


class TestGetServiceLogsFilters:
    """DEV-5: since/grep parameters on get_service_logs."""

    def _call(self, **kwargs):
        captured: list[str] = []

        def fake(host: str, command: str, timeout: int = 60):
            captured.append(command)
            return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

        with mock.patch.object(mcp_server, "_run_remote", fake):
            result = json.loads(mcp_server.get_service_logs(**kwargs))
        return result, captured

    def test_since_and_grep_reach_command(self):
        result, captured = self._call(service="aitbc-market", lines=100, since="10 min ago", grep="ERROR", host="node2")
        assert result["returncode"] == 0
        cmd = captured[0]
        assert "system" in cmd and "logs" in cmd
        assert "--since=" in cmd and "10 min ago" in cmd
        assert "--grep=" in cmd and "ERROR" in cmd

    def test_defaults_omit_new_options(self):
        result, captured = self._call(service="aitbc-market", host="node2")
        assert result["returncode"] == 0
        assert "--since" not in captured[0]
        assert "--grep" not in captured[0]

    def test_injection_rejected_before_any_command(self):
        """Newline/CR/NUL and the 200-char limit are still refused."""
        for kwargs in (
            {"since": "10m\nreboot"},
            {"since": "10m\rreboot"},
            {"since": "10m\x00reboot"},
            {"grep": "a\ncat /etc/passwd"},
            {"grep": "a\x00cat /etc/passwd"},
            {"grep": "A" * 201},
            {"since": "x" * 201},
        ):
            result, captured = self._call(service="aitbc-market", host="node2", **kwargs)
            assert "error" in result, kwargs
            assert not captured

    def test_service_name_keeps_strict_blocklist(self):
        """The service feeds journalctl -u <unit> — metachars stay refused."""
        result, captured = self._call(service="aitbc-market;id", host="node2")
        assert "error" in result
        assert not captured

    def test_shell_metachars_reach_command_quoted(self):
        """Metacharacters are inert once shlex-quoted — alternation and
        friends now pass validation (gap-log row 20)."""
        for kwargs, needle in (
            ({"since": "10m; rm -rf /"}, "--since='10m; rm -rf /'"),
            ({"since": "10m$(whoami)"}, "--since='10m$(whoami)'"),
            ({"since": "10m`id`"}, "--since='10m`id`'"),
            ({"grep": "a|cat /etc/passwd"}, "--grep='a|cat /etc/passwd'"),
            ({"grep": "WARN|ERROR"}, "--grep='WARN|ERROR'"),
        ):
            result, captured = self._call(service="aitbc-market", host="node2", **kwargs)
            assert result["returncode"] == 0, kwargs
            assert needle in captured[0], (needle, captured[0])

    def test_priority_reaches_command(self):
        """CLI-5: priority maps to journalctl -p on the CLI side."""
        result, captured = self._call(service="aitbc-market", priority="err", host="node2")
        assert result["returncode"] == 0
        assert "--priority=err" in captured[0]

    def test_priority_validated(self):
        for bad in ("err;rm", "err|info", "e r r", "x" * 41):
            result, captured = self._call(service="aitbc-market", priority=bad, host="node2")
            assert "error" in result, bad
            assert not captured

    def test_severity_pattern_passes_flag_only(self):
        """The flag forwards as a bare switch — the regex is built CLI-side,
        so no '|' ever travels as user input through this tool."""
        result, captured = self._call(service="aitbc-market", severity_pattern=True, host="node2")
        assert result["returncode"] == 0
        assert "--severity-pattern" in captured[0]
        assert "--grep" not in captured[0]

    def test_severity_pattern_and_grep_mutually_exclusive(self):
        result, captured = self._call(service="aitbc-market", grep="OOM", severity_pattern=True, host="node2")
        assert "error" in result
        assert not captured

    def test_defaults_omit_priority_and_severity(self):
        result, captured = self._call(service="aitbc-market", host="node2")
        assert "--priority" not in captured[0]
        assert "--severity-pattern" not in captured[0]


class TestDestructiveClassification:
    """TOOL-1: the destructive gate must cover the audited mutating leaves.

    The classification sees only the subcommand tokens plus the group for
    exact-path entries — never the option values.  These pins lock the
    Phase-0 audit so a rename or refactor cannot silently reopen a gate.
    """

    @pytest.mark.parametrize(
        ("group", "subcommand"),
        [
            # pre-existing coverage that must keep working
            ("wallet", ["send"]),
            ("wallet", ["bridge", "sell", "lock"]),
            ("wallet", ["bridge", "sell", "quote"]),
            ("exchange-island", ["cancel"]),
            ("transactions", ["batch"]),
            # TOOL-1 additions — each was verified mutating in the audit
            ("exchange", ["node", "set-payout"]),
            ("wallet", ["earn"]),
            ("wallet", ["liquidity-claim"]),
            ("wallet", ["multisig-create"]),
            ("wallet", ["switch"]),
            ("agent", ["register-identity"]),
            ("agent", ["subscribe"]),
            ("agent", ["workflow", "create-workflow"]),
            ("agent", ["config-set"]),
            ("agent-task", ["hire"]),
            ("agent-wallet", ["rebalance"]),
            ("agent-msg", ["request-coins"]),
            ("agent-msg", ["ping"]),
            ("ai", ["pay"]),
            ("ai", ["refund-sweep"]),
            ("bootstrap", ["bootstrap-env"]),
            ("bridge", ["attest"]),
            ("bridge", ["confirm"]),
            ("bridge", ["ingest-header"]),
            ("bridge", ["proof"]),
            ("bridge", ["sign-proof"]),
            ("bridge", ["store-header"]),
            ("bridge", ["register-validator"]),
            ("bridge", ["unlock"]),
            ("coin-requests", ["approve"]),
            ("coin-requests", ["reject"]),
            ("coin-requests", ["reopen"]),
            ("coin-requests", ["request"]),
            ("coin-requests", ["reconcile"]),
            ("config", ["set"]),
            ("config", ["unset"]),
            ("config", ["edit"]),
            ("config", ["reset"]),
            ("config", ["set-secret"]),
            ("config", ["import-config"]),
            ("config", ["profiles", "load"]),
            ("config", ["profiles", "save"]),
            ("compliance", ["export-audit"]),
            ("crosschain", ["confirm"]),
            ("crosschain", ["swap"]),
            ("dispute", ["arbitrator", "authorize"]),
            ("dispute", ["auto-adjudicate"]),
            ("dispute", ["evidence", "add"]),
            ("dispute", ["resolve"]),
            ("edge", ["database", "delete-db"]),
            ("edge", ["database", "init-db"]),
            ("edge", ["database", "sync-db"]),
            ("edge", ["gpu", "remove-gpu"]),
            ("edge", ["gpu", "scan-gpus"]),
            ("edge", ["metrics", "delete-metric"]),
            ("edge", ["metrics", "record"]),
            ("edge", ["serve", "cancel-request"]),
            ("edge", ["serve", "submit-request"]),
            ("edge", ["transfer"]),
            ("edge", ["island", "join"]),
            ("edge", ["island", "leave"]),
            ("exchange", ["add-liquidity"]),
            ("exchange", ["create-pair"]),
            ("exchange", ["start-trading"]),
            ("genesis", ["init"]),
            ("genesis", ["reset"]),
            ("genesis", ["sync-from-hub"]),
            ("governance", ["aggregate-votes"]),
            ("governance", ["close"]),
            ("governance", ["execute-cross-chain"]),
            ("governance", ["propagate"]),
            ("gpu-onchain", ["allocate"]),
            ("gpu-onchain", ["deregister"]),
            ("grant", ["disburse"]),
            ("ipfs", ["island", "subscribe"]),
            ("ipfs", ["island", "swarm-key"]),
            ("ipfs", ["pin"]),
            ("ipfs", ["unpin"]),
            ("ipfs", ["upload"]),
            ("ipfs", ["download"]),
            ("market", ["host"]),
            ("market", ["hermes"]),
            ("market", ["process-video"]),
            ("market", ["download"]),
            ("market", ["offer-cancel"]),
            ("market", ["gpu", "quote"]),
            ("market", ["exchange", "deposit-eth"]),
            ("network", ["force-sync"]),
            ("network", ["set-sync-source"]),
            ("network", ["heartbeat"]),
            ("network", ["subscribe"]),
            ("node", ["add"]),
            ("node", ["remove"]),
            ("node", ["bridge", "approve"]),
            ("node", ["bridge", "reject"]),
            ("node", ["bridge", "request"]),
            ("node", ["island", "join"]),
            ("node", ["island", "leave"]),
            ("operations", ["agent", "deregister"]),
            ("operations", ["agent", "message"]),
            ("operations", ["ai", "submit-job"]),
            ("operations", ["governance", "delegate"]),
            ("operations", ["governance", "proposal"]),
            ("oracle", ["store"]),
            ("platform", ["init-platform"]),
            ("plugin", ["load"]),
            ("reinvest", ["policy"]),
            ("reputation", ["create-profile"]),
            ("reputation", ["feedback"]),
            ("resource", ["allocate"]),
            ("resource", ["deallocate"]),
            ("resource", ["optimize"]),
            ("security", ["patch"]),
            ("service", ["harden"]),
            ("system", ["env-set"]),
            ("system", ["run-script"]),
            ("tee", ["attest"]),
            ("tee", ["keygen"]),
            ("tee", ["launch"]),
            ("trade", ["lock-escrow"]),
            ("trade", ["settle"]),
            ("trade", ["match-all"]),
            ("trade", ["register-chain"]),
            ("trade", ["sync"]),
            ("cluster", ["sync"]),
            ("blockchain", ["migrate"]),
            ("deploy", ["deploy-brand"]),
            ("contract", ["call"]),
            ("http", ["call"]),
        ],
    )
    def test_known_mutating_leaf_classified(self, group, subcommand):
        assert mcp_server._is_aitbc_subcommand_destructive(subcommand, group), f"{group} {subcommand}"

    @pytest.mark.parametrize(
        ("group", "subcommand"),
        [
            # bare top-level mutating commands have no subcommand token at all
            ("start", None),
            ("stop", []),
            ("restart", None),
            ("update", None),
            ("stake", None),
            ("unstake", None),
            ("liquidity-stake", None),
        ],
    )
    def test_bare_mutating_group_classified(self, group, subcommand):
        assert mcp_server._is_aitbc_subcommand_destructive(subcommand, group), group

    @pytest.mark.parametrize(
        ("group", "subcommand"),
        [
            # leaf-name collisions: these mutate and match by exact path
            ("monitor", ["alerts"]),
            ("monitor", ["webhooks"]),
            ("trade", ["match"]),
            ("wallet", ["export"]),
            ("crosschain", ["bridge"]),
            ("edge", ["island", "bridge"]),
            ("dispute", ["file"]),
            ("ai", ["service", "test"]),
            ("sync", ["bulk"]),
        ],
    )
    def test_exact_path_entries_classified(self, group, subcommand):
        assert mcp_server._is_aitbc_subcommand_destructive(subcommand, group), f"{group} {subcommand}"

    @pytest.mark.parametrize(
        ("group", "subcommand"),
        [
            # reads sharing a leaf name with a mutating command elsewhere
            ("market", ["match"]),
            ("config", ["export"]),
            ("prometheus", ["alerts"]),
            ("analytics", ["alerts"]),
            ("system", ["file"]),
            ("node", ["test"]),
            ("wallet", ["bridge", "status"]),
            ("wallet", ["bridge", "float"]),
            ("wallet", ["bridge", "settlements"]),
            ("node", ["bridge", "list-bridges"]),
            ("sync", ["status"]),
            # plain reads
            ("monitor", ["campaigns"]),
            ("monitor", ["campaign-stats"]),
            ("system", ["logs"]),
            ("system", ["status"]),
            ("explorer", ["block"]),
            ("trade", ["discover"]),
            ("wallet", ["balance"]),
            ("agent", ["discover", "agents"]),
            ("zk", ["verify"]),
            ("genesis", ["verify"]),
            ("exchange", ["verify"]),
            ("wallet", ["request-payment"]),
        ],
    )
    def test_read_leaves_not_classified(self, group, subcommand):
        assert not mcp_server._is_aitbc_subcommand_destructive(subcommand, group), f"{group} {subcommand}"

    def test_string_subcommand_splits_for_classification(self):
        """'sell lock' as one string must classify the same as a list."""
        assert mcp_server._is_aitbc_subcommand_destructive("bridge sell lock", "wallet")
        assert mcp_server._is_aitbc_subcommand_destructive("sell lock", "wallet")
        assert not mcp_server._is_aitbc_subcommand_destructive("bridge status", "wallet")

    def test_list_valued_options_build_repeated_flags(self):
        command = mcp_server._build_aitbc_cli_command(
            "http", "call", ["market", "v1/x"], {"expect-status": ["401", "404"]}, "json"
        )
        assert "--expect-status=401" in command
        assert "--expect-status=404" in command

    def test_read_tool_rejects_nested_destructive_path(self):
        result = json.loads(
            mcp_server.read_aitbc_cli(
                group="wallet",
                subcommand=["bridge", "sell", "lock"],
                host="node2",
            )
        )
        assert "error" in result
        assert "destructive" in result["error"]

    def test_read_tool_rejects_exact_path(self):
        result = json.loads(mcp_server.read_aitbc_cli(group="monitor", subcommand=["alerts"], host="node2"))
        assert "error" in result

    def test_read_tool_rejects_bare_mutating_group(self):
        result = json.loads(mcp_server.read_aitbc_cli(group="start", host="node2"))
        assert "error" in result

    def test_run_tool_requires_confirm_for_new_leaf(self):
        result = json.loads(
            mcp_server.run_aitbc_cli(
                group="exchange",
                subcommand=["node", "set-payout"],
                host="node2",
                dry_run=False,
                confirm=False,
            )
        )
        assert result.get("error") == "Confirmation required"


# Commands whose decorators wrap the callback past inspect.getsource; pinned
# so a rename still forces a human look rather than silently skipping.
_WRAPPER_LOOP_PATHS = {
    "blockchain block",
    "blockchain height",
    "http call",
    "market cancel",
    "market download",
    "market hermes",
    "market host",
    "market jobs",
    "market list",
    "market match",
    "market offer-disable",
    "market offer-list",
    "market process",
    "market providers",
    "market run",
    "market transcribe",
    "system check",
    "update",
}

# Leaves whose callback source matches the mutation signal but which were
# read and verified read-only in the TOOL-1 Phase-0 audit: pure GETs,
# systemctl/subprocess reads, POST-for-search (/v1/agents/discover, ipfs
# pin/ls), POST-for-verify endpoints, a verifier subprocess, and in-process
# simulators.  A NEW leaf matching the signal must be classified or added
# here deliberately — never silently.
_KNOWN_READ_SIGNAL_PATHS = {
    "agent discover agents",
    "agent verify-identity",
    "agent-comm discover",
    "agent-comm list",
    "agent-comm network",
    "agent-task result",
    "analytics dashboard",
    "blockchain monitor",
    # subprocess.run is the read vector, not a mutation: it shells the monitor's
    # own `list`/`status` admin verbs and hardcodes them — no write verb (write-off,
    # abandon, manual-payout) is reachable through this command.
    "bridge deposits",
    "config export",
    "dispute evidence verify",
    "energy floor",
    "energy provider profile",
    "energy suggest",
    "exchange verify",
    "explorer activity-timeline",
    "explorer block",
    "explorer block-by-hash",
    "explorer blocks-by-address",
    "explorer chain-head",
    "explorer chains",
    "explorer latest-blocks",
    "explorer network-stats",
    "explorer non-empty-blocks",
    "explorer provider-reputation",
    "explorer search-transactions",
    "explorer top-addresses",
    "explorer transaction",
    "explorer transaction-by-hash",
    "genesis verify",
    "ipfs list",
    "market gpu status",
    "market status",
    "messaging list",
    "mining list",
    "mining status",
    "monitor metrics",
    "operations agent list",
    "operations ai status",
    "oracle listings",
    "prometheus alert-history",
    "prometheus alerts",
    "prometheus check",
    "reputation leaderboard",
    "reputation metrics",
    "reputation profile",
    "reputation trust-score",
    "simulate blockchain",
    "system cat",
    "system cron",
    "system env-names",
    "system logs",
    "system show",
    "system status",
    "trade discover",
    "trade watch",
    "transactions search",
    "transactions status",
    "wallet list",
    "wallet transactions",
    "workflow list",
    "zk verify",
}

_MUT_SIGNAL = re.compile(
    r"\.post\(|\.put\(|\.delete\(|\.patch\(|_save_wallet|_resave_wallet|write_text|unlink\(|"
    r"systemctl|subprocess\.|click\.confirm|sign_transaction|/rpc/transaction|broadcast|"
    r"requests\.post|_send_transaction|_submit|shutil\.|\.write\(|open\(.*w|json\.dump"
)

# Option names that mark a mutating command (confirmation gates, destructive
# force flags, dry-run previews).
_CONFIRM_STYLE_OPTS = {"confirm", "yes", "force", "dry_run", "i_am_sure"}


class TestDestructiveStructuralAudit:
    """Walk the real Click tree: a mutating leaf must be classified.

    Signals: a confirm/yes/force/dry-run option on the command, a
    ``click.confirm(`` call, or a mutating call in the callback source.
    The exception lists are pinned — a new mutating command fails the test
    until a human classifies it.
    """

    def _leaves(self):
        import click
        from aitbc_cli.core.main import cli

        def walk(cmd, path):
            if isinstance(cmd, click.Group):
                for name, sub in sorted(cmd.commands.items()):
                    yield from walk(sub, path + [name])
            else:
                yield cmd, path

        return list(walk(cli, []))

    def test_confirm_style_commands_are_classified(self):
        """Every command carrying a confirm/yes/force/dry-run option or
        calling click.confirm must classify as destructive — no exceptions."""
        import click
        import inspect

        for cmd, path in self._leaves():
            full = " ".join(path)
            try:
                src = inspect.getsource(cmd.callback)
            except (OSError, TypeError, ValueError):
                src = ""
            has_confirm_opt = any(
                isinstance(p, click.Option) and _CONFIRM_STYLE_OPTS & {o.lstrip("-").replace("-", "_") for o in p.opts}
                for p in cmd.params
            )
            if has_confirm_opt or "click.confirm(" in src:
                assert mcp_server._is_aitbc_subcommand_destructive(path[1:], path[0]), (
                    f"{full} asks for confirmation but is not gated"
                )

    def test_signal_bearing_leaf_is_classified_or_pinned_read(self):
        import inspect

        for cmd, path in self._leaves():
            full = " ".join(path)
            try:
                src = inspect.getsource(cmd.callback)
            except (OSError, TypeError, ValueError):
                assert full in _WRAPPER_LOOP_PATHS, f"{full} callback source unreadable — audit it, then pin"
                continue
            if _MUT_SIGNAL.search(src):
                classified = mcp_server._is_aitbc_subcommand_destructive(path[1:], path[0])
                assert classified or full in _KNOWN_READ_SIGNAL_PATHS, (
                    f"{full} matches a mutating-call signal but is neither classified destructive nor a pinned read"
                )

    def test_exception_lists_stay_in_sync_with_tree(self):
        """Pinned sets must not drift: every entry must still be a real leaf,
        and wrapper-loop detection must agree with the pin."""
        import inspect

        tree_paths = {" ".join(p) for _, p in self._leaves()}
        for full in _KNOWN_READ_SIGNAL_PATHS:
            assert full in tree_paths, f"{full} no longer exists — drop it from the read pin"
        unreadable = set()
        for cmd, path in self._leaves():
            try:
                inspect.getsource(cmd.callback)
            except (OSError, TypeError, ValueError):
                unreadable.add(" ".join(path))
        assert unreadable == _WRAPPER_LOOP_PATHS


class TestHostForRoleRouting:
    """MCP-ROUTING-1: role/host resolution must be explicit, never silent.

    ``host`` used to override ``role`` silently and an unmapped role string
    fell through to be used as the ssh target itself. Both are now refused.
    """

    _HOSTS = {
        "roles": {"hub": "hub.aitbc", "customer": "node0", "shop": "node2"},
        "default_host": "hub.aitbc",
        "ssh_user": "root",
    }

    def test_role_resolves_through_map(self):
        with mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)):
            assert mcp_server._host_for_role("customer") == "node0"

    def test_host_only_resolves_verbatim(self):
        with mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)):
            assert mcp_server._host_for_role(None, "node2") == "node2"

    def test_user_at_host_override_allowed(self):
        with mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)):
            assert mcp_server._host_for_role(None, "root@hub.aitbc") == "root@hub.aitbc"

    def test_default_host_when_neither_given(self):
        with mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)):
            assert mcp_server._host_for_role(None) == "hub.aitbc"

    def test_role_and_host_together_refused(self):
        """A call that can reach another node's wallet must not silently pick a side."""
        with (
            mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)),
            pytest.raises(mcp_server.ToolError, match="either role or host"),
        ):
            mcp_server._host_for_role("customer", "hub.aitbc")

    def test_unknown_role_refused_instead_of_ssh_to_role_name(self):
        """The old fallthrough ran ``ssh … bogus-role`` — now refused."""
        with (
            mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)),
            pytest.raises(mcp_server.ToolError, match="unknown role"),
        ):
            mcp_server._host_for_role("bogus-role")

    def test_option_looking_host_refused(self):
        """`-oProxyCommand=…` style values must never reach ssh argv."""
        with mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)):
            for bad in ("-oProxyCommand=/bin/echo marker", "-F/dev/null", "-v"):
                with pytest.raises(mcp_server.ToolError, match="invalid host"):
                    mcp_server._host_for_role(None, bad)

    def test_host_with_whitespace_or_equals_refused(self):
        with mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)):
            for bad in ("hub.aitbc -oBatchMode=no", "a=b", "hub .aitbc", " "):
                with pytest.raises(mcp_server.ToolError, match="invalid host"):
                    mcp_server._host_for_role(None, bad)

    def test_envelope_carries_resolved_host_and_role(self):
        """Dry-run/result envelopes name where the call actually went."""
        with (
            mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)),
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
            mock.patch.object(mcp_server, "_ssh_target", return_value="root@node0"),
        ):
            ctx = mcp_server._execution_context("node0")
        assert ctx["resolved_host"] == "node0"
        assert ctx["role_used"] == "customer"
        assert ctx["target"] == "root@node0"

    def test_adhoc_host_envelope_has_no_role(self):
        with (
            mock.patch.object(mcp_server, "_HOSTS_CONFIG", dict(self._HOSTS)),
            mock.patch.object(mcp_server, "_is_local_host", return_value=False),
        ):
            ctx = mcp_server._execution_context("ad-hoc.example")
        assert ctx["resolved_host"] == "ad-hoc.example"
        assert ctx["role_used"] is None

class TestResultEnvelopeStatus:
    """SM-07/SM-09: every command-result envelope carries the failure signal.

    SP-13-class CLI commands exit 0 while printing an error; through MCP they
    arrived as success-status results with the error only in the body, so an
    agent could not tell the call failed.  ``_run_remote`` now stamps ``ok``
    and ``exit_code`` on every envelope, ``error_hint`` when a body pattern —
    not the return code — made ``ok`` false, and ``timed_out`` on timeouts.
    """

    def _run(self, stdout="", stderr="", rc=0):
        server = _load_isolated_server()

        def fake_run(*a, **k):
            return subprocess.CompletedProcess(a[0], rc, stdout, stderr)

        with mock.patch.object(server.subprocess, "run", fake_run):
            return server._run_remote("localhost", "aitbc probe")

    def test_clean_run_marks_ok(self):
        result = self._run('{"height": 5005}\n')
        assert result["ok"] is True
        assert result["exit_code"] == 0
        assert "error_hint" not in result

    def test_nonzero_exit_marks_not_ok(self):
        result = self._run("", "boom\n", rc=2)
        assert result["ok"] is False
        assert result["exit_code"] == 2

    @pytest.mark.parametrize(
        "body",
        [
            "Error getting transaction status: GET request failed: 404 Client Error\n",
            "Error listing proposals: http://localhost:8105/v1/governance/proposals\n",
            "Network error: GET request failed: Retry attempts exhausted\n",
            "Webhook test failed: POST request failed\n",
            "Authentication failed for node aitbc-primary\n",
            "Explorer API unavailable: GET request failed: 400 Client Error\n",
            "Market service not available at http://127.0.0.1:8102\n",
            "Wallet 'missing-wallet' not found\n",
            "Transaction 0xdeadbeef not found\n",
            "Request req-123 not found.\n",
            "Block at height 128452 not found\n",
            "No stored credential found for 'client' in 'default'\n",
            "jobs failed\n",
            "✗ Job failed\n",
            "Traceback (most recent call last):\n  File ...\n",
            "Usage: aitbc wallet [OPTIONS]\n",
            "Error: No such command 'nope'\n",
            '{"summary": {"error": "Could not fetch job data"}}\n',
            '{"status": "unreachable ([Errno 111] Connection refused)"}\n',
            # error may sit below a banner within the scan window
            "───── AITBC Dashboard ─────\nRefreshing every 5s\n\nError fetching data: 401\n",
        ],
    )
    def test_exit_zero_error_body_marks_not_ok(self, body):
        result = self._run(body)
        assert result["ok"] is False
        assert result["exit_code"] == 0
        assert result.get("error_hint")

    @pytest.mark.parametrize(
        "body",
        [
            '{"failed": 0, "jobs": 3}\n',  # JSON key, not a failure report
            "items processed; Failed: 0\n",  # zero-failure statistic
            "5 passed, 0 failed\n",
            "No agents found\n",
            "No alerts found\n",
            "No stored credentials for environment 'default'\n",
            "No open orders for AIT/ETH\n",
            '{"error": null, "data": []}\n',
            '{"message": "No chains found", "hint": "pass --node-url ..."}\n',
            "Pending transactions: 0\n",
        ],
    )
    def test_clean_read_stays_ok(self, body):
        """A false ok:false on a successful read is worse than no flag."""
        result = self._run(body)
        assert result["ok"] is True, body

    def test_error_on_stderr_marks_not_ok(self):
        result = self._run("[1, 2]\n", "Failed to collect metrics: GET request failed: 401\n")
        assert result["ok"] is False
        assert result["error_hint"].startswith("Failed to collect metrics")

    def test_error_hint_omitted_when_returncode_flags(self):
        result = self._run("", "Error: whatever\n", rc=1)
        assert result["ok"] is False
        assert "error_hint" not in result

    def test_timeout_decodes_bytes_partial_output(self):
        """SM-09: TimeoutExpired stdout stays bytes even with text=True."""
        server = _load_isolated_server()

        def raise_timeout(*a, **k):
            exc = subprocess.TimeoutExpired(["aitbc"], 5)
            exc.stdout = b'{"partial": "\xe2\x80'  # truncated utf-8
            exc.stderr = b"partial err line"
            raise exc

        with mock.patch.object(server.subprocess, "run", raise_timeout):
            result = server._run_remote("localhost", "aitbc probe", timeout=5)
        assert result["ok"] is False
        assert result["exit_code"] == -1
        assert result["timed_out"] is True
        assert isinstance(result["stdout"], str)
        assert "b'" not in result["stdout"]  # never a bytes repr
        assert "timeout after 5s" in result["stderr"]
        assert "partial err line" in result["stderr"]

    def test_timeout_without_partial_output(self):
        server = _load_isolated_server()

        def raise_timeout(*a, **k):
            raise subprocess.TimeoutExpired(["aitbc"], 7)

        with mock.patch.object(server.subprocess, "run", raise_timeout):
            result = server._run_remote("localhost", "aitbc probe", timeout=7)
        assert result["ok"] is False
        assert result["timed_out"] is True
        assert result["stdout"] == ""
        assert result["stderr"] == "timeout after 7s"

    def test_json_stamps_ok_on_error_envelopes(self):
        assert json.loads(mcp_server._json({"error": "nope"}))["ok"] is False
        assert json.loads(mcp_server._json({"dry_run": True, "command": "x"}))["ok"] is True
        # explicit ok wins over the convention stamp
        assert json.loads(mcp_server._json({"error": "degraded", "ok": True}))["ok"] is True

    def test_destructive_refusal_envelope_is_not_ok(self):
        result = json.loads(mcp_server.read_aitbc_cli(group="monitor", subcommand=["alerts"], host="node2"))
        assert result["ok"] is False


class TestDestructivePathSplitting:
    """SM-05: the destructive-path gate must see the *effective* command path.

    Click consumes leading positionals as path tokens, so ``subcommand``
    tokens and ``args`` are interchangeable spellings of the same path —
    the gate must classify all of them identically.
    """

    @pytest.mark.parametrize(
        ("group", "subcommand", "args"),
        [
            ("monitor", ["alerts"], ["list"]),  # previously refused spelling
            ("monitor", ["alerts", "list"], None),  # the escape
            ("monitor", ["alerts", "test"], None),  # webhook POST leaf
            ("monitor", ["alerts list"], None),  # whitespace inside one element
            ("monitor", "alerts list", None),  # string spelling
            ("monitor", None, ["alerts", "remove"]),  # args wholly supply the path
            ("monitor", ["alerts"], ["remove"]),
            ("monitor", ["webhooks", "test"], None),
            ("wallet", ["export", "mywallet"], None),
            ("wallet", ["export"], ["mywallet"]),
            ("trade", ["match", "x"], None),
            ("dispute", ["file", "x"], None),
            ("sync", ["bulk", "x"], None),
            ("crosschain", ["bridge", "x"], None),
            ("edge", ["island", "bridge", "x"], None),
            ("ai", ["service", "test", "x"], None),
            ("start", ["node"], None),  # deeper token under a bare leaf
            ("ai", None, ["submit"]),  # args-only destructive leaf
            ("market", None, ["create"]),
        ],
    )
    def test_destructive_path_all_spellings(self, group, subcommand, args):
        assert mcp_server._is_aitbc_subcommand_destructive(subcommand, group, args), f"{group} {subcommand} {args}"

    @pytest.mark.parametrize(
        ("group", "subcommand", "args"),
        [
            ("monitor", ["campaigns"], None),
            ("monitor", ["campaign-stats"], ["cmp-1"]),
            ("market", ["match"], None),
            ("market", ["list"], None),
            ("prometheus", ["alerts"], None),
            ("analytics", ["alerts"], None),
            ("sync", ["status"], None),
            ("trade", ["discover"], None),
            ("wallet", ["balance"], ["genesis"]),
            ("ai", ["status"], ["job-abc123"]),
            ("version", None, None),
            ("monitor", ["history"], None),
        ],
    )
    def test_read_paths_stay_open(self, group, subcommand, args):
        assert not mcp_server._is_aitbc_subcommand_destructive(subcommand, group, args), f"{group} {subcommand} {args}"

    def test_read_tool_rejects_split_path_spelling(self):
        """The SM-05 escape: read_aitbc_cli must refuse deeper path tokens too."""
        result = json.loads(mcp_server.read_aitbc_cli(group="monitor", subcommand=["alerts", "list"], host="node2"))
        assert "error" in result
        assert "destructive" in result["error"]

    def test_read_tool_rejects_args_only_path(self):
        result = json.loads(mcp_server.read_aitbc_cli(group="monitor", subcommand=None, args=["alerts", "list"], host="node2"))
        assert "error" in result
        assert "destructive" in result["error"]

    def test_run_tool_requires_confirm_for_split_path(self):
        result = json.loads(
            mcp_server.run_aitbc_cli(
                group="monitor",
                subcommand=["alerts", "test"],
                host="node2",
                dry_run=False,
                confirm=False,
            )
        )
        assert result.get("error") == "Confirmation required"

class TestSplitPosixPrefix:
    """MCP-MISC-1/SM-11: POSIX prefixes in a command string become real
    child env/cwd on the local exec path."""

    def test_plain_command_untouched(self):
        env, cwd, argv = mcp_server._split_posix_prefix("aitbc blockchain height")
        assert env == {}
        assert cwd is None
        assert argv == ["aitbc", "blockchain", "height"]

    def test_env_assignments_peeled(self):
        env, cwd, argv = mcp_server._split_posix_prefix(
            "HOME=/var/tmp/sc AITBC_WALLET_DIR='/var/tmp/sc/wallets dir' aitbc wallet list"
        )
        assert env == {"HOME": "/var/tmp/sc", "AITBC_WALLET_DIR": "/var/tmp/sc/wallets dir"}
        assert cwd is None
        assert argv == ["aitbc", "wallet", "list"]

    def test_cd_clause_peeled_before_env(self):
        env, cwd, argv = mcp_server._split_posix_prefix("cd /var/tmp/sc && HOME=/var/tmp/sc aitbc wallet list")
        assert env == {"HOME": "/var/tmp/sc"}
        assert cwd == "/var/tmp/sc"
        assert argv == ["aitbc", "wallet", "list"]

    def test_mid_command_assignment_not_peeled(self):
        """Only leading NAME=value tokens are env; a later token stays argv."""
        env, cwd, argv = mcp_server._split_posix_prefix("aitbc wallet list --name=x")
        assert env == {}
        assert argv == ["aitbc", "wallet", "list", "--name=x"]


class TestLocalRunRemoteEnvCwd:
    """The local branch of _run_remote applies peeled prefixes via
    subprocess env=/cwd= instead of exec'ing the prefix as argv[0]."""

    def test_env_prefix_applied_to_child_env(self):
        server = _load_isolated_server()
        run = mock.Mock(return_value=_completed(stdout="{}"))
        with (
            mock.patch.object(server, "_is_local_host", return_value=True),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("localhost", "HOME=/var/tmp/sc aitbc blockchain height")
        argv = run.call_args[0][0]
        assert argv == ["aitbc", "blockchain", "height"]
        child_env = run.call_args.kwargs["env"]
        assert child_env["HOME"] == "/var/tmp/sc"
        # Parent environment is preserved underneath the override.
        assert "PATH" in child_env

    def test_cd_clause_applied_to_child_cwd(self):
        server = _load_isolated_server()
        run = mock.Mock(return_value=_completed(stdout="{}"))
        with (
            mock.patch.object(server, "_is_local_host", return_value=True),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("localhost", "cd /var/tmp/sc && HOME=/var/tmp/sc aitbc blockchain height")
        argv = run.call_args[0][0]
        assert argv == ["aitbc", "blockchain", "height"]
        assert run.call_args.kwargs["cwd"] == "/var/tmp/sc"
        assert run.call_args.kwargs["env"]["HOME"] == "/var/tmp/sc"

    def test_no_prefix_runs_without_env_or_cwd(self):
        server = _load_isolated_server()
        run = mock.Mock(return_value=_completed(stdout="{}"))
        with (
            mock.patch.object(server, "_is_local_host", return_value=True),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("localhost", "aitbc blockchain height")
        assert run.call_args.kwargs["env"] is None
        assert run.call_args.kwargs["cwd"] is None


class TestGenericCliEnvCwd:
    """MCP-MISC-1/SM-11: env/cwd parameters on run_aitbc_cli / read_aitbc_cli."""

    def _capture(self, server):
        captured: list[str] = []

        def fake(host: str, command: str, timeout: int = 60):
            captured.append(command)
            return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

        return captured, mock.patch.object(server, "_run_remote", fake)

    def test_env_prefix_reaches_read_command(self):
        captured, patcher = self._capture(mcp_server)
        with patcher:
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="wallet",
                    subcommand=["list"],
                    env={"HOME": "/var/tmp/mcp-scratch"},
                    host="node2",
                )
            )
        assert result["returncode"] == 0
        assert captured[0].startswith("HOME=/var/tmp/mcp-scratch ")
        assert "aitbc" in captured[0] and "wallet list" in captured[0]

    def test_env_and_cwd_render_as_posix_prefix(self):
        captured, patcher = self._capture(mcp_server)
        with patcher:
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="wallet",
                    subcommand=["list"],
                    env={"HOME": "/var/tmp/sc", "AITBC_WALLET_DIR": "/var/tmp/sc/wallets"},
                    cwd="/var/tmp/sc",
                    host="node2",
                )
            )
        assert result["returncode"] == 0
        assert captured[0].startswith("cd /var/tmp/sc && HOME=/var/tmp/sc AITBC_WALLET_DIR=/var/tmp/sc/wallets ")

    def test_env_prefix_shown_in_dry_run(self):
        result = json.loads(
            mcp_server.run_aitbc_cli(
                group="wallet",
                subcommand="create",
                options={"name": "scratch"},
                env={"HOME": "/var/tmp/sc"},
                dry_run=True,
                host="node2",
            )
        )
        assert result["dry_run"] is True
        assert result["command"].startswith("HOME=/var/tmp/sc ")

    def test_env_on_destructive_subcommand_still_needs_confirm(self):
        result = json.loads(
            mcp_server.run_aitbc_cli(
                group="wallet",
                subcommand="create",
                options={"name": "scratch"},
                env={"HOME": "/var/tmp/sc"},
                dry_run=False,
                confirm=False,
                host="node2",
            )
        )
        assert result["error"] == "Confirmation required"
        assert result["command"].startswith("HOME=/var/tmp/sc ")

    def test_secret_shaped_env_name_refused(self):
        for name in ("AITBC_API_KEY", "AITBC_JWT_SECRET", "AITBC_WALLET_PASSWORD", "MY_TOKEN"):
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="wallet",
                    subcommand=["list"],
                    env={name: "/var/tmp/sc"},
                    host="node2",
                )
            )
            assert "not allowed" in result["error"], name

    def test_non_allowlisted_env_name_refused(self):
        result = json.loads(
            mcp_server.read_aitbc_cli(
                group="wallet",
                subcommand=["list"],
                env={"PATH": "/var/tmp/sc"},
                host="node2",
            )
        )
        assert "not allowed" in result["error"]

    def test_env_value_outside_scratch_refused(self):
        for value in ("/etc/aitbc", "/var/tmp/../etc", "relative/path", "/var/lib/aitbc/wallets"):
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="wallet",
                    subcommand=["list"],
                    env={"HOME": value},
                    host="node2",
                )
            )
            assert "under /var/tmp" in result["error"], value

    def test_env_value_at_scratch_root_accepted(self):
        captured, patcher = self._capture(mcp_server)
        with patcher:
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="wallet",
                    subcommand=["list"],
                    env={"HOME": "/var/tmp"},
                    host="node2",
                )
            )
        assert result["returncode"] == 0

    def test_invalid_env_name_refused(self):
        result = json.loads(
            mcp_server.read_aitbc_cli(
                group="wallet",
                subcommand=["list"],
                env={"BAD;NAME": "/var/tmp/sc"},
                host="node2",
            )
        )
        assert "invalid environment variable name" in result["error"]

    def test_cwd_outside_scratch_refused(self):
        for value in ("/root", "/var/tmp/../etc", "tmp/scratch"):
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="wallet",
                    subcommand=["list"],
                    cwd=value,
                    host="node2",
                )
            )
            assert "under /var/tmp" in result["error"], value

    def test_no_env_no_cwd_unchanged(self):
        captured, patcher = self._capture(mcp_server)
        with patcher:
            result = json.loads(mcp_server.read_aitbc_cli(group="wallet", subcommand=["list"], host="node2"))
        assert result["returncode"] == 0
        assert not captured[0].startswith("cd ")
        assert "=" not in captured[0].split(" ", 1)[0]
