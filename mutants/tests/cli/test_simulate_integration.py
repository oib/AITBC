"""Integration tests for simulate CLI commands

These tests require coordinator-api running and validate simulation operations
including blockchain, wallets, price, network, and ai-jobs simulations with actual service calls.
"""

import json
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest
from aitbc.network import AITBCHTTPClient
from aitbc_cli.commands.simulate import simulate
from aitbc_cli.utils.http_client import NetworkError
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://127.0.0.1:18000"
    config.api_key = "test_api_key"
    return config


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for coordinator-api"""
    client = MagicMock(spec=AITBCHTTPClient)
    return client


class TestSimulateCommandsIntegration:
    """Integration tests for simulate commands with coordinator-api"""

    @pytest.fixture
    def coordinator_available(self):
        """Skip test if coordinator-api is not running"""
        try:
            response = httpx.get("http://127.0.0.1:18000/health", timeout=2)
            if response.status_code == 200:
                return True
        except Exception:
            pytest.skip("coordinator-api not running at http://127.0.0.1:18000")

    def test_simulate_blockchain(self, runner, mock_config, coordinator_available):
        """Test blockchain simulation"""
        result = runner.invoke(
            simulate, ["blockchain", "--blocks", "10", "--transactions", "50"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "blocks" in data or "simulation_id" in data

    def test_simulate_wallets(self, runner, mock_config, coordinator_available):
        """Test wallet simulation"""
        result = runner.invoke(
            simulate, ["wallets", "--count", "5", "--balance", "1000"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "wallets" in data or "simulation_id" in data

    def test_simulate_price(self, runner, mock_config, coordinator_available):
        """Test price simulation"""
        result = runner.invoke(
            simulate, ["price", "--days", "30", "--volatility", "0.1"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "prices" in data or "simulation_id" in data

    def test_simulate_network(self, runner, mock_config, coordinator_available):
        """Test network simulation"""
        result = runner.invoke(
            simulate, ["network", "--nodes", "10", "--latency", "50"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "network" in data or "simulation_id" in data

    def test_simulate_ai_jobs(self, runner, mock_config, coordinator_available):
        """Test AI jobs simulation"""
        result = runner.invoke(
            simulate, ["ai-jobs", "--jobs", "20", "--duration", "300"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "jobs" in data or "simulation_id" in data

    def test_simulate_run(self, runner, mock_config, coordinator_available):
        """Test running a simulation"""
        result = runner.invoke(
            simulate, ["run", "--type", "blockchain", "--duration", "60"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "simulation_id" in data or "status" in data

    def test_simulate_status(self, runner, mock_config, coordinator_available):
        """Test getting simulation status"""
        # First run a simulation
        run_result = runner.invoke(simulate, ["run", "--type", "blockchain"], obj={"config": mock_config, "output": "json"})

        assert run_result.exit_code == 0
        run_data = json.loads(run_result.output)
        sim_id = run_data.get("simulation_id")

        if sim_id:
            # Get status
            status_result = runner.invoke(simulate, ["status", sim_id], obj={"config": mock_config, "output": "json"})

            assert status_result.exit_code == 0
            status_data = json.loads(status_result.output)
            assert "status" in status_data

    def test_simulate_result(self, runner, mock_config, coordinator_available):
        """Test getting simulation results"""
        # First run a simulation
        run_result = runner.invoke(simulate, ["run", "--type", "wallets"], obj={"config": mock_config, "output": "json"})

        assert run_result.exit_code == 0
        run_data = json.loads(run_result.output)
        sim_id = run_data.get("simulation_id")

        if sim_id:
            # Get results
            result_result = runner.invoke(simulate, ["result", sim_id], obj={"config": mock_config, "output": "json"})

            assert result_result.exit_code == 0
            result_data = json.loads(result_result.output)
            assert "results" in result_data or "data" in result_data

    def test_simulate_blockchain_with_params(self, runner, mock_config, coordinator_available):
        """Test blockchain simulation with custom parameters"""
        result = runner.invoke(
            simulate,
            ["blockchain", "--blocks", "100", "--transactions", "500", "--difficulty", "5"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "blocks" in data or "simulation_id" in data

    def test_simulate_wallets_with_distribution(self, runner, mock_config, coordinator_available):
        """Test wallet simulation with balance distribution"""
        result = runner.invoke(
            simulate,
            ["wallets", "--count", "10", "--distribution", "exponential"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "wallets" in data or "simulation_id" in data

    def test_simulate_price_with_trend(self, runner, mock_config, coordinator_available):
        """Test price simulation with trend"""
        result = runner.invoke(
            simulate,
            ["price", "--days", "90", "--trend", "bullish", "--volatility", "0.15"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "prices" in data or "simulation_id" in data

    def test_simulate_network_with_topology(self, runner, mock_config, coordinator_available):
        """Test network simulation with custom topology"""
        result = runner.invoke(
            simulate,
            ["network", "--nodes", "20", "--topology", "mesh", "--latency", "100"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "network" in data or "simulation_id" in data

    def test_simulate_ai_jobs_with_gpu(self, runner, mock_config, coordinator_available):
        """Test AI jobs simulation with GPU requirements"""
        result = runner.invoke(
            simulate,
            ["ai-jobs", "--jobs", "30", "--gpu-required", "--duration", "600"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "jobs" in data or "simulation_id" in data

    def test_simulate_run_async(self, runner, mock_config, coordinator_available):
        """Test running simulation in async mode"""
        result = runner.invoke(
            simulate,
            ["run", "--type", "network", "--async", "--duration", "120"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "simulation_id" in data
        assert data.get("status") in ["started", "running", "pending"]

    def test_simulate_status_nonexistent(self, runner, mock_config):
        """Test getting status of non-existent simulation"""
        result = runner.invoke(simulate, ["status", "sim_nonexistent_12345"], obj={"config": mock_config, "output": "json"})

        # Should handle gracefully
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_simulate_result_nonexistent(self, runner, mock_config):
        """Test getting results of non-existent simulation"""
        result = runner.invoke(simulate, ["result", "sim_nonexistent_12345"], obj={"config": mock_config, "output": "json"})

        # Should handle gracefully
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_simulate_multiple_concurrent(self, runner, mock_config, coordinator_available):
        """Test running multiple concurrent simulations"""
        sim_ids = []

        for _i in range(3):
            result = runner.invoke(
                simulate, ["run", "--type", "blockchain", "--async"], obj={"config": mock_config, "output": "json"}
            )

            assert result.exit_code == 0
            data = json.loads(result.output)
            sim_id = data.get("simulation_id")
            if sim_id:
                sim_ids.append(sim_id)

        # Verify we got multiple simulation IDs
        assert len(sim_ids) > 0

    @patch("aitbc_cli.commands.simulate.get_config")
    @patch("aitbc_cli.commands.simulate.AITBCHTTPClient")
    def test_simulate_api_error_handling(self, mock_http_client_class, mock_get_config, runner):
        """Test simulate command handles coordinator-api errors gracefully"""
        mock_config = Mock()
        mock_config.coordinator_url = "http://invalid:9999"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.post.side_effect = NetworkError("Connection refused")

        result = runner.invoke(simulate, ["run", "blockchain"], obj={"config": mock_config, "output": "json"})

        # Should fail gracefully with network error message
        assert result.exit_code != 0 or "error" in result.output.lower() or "network" in result.output.lower()

    @patch("aitbc_cli.commands.simulate.get_config")
    @patch("aitbc_cli.commands.simulate.AITBCHTTPClient")
    def test_simulate_blockchain_via_coordinator_api(self, mock_http_client_class, mock_get_config, runner):
        """Test blockchain simulation via coordinator-api"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.post.return_value = {"simulation_id": "sim_123", "status": "started", "blocks": 10}

        result = runner.invoke(simulate, ["blockchain", "--blocks", "10"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        # Verify API was called (if simulate command uses coordinator-api)

    def test_simulate_output_formats(self, runner, mock_config, coordinator_available):
        """Test simulation output in different formats"""
        # JSON format
        result_json = runner.invoke(simulate, ["blockchain", "--blocks", "5"], obj={"config": mock_config, "output": "json"})

        assert result_json.exit_code == 0
        json.loads(result_json.output)  # Should be valid JSON

        # Table format
        result_table = runner.invoke(simulate, ["blockchain", "--blocks", "5"], obj={"config": mock_config, "output": "table"})

        assert result_table.exit_code == 0
