"""
Monitor Commands Tests
Tests for monitor CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestMonitorCommands:
    """Test monitor command group"""

    def test_monitor_group_exists(self):
        """Test that monitor command group exists"""
        from aitbc_cli.commands.monitor import monitor

        assert monitor is not None
        assert hasattr(monitor, "name")

    def test_monitor_group_name(self):
        """Test monitor group name"""
        from aitbc_cli.commands.monitor import monitor

        assert monitor.name == "monitor"

    def test_monitor_group_has_dashboard_subcommand(self):
        """The ``dashboard`` subcommand is registered on the monitor group."""
        from aitbc_cli.commands.monitor import monitor

        assert "dashboard" in monitor.commands

    def test_monitor_group_has_metrics_subcommand(self):
        """The ``metrics`` subcommand is registered on the monitor group."""
        from aitbc_cli.commands.monitor import monitor

        assert "metrics" in monitor.commands

    def test_monitor_group_has_alerts_subcommand(self):
        """The ``alerts`` subcommand is registered on the monitor group."""
        from aitbc_cli.commands.monitor import monitor

        assert "alerts" in monitor.commands

    def test_monitor_group_has_campaigns_subcommand(self):
        """The ``campaigns`` subcommand is registered on the monitor group."""
        from aitbc_cli.commands.monitor import monitor

        assert "campaigns" in monitor.commands

    def test_monitor_group_has_history_subcommand(self):
        """The ``history`` subcommand is registered on the monitor group."""
        from aitbc_cli.commands.monitor import monitor

        assert "history" in monitor.commands

    def test_monitor_campaigns_command(self, runner):
        """``monitor campaigns`` lists incentive campaigns from local config."""
        from aitbc_cli.commands.monitor import monitor

        result = runner.invoke(monitor, ["campaigns"])

        assert result.exit_code == 0, result.output

    def test_monitor_alerts_list_command(self, runner):
        """``monitor alerts list`` lists configured alerts (or shows none)."""
        from aitbc_cli.commands.monitor import monitor

        result = runner.invoke(monitor, ["alerts", "list"])

        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.commands.monitor.AITBCHTTPClient")
    def test_monitor_metrics_command(self, mock_http_class, runner, mock_config):
        """``monitor metrics`` collects and displays system metrics."""
        mock_client = mock_http_class.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "online"}
        mock_client.get.return_value = mock_response

        from aitbc_cli.commands.monitor import monitor

        result = runner.invoke(
            monitor,
            ["metrics"],
            obj={"output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.commands.monitor.AITBCHTTPClient")
    def test_monitor_metrics_handles_offline(self, mock_http_class, runner, mock_config):
        """``monitor metrics`` gracefully handles offline services."""
        from aitbc_cli.commands.monitor import monitor
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(
            monitor,
            ["metrics"],
            obj={"output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.commands.monitor.AITBCHTTPClient")
    def test_monitor_history_command(self, mock_http_class, runner, mock_config):
        """``monitor history`` displays historical data analysis."""
        mock_client = mock_http_class.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_client.get.return_value = mock_response

        from aitbc_cli.commands.monitor import monitor

        result = runner.invoke(
            monitor,
            ["history"],
            obj={"output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
