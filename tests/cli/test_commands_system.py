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

        result = runner.invoke(system, ["check"])

        assert result.exit_code == 0, result.output
        assert "Service Check" in result.output

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
        assert "aitbc-blockchain-node" in cmd

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
        assert "/api/v1/status" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.system.get_config")
    @patch("aitbc_cli.commands.system.AITBCHTTPClient")
    def test_system_status_network_error(self, mock_http_class, mock_get_config, runner):
        """``system status`` handles NetworkError gracefully."""
        from aitbc_cli.commands.system import system
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(system, ["status"])

        # NetworkError is caught and an error message is printed (exit 0).
        assert result.exit_code == 0, result.output
        assert "Network error" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
