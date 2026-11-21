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
        mock_client.get.return_value = {"status": "online"}

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

    pytest.main([__file__, "-v"])

    @patch("aitbc_cli.commands.monitor._monitoring_client")
    def test_monitor_history_success_rate_and_utc(self, mock_client_factory, runner, mock_config):
        """#2409: success_rate is over resolved jobs (completed+failed), and
        since/analyzed_at are timezone-aware UTC — canceled/expired must not
        read as failures and local-naive timestamps must not skew the window.
        """
        import json

        mock_client = mock_client_factory.return_value
        mock_client.get.return_value = {
            "jobs": {
                "total": 10,
                "completed": 4,
                "failed": 2,
                "canceled": 3,
                "expired": 1,
                "other": 0,
                "pending": 0,
            }
        }

        from aitbc_cli.commands.monitor import monitor

        result = runner.invoke(
            monitor,
            ["history", "--period", "24h"],
            obj={"output_format": "json", "config": mock_config},
        )

        assert result.exit_code == 0, result.output
        body = json.loads(result.output)
        summary = body["summary"]
        # 4 / (4+2) = 66.7% — not 4/10 = 40%
        assert summary["success_rate"] == "66.7%"
        assert summary["success_rate_basis"] == "completed / (completed + failed)"
        assert summary["canceled"] == 3
        assert summary["expired"] == 1
        assert "+00:00" in body["since"]
        assert "+00:00" in body["analyzed_at"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
