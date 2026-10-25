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
