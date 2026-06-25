"""
Simulate Commands Tests
Tests for simulate CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestSimulateCommands:
    """Test simulate command group"""

    def test_simulate_group_exists(self):
        """Test that simulate command group exists"""
        from aitbc_cli.commands.simulate import simulate

        assert simulate is not None
        assert hasattr(simulate, "name")

    def test_simulate_group_name(self):
        """Test simulate group name"""
        from aitbc_cli.commands.simulate import simulate

        assert simulate.name == "simulate"

    def test_simulate_group_has_blockchain_subcommand(self):
        """The ``blockchain`` subcommand is registered on the simulate group."""
        from aitbc_cli.commands.simulate import simulate

        assert "blockchain" in simulate.commands

    def test_simulate_group_has_wallets_subcommand(self):
        """The ``wallets`` subcommand is registered on the simulate group."""
        from aitbc_cli.commands.simulate import simulate

        assert "wallets" in simulate.commands

    def test_simulate_group_has_price_subcommand(self):
        """The ``price`` subcommand is registered on the simulate group."""
        from aitbc_cli.commands.simulate import simulate

        assert "price" in simulate.commands

    def test_simulate_group_has_network_subcommand(self):
        """The ``network`` subcommand is registered on the simulate group."""
        from aitbc_cli.commands.simulate import simulate

        assert "network" in simulate.commands

    def test_simulate_group_has_run_subcommand(self):
        """The ``run`` subcommand is registered on the simulate group."""
        from aitbc_cli.commands.simulate import simulate

        assert "run" in simulate.commands

    def test_simulate_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the simulate group."""
        from aitbc_cli.commands.simulate import simulate

        assert "status" in simulate.commands

    def test_simulate_blockchain_command(self, runner):
        """``simulate blockchain`` produces blocks and a summary."""
        from aitbc_cli.commands.simulate import simulate

        result = runner.invoke(
            simulate,
            ["blockchain", "--blocks", "2", "--transactions", "3", "--delay", "0"],
        )

        assert result.exit_code == 0, result.output
        assert "Simulation Summary" in result.output
        assert "Total Blocks: 2" in result.output

    def test_simulate_wallets_command(self, runner):
        """``simulate wallets`` creates wallets and simulates transactions."""
        from aitbc_cli.commands.simulate import simulate

        result = runner.invoke(
            simulate,
            ["wallets", "--wallets", "2", "--transactions", "1"],
        )

        assert result.exit_code == 0, result.output
        assert "Final Wallet Balances" in result.output

    def test_simulate_price_command(self, runner):
        """``simulate price`` simulates price movements and shows statistics."""
        from aitbc_cli.commands.simulate import simulate

        result = runner.invoke(
            simulate,
            ["price", "--timesteps", "3", "--delay", "0"],
        )

        assert result.exit_code == 0, result.output
        assert "Price Statistics" in result.output

    def test_simulate_network_command(self, runner):
        """``simulate network`` simulates network topology and node failures."""
        from aitbc_cli.commands.simulate import simulate

        result = runner.invoke(
            simulate,
            ["network", "--nodes", "2", "--network-delay", "0", "--failure-rate", "0"],
        )

        assert result.exit_code == 0, result.output
        assert "Network Topology" in result.output

    @patch("aitbc_cli.commands.simulate.get_config")
    @patch("aitbc_cli.commands.simulate.AITBCHTTPClient")
    def test_simulate_run_command(self, mock_http_class, mock_get_config, runner):
        """``simulate run`` submits a simulation to the coordinator-api."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"simulation_id": "sim-123", "status": "started"}

        from aitbc_cli.commands.simulate import simulate

        result = runner.invoke(simulate, ["run", "test-scenario"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/simulate/run" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.commands.simulate.get_config")
    @patch("aitbc_cli.commands.simulate.AITBCHTTPClient")
    def test_simulate_run_command_with_params(self, mock_http_class, mock_get_config, runner):
        """``simulate run --params`` passes JSON params to the simulation."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"simulation_id": "sim-456", "status": "started"}

        from aitbc_cli.commands.simulate import simulate

        result = runner.invoke(
            simulate,
            ["run", "test-scenario", "--params", '{"key": "value"}'],
        )

        assert result.exit_code == 0, result.output
        _, kwargs = mock_client.post.call_args
        assert kwargs.get("json", {}).get("params") == {"key": "value"}

    @patch("aitbc_cli.commands.simulate.get_config")
    @patch("aitbc_cli.commands.simulate.AITBCHTTPClient")
    def test_simulate_status_command(self, mock_http_class, mock_get_config, runner):
        """``simulate status`` fetches simulation status from coordinator-api."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"simulation_id": "sim-123", "status": "running"}

        from aitbc_cli.commands.simulate import simulate

        result = runner.invoke(simulate, ["status", "sim-123"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "sim-123" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.simulate.get_config")
    @patch("aitbc_cli.commands.simulate.AITBCHTTPClient")
    def test_simulate_result_command(self, mock_http_class, mock_get_config, runner):
        """``simulate result`` fetches simulation results from coordinator-api."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"simulation_id": "sim-123", "results": []}

        from aitbc_cli.commands.simulate import simulate

        result = runner.invoke(simulate, ["result", "sim-123"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "sim-123" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.simulate.get_config")
    @patch("aitbc_cli.commands.simulate.AITBCHTTPClient")
    def test_simulate_run_network_error(self, mock_http_class, mock_get_config, runner):
        """``simulate run`` aborts on NetworkError."""
        from aitbc_cli.commands.simulate import simulate
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(simulate, ["run", "test-scenario"])

        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
