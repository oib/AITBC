"""CLI-5: ``aitbc system logs`` --priority/-p and --severity-pattern.

Both options land on the same journalctl argv list — these tests pin the
exact argv so a refactor can't silently drop the mapping or let user input
reach the pattern.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import system as system_module


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def journalctl():
    """Capture the journalctl argv instead of running it."""
    calls = []

    class _Result:
        returncode = 0
        stdout = "log output\n"
        stderr = ""

    def _run(cmd, **kw):
        calls.append(cmd)
        return _Result()

    with patch.object(system_module.subprocess, "run", side_effect=_run) as m:
        m.calls = calls
        yield m


def _invoke(runner, *args):
    return runner.invoke(system_module.logs, list(args), obj={"output_format": "json"})


class TestPriority:
    def test_priority_maps_to_journalctl_p(self, runner, journalctl):
        result = _invoke(runner, "--service", "blockchain-node", "-p", "err")
        assert result.exit_code == 0, result.output
        cmd = journalctl.calls[0]
        i = cmd.index("-p")
        assert cmd[i + 1] == "err"

    def test_priority_long_form(self, runner, journalctl):
        result = _invoke(runner, "--service", "wallet", "--priority", "warning")
        assert result.exit_code == 0, result.output
        cmd = journalctl.calls[0]
        assert cmd[cmd.index("-p") + 1] == "warning"

    @pytest.mark.parametrize("level", ["0", "3", "7", "emerg", "crit", "info", "debug", "err..warning", "2..5"])
    def test_valid_levels_accepted(self, runner, journalctl, level):
        result = _invoke(runner, "--service", "wallet", "-p", level)
        assert result.exit_code == 0, result.output

    @pytest.mark.parametrize("level", ["bogus", "fatal", "8", "-1", "err..fatal", "err|info", "err;rm", "em erg"])
    def test_invalid_levels_rejected(self, runner, journalctl, level):
        result = _invoke(runner, "--service", "wallet", "-p", level)
        assert result.exit_code != 0
        assert "journalctl level" in result.output
        assert journalctl.calls == []


class TestSeverityPattern:
    def test_flag_maps_to_fixed_grep(self, runner, journalctl):
        result = _invoke(runner, "--service", "wallet", "--severity-pattern")
        assert result.exit_code == 0, result.output
        cmd = journalctl.calls[0]
        greps = [t for t in cmd if t.startswith("--grep=")]
        assert greps == ["--grep=WARN|WARNING|ERROR|CRITICAL|FATAL"]

    def test_mutually_exclusive_with_grep(self, runner, journalctl):
        result = _invoke(runner, "--service", "wallet", "--grep", "OOM", "--severity-pattern")
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output
        assert journalctl.calls == []

    def test_no_user_input_reaches_pattern(self, runner, journalctl):
        """The pattern is a fixed constant — nothing user-supplied lands in it."""
        result = _invoke(runner, "--service", "wallet", "--severity-pattern", "--since", "10 min ago")
        assert result.exit_code == 0, result.output
        cmd = journalctl.calls[0]
        greps = [t for t in cmd if t.startswith("--grep=")]
        assert greps == ["--grep=WARN|WARNING|ERROR|CRITICAL|FATAL"]

    def test_combined_with_priority(self, runner, journalctl):
        result = _invoke(runner, "--service", "wallet", "-p", "info", "--severity-pattern")
        assert result.exit_code == 0, result.output
        cmd = journalctl.calls[0]
        assert "-p" in cmd and any(t.startswith("--grep=") for t in cmd)


class TestUnchangedDefaults:
    def test_plain_invocation_has_no_new_flags(self, runner, journalctl):
        result = _invoke(runner, "--service", "blockchain-node")
        assert result.exit_code == 0, result.output
        cmd = journalctl.calls[0]
        assert "-p" not in cmd
        assert not any(t.startswith("--grep=") for t in cmd)
        assert cmd[:3] == ["journalctl", "-n", "50"]

    def test_grep_still_validated(self, runner, journalctl):
        result = _invoke(runner, "--service", "wallet", "--grep", "a\nb")
        assert result.exit_code != 0
        assert journalctl.calls == []
