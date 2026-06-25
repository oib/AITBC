"""
Performance Commands Tests
Tests for performance CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestPerformanceCommands:
    """Test performance command group"""

    def test_performance_group_exists(self):
        """Test that performance command group exists"""
        from aitbc_cli.commands.performance import performance

        assert performance is not None
        assert hasattr(performance, "name")

    def test_performance_group_name(self):
        """Test performance group name"""
        from aitbc_cli.commands.performance import performance

        assert performance.name == "performance"

    def test_performance_group_has_benchmark_subcommand(self):
        """The ``benchmark`` subcommand is registered on the performance group."""
        from aitbc_cli.commands.performance import performance

        assert "benchmark" in performance.commands

    def test_performance_group_has_optimize_subcommand(self):
        """The ``optimize`` subcommand is registered on the performance group."""
        from aitbc_cli.commands.performance import performance

        assert "optimize" in performance.commands

    def test_performance_group_has_tune_subcommand(self):
        """The ``tune`` subcommand is registered on the performance group."""
        from aitbc_cli.commands.performance import performance

        assert "tune" in performance.commands

    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_performance_benchmark_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``performance benchmark`` returns benchmark data from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"tps": 5000, "latency_ms": 25}

        from aitbc_cli.commands.performance import performance

        result = runner.invoke(performance, ["benchmark"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/rpc/performance/benchmark" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_performance_benchmark_falls_back_on_network_error(self, mock_http_class, runner):
        """``performance benchmark`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.performance import performance
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(performance, ["benchmark"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_performance_optimize_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``performance optimize`` returns optimization data from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"optimization_applied": True, "gain_pct": 15}

        from aitbc_cli.commands.performance import performance

        result = runner.invoke(performance, ["optimize"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/rpc/performance/optimize" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_performance_optimize_falls_back_on_network_error(self, mock_http_class, runner):
        """``performance optimize`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.performance import performance
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(performance, ["optimize"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_performance_tune_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``performance tune`` returns tuning data from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"parameters_tuned": ["cache_size", "batch_size"]}

        from aitbc_cli.commands.performance import performance

        result = runner.invoke(performance, ["tune"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/rpc/performance/tune" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_performance_tune_falls_back_on_network_error(self, mock_http_class, runner):
        """``performance tune`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.performance import performance
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(performance, ["tune"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
