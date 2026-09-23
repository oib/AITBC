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
        """``performance benchmark`` measures real read latency against live RPC endpoints.

        The node has no server-side benchmark endpoint; the command samples
        ``/rpc/head``, ``/rpc/network-info`` and ``/rpc/mempool`` instead of the
        old (never-existing) ``POST /rpc/performance/benchmark``.
        """
        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = [
            {"height": 100},
            {"height": 100},
            {"height": 100},
            {"peers": ["a", "b"]},
            {"transactions": []},
        ]

        from aitbc_cli.commands.performance import performance

        result = runner.invoke(performance, ["benchmark"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_not_called()
        paths = [call.args[0] for call in mock_client.get.call_args_list]
        assert paths == ["/rpc/head", "/rpc/head", "/rpc/head", "/rpc/network-info", "/rpc/mempool"]

    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_performance_benchmark_errors_when_rpc_unreachable(self, mock_http_class, runner):
        """``performance benchmark`` aborts on NetworkError — no fabricated data."""
        from aitbc_cli.commands.performance import performance
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(performance, ["benchmark"])

        assert result.exit_code != 0
        assert "simulated" not in result.output

    def test_performance_optimize_not_implemented(self, runner):
        """``performance optimize`` reports honestly that the node has no such endpoint."""
        from aitbc_cli.commands.performance import performance

        result = runner.invoke(performance, ["optimize"])

        assert result.exit_code != 0
        assert "Not implemented" in result.output
        assert "simulated" not in result.output

    def test_performance_tune_not_implemented(self, runner):
        """``performance tune`` reports honestly that the node has no such endpoint."""
        from aitbc_cli.commands.performance import performance

        result = runner.invoke(performance, ["tune"])

        assert result.exit_code != 0
        assert "Not implemented" in result.output
        assert "simulated" not in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
