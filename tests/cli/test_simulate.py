"""Tests for simulate CLI commands"""

from unittest.mock import Mock, patch

import pytest
from aitbc_cli.commands.simulate import simulate
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://test:8000"
    config.api_key = "test_api_key"
    return config


class TestSimulateCommands:
    """Test simulate command group"""

    @pytest.fixture(autouse=True)
    def mock_http(self):
        """Mock AITBCHTTPClient for coordinator API calls"""
        with patch("aitbc_cli.commands.simulate.AITBCHTTPClient") as mock_http_class:
            mock_instance = Mock()
            mock_http_class.return_value = mock_instance
            mock_instance.post.return_value = {"simulation_id": "sim_123", "status": "running", "scenario": "test_scenario"}
            mock_instance.get.return_value = {
                "simulation_id": "sim_123",
                "status": "completed",
                "results": {"total_transactions": 1000},
            }
            yield mock_http_class

    def test_blockchain_command(self, runner, mock_config):
        """Test blockchain simulation command"""
        result = runner.invoke(
            simulate,
            ["blockchain", "--blocks", "2", "--transactions", "5", "--delay", "0"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        assert "Simulating blockchain" in result.output
        assert "Block 1" in result.output or "Block 2" in result.output

    def test_wallets_command(self, runner, mock_config):
        """Test wallet simulation command"""
        result = runner.invoke(
            simulate,
            ["wallets", "--wallets", "2", "--balance", "100.0", "--transactions", "3"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        assert "Simulating 2 wallets" in result.output
        assert "Created wallet sim_wallet_1" in result.output
        assert "Final Wallet Balances" in result.output

    def test_price_command(self, runner, mock_config):
        """Test price simulation command"""
        result = runner.invoke(
            simulate,
            ["price", "--price", "50.0", "--volatility", "0.1", "--timesteps", "5", "--delay", "0"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        assert "Simulating AIT price" in result.output
        assert "Price Statistics" in result.output

    def test_network_command(self, runner, mock_config):
        """Test network simulation command"""
        result = runner.invoke(
            simulate,
            ["network", "--nodes", "3", "--network-delay", "0", "--failure-rate", "0.0"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        assert "Simulating network" in result.output
        assert "Network Topology" in result.output
        assert "Final Network Status" in result.output

    def test_ai_jobs_command(self, runner, mock_config):
        """Test AI jobs simulation command"""
        with patch("aitbc_cli.commands.simulate.time.sleep"):
            result = runner.invoke(
                simulate,
                ["ai-jobs", "--jobs", "2", "--models", "text-generation", "--duration-range", "1-1"],
                obj={"config": mock_config, "output": "json"},
            )

        assert result.exit_code == 0
        assert "Simulating 2 AI jobs" in result.output
        assert "Job Statistics" in result.output

    def test_run_scenario(self, runner, mock_config, mock_http):
        """Test running a simulation scenario via coordinator API"""
        result = runner.invoke(
            simulate, ["run", "test_scenario", "--params", '{"nodes": 5}'], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        mock_http.return_value.post.assert_called_once()
        call_args = mock_http.return_value.post.call_args
        assert "/simulate/run" in call_args[0][0]

    def test_status_command(self, runner, mock_config, mock_http):
        """Test simulation status command"""
        result = runner.invoke(simulate, ["status", "sim_123"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        mock_http.return_value.get.assert_called_once()
        call_args = mock_http.return_value.get.call_args
        assert "/simulate/sim_123/status" in call_args[0][0]

    def test_result_command(self, runner, mock_config, mock_http):
        """Test simulation result command"""
        result = runner.invoke(simulate, ["result", "sim_123"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        mock_http.return_value.get.assert_called_once()
        call_args = mock_http.return_value.get.call_args
        assert "/simulate/sim_123/result" in call_args[0][0]

    def test_run_invalid_json_params(self, runner, mock_config):
        """Test run with invalid JSON params exits with error"""
        result = runner.invoke(
            simulate, ["run", "test_scenario", "--params", "not-valid-json"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code != 0
        assert "Invalid JSON" in result.output or "Error" in result.output
