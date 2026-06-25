"""
Analytics Commands Tests
Tests for analytics CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestAnalyticsCommands:
    """Test analytics command group"""

    def test_analytics_group_exists(self):
        """Test that analytics command group exists"""
        from aitbc_cli.commands.analytics import analytics

        assert analytics is not None
        assert hasattr(analytics, "name")

    def test_analytics_group_name(self):
        """Test analytics group name"""
        from aitbc_cli.commands.analytics import analytics

        assert analytics.name == "analytics"

    def test_analytics_group_has_summary_subcommand(self):
        """The ``summary`` subcommand is registered on the analytics group."""
        from aitbc_cli.commands.analytics import analytics

        assert "summary" in analytics.commands

    def test_analytics_group_has_monitor_subcommand(self):
        """The ``monitor`` subcommand is registered on the analytics group."""
        from aitbc_cli.commands.analytics import analytics

        assert "monitor" in analytics.commands

    @patch("aitbc_cli.commands.analytics.ChainAnalytics")
    @patch("aitbc_cli.commands.analytics.load_multichain_config")
    def test_analytics_summary_command(
        self, mock_load_config, mock_analytics_class, runner
    ):
        """``analytics summary`` returns cross-chain analysis from the mocked analytics layer."""
        mock_analytics = mock_analytics_class.return_value
        mock_analytics.get_cross_chain_analysis.return_value = {
            "total_chains": 3,
            "active_chains": 2,
            "alerts_summary": {"total_alerts": 1, "critical_alerts": 0},
            "resource_usage": {
                "total_memory_mb": 512.0,
                "total_disk_mb": 1024.0,
                "total_clients": 5,
                "total_agents": 3,
            },
            "performance_comparison": {
                "chain-1": {"tps": 10.5, "block_time": 2.0, "health_score": 85.0},
            },
        }

        from aitbc_cli.commands.analytics import analytics

        result = runner.invoke(analytics, ["summary"])

        assert result.exit_code == 0, result.output
        mock_load_config.assert_called_once()
        mock_analytics.get_cross_chain_analysis.assert_called_once()

    @patch("aitbc_cli.commands.analytics.ChainAnalytics")
    @patch("aitbc_cli.commands.analytics.load_multichain_config")
    def test_analytics_summary_single_chain(
        self, mock_load_config, mock_analytics_class, runner
    ):
        """``analytics summary --chain-id`` returns single-chain performance summary."""
        mock_analytics = mock_analytics_class.return_value
        mock_analytics.get_chain_performance_summary.return_value = {
            "chain_id": "chain-1",
            "time_range_hours": 24,
            "data_points": 100,
            "health_score": 85.0,
            "active_alerts": 0,
            "statistics": {
                "tps": {"avg": 10.5},
                "block_time": {"avg": 2.0},
                "gas_price": {"avg": 1000},
            },
        }

        from aitbc_cli.commands.analytics import analytics

        result = runner.invoke(analytics, ["summary", "--chain-id", "chain-1"])

        assert result.exit_code == 0, result.output
        mock_analytics.get_chain_performance_summary.assert_called_once_with("chain-1", 24)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
