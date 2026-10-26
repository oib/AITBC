"""
System Commands Tests
Tests for system CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestSystemCommands:
    """Test system command group"""

    def test_system_group_exists(self):
        """Test that system command group exists"""
        from aitbc_cli.commands.system import system

        assert system is not None
        assert hasattr(system, "name")

    def test_system_group_name(self):
        """Test system group name"""
        from aitbc_cli.commands.system import system

        assert system.name == "system"

    def test_system_group_has_architect_subcommand(self):
        """The ``architect`` subcommand is registered on the system group."""
        from aitbc_cli.commands.system import system

        assert "architect" in system.commands

    def test_system_group_has_audit_subcommand(self):
        """The ``audit`` subcommand is registered on the system group."""
        from aitbc_cli.commands.system import system

        assert "audit" in system.commands

    def test_system_group_has_check_subcommand(self):
        """The ``check`` subcommand is registered on the system group."""
        from aitbc_cli.commands.system import system

        assert "check" in system.commands

    def test_system_group_has_restart_subcommand(self):
        """The ``restart`` subcommand is registered on the system group."""
        from aitbc_cli.commands.system import system

        assert "restart" in system.commands

    def test_system_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the system group."""
        from aitbc_cli.commands.system import system

        assert "status" in system.commands

    def test_system_architect_command(self, runner):
        """``system architect`` outputs the system architecture overview."""
        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["architect"])

        assert result.exit_code == 0, result.output
        assert "System Architecture" in result.output

    def test_system_audit_command(self, runner):
        """``system audit`` outputs the system audit report."""
        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["audit"])

        assert result.exit_code == 0, result.output
        assert "System Audit" in result.output

    def test_system_check_command(self, runner):
        """``system check`` checks service configuration."""
        from aitbc_cli.commands.system import system

        # Asks for the human rendering on purpose: the assertion is on the
        # title banner, and output() suppresses that for json/yaml/csv so a
        # machine-readable stream stays parseable.
        result = runner.invoke(system, ["check"], obj={"output": "table", "output_format": "table"})

        assert result.exit_code == 0, result.output
        assert "System Health Check" in result.output

    def test_system_check_with_service(self, runner):
        """``system check --service`` checks a specific service."""
        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["check", "--service", "blockchain-node"])

        assert result.exit_code == 0, result.output
        assert "blockchain-node" in result.output

    @patch("subprocess.run")
    def test_system_restart_command(self, mock_run, runner):
        """``system restart`` restarts a systemd service via subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["restart", "--service", "blockchain-node"])

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "systemctl" in cmd
        assert "aitbc-blockchain-node.service" in cmd

    @patch("aitbc_cli.commands.system.get_config")
    @patch("aitbc_cli.commands.system.AITBCHTTPClient")
    def test_system_status_command(self, mock_http_class, mock_get_config, runner):
        """``system status`` fetches system status from coordinator-api."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"status": "healthy", "services": 5}

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["status"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/health" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.system.get_config")
    @patch("aitbc_cli.commands.system.AITBCHTTPClient")
    def test_system_status_network_error(self, mock_http_class, mock_get_config, runner):
        """``system status`` handles NetworkError gracefully."""
        from aitbc_cli.commands.system import system
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(system, ["status"])

        # NetworkError is reported and the command fails.
        assert result.exit_code != 0, result.output
        assert "Network error" in result.output


class TestSystemLogsCommand:
    """``system logs`` --since/--grep options (DEV-5)."""

    def _mock_ok(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "log output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

    @patch("subprocess.run")
    def test_logs_default_argv_unchanged(self, mock_run, runner):
        """Without the new options the journalctl argv is identical."""
        self._mock_ok(mock_run)

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["logs", "--service", "blockchain-node"])

        assert result.exit_code == 0, result.output
        cmd = mock_run.call_args[0][0]
        assert cmd == ["journalctl", "-n", "50", "-u", "aitbc-blockchain-node.service", "--no-pager"]

    @patch("subprocess.run")
    def test_logs_since_and_grep_reach_journalctl(self, mock_run, runner):
        """--since/--grep are passed to journalctl as argv (no shell)."""
        self._mock_ok(mock_run)

        from aitbc_cli.commands.system import system

        result = runner.invoke(
            system,
            ["logs", "--service", "blockchain-node", "--since", "10 min ago", "--grep", "ERROR"],
        )

        assert result.exit_code == 0, result.output
        cmd = mock_run.call_args[0][0]
        assert "--since" in cmd
        assert "10 min ago" in cmd
        assert "--grep=ERROR" in cmd

    @patch("subprocess.run")
    def test_logs_rejects_newline_in_since(self, mock_run, runner):
        """--since must not contain newlines."""
        self._mock_ok(mock_run)

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["logs", "--service", "x", "--since", "now\n; rm -rf /"])

        assert result.exit_code != 0
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_logs_rejects_overlong_grep(self, mock_run, runner):
        """--grep is bounded at 200 chars."""
        self._mock_ok(mock_run)

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["logs", "--service", "x", "--grep", "A" * 201])

        assert result.exit_code != 0
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_logs_rejects_newline_in_grep(self, mock_run, runner):
        """--grep must not contain newlines."""
        self._mock_ok(mock_run)

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["logs", "--service", "x", "--grep", "a\nb"])

        assert result.exit_code != 0
        mock_run.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
