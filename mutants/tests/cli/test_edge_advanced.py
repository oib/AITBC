"""Integration tests for edge advanced CLI commands

These tests require edge-api running and validate advanced edge operations
including island leave/bridge, GPU operations, database operations, serve operations, and metrics.
"""

import json
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest
from aitbc.network.http_client import AITBCHTTPClient
from aitbc_cli.commands.edge import edge
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
    """Mock HTTP client for edge-api"""
    client = MagicMock(spec=AITBCHTTPClient)
    return client


class TestEdgeAdvancedCommands:
    """Integration tests for edge advanced commands with edge-api"""

    @pytest.fixture
    def edge_available(self):
        """Skip test if edge-api is not running"""
        try:
            response = httpx.get("http://127.0.0.1:8200/health", timeout=2)
            if response.status_code == 200:
                return True
        except Exception:
            pytest.skip("edge-api not running at http://127.0.0.1:8200")

    # Island advanced operations
    def test_edge_island_leave(self, runner, mock_config, edge_available):
        """Test leaving an island"""
        result = runner.invoke(
            edge, ["island", "leave", "--island-id", "test_island_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "island_id" in data or "status" in data

    def test_edge_island_bridge(self, runner, mock_config, edge_available):
        """Test bridging between islands"""
        result = runner.invoke(
            edge,
            ["island", "bridge", "--source", "island_a", "--target", "island_b"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "bridge_id" in data or "status" in data

    # GPU operations
    def test_edge_gpu_list_gpus(self, runner, mock_config, edge_available):
        """Test listing GPUs"""
        result = runner.invoke(edge, ["gpu", "list-gpus"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "gpus" in data or isinstance(data, list)

    def test_edge_gpu_get_gpu(self, runner, mock_config, edge_available):
        """Test getting specific GPU info"""
        result = runner.invoke(edge, ["gpu", "get-gpu", "--gpu-id", "gpu_123"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "gpu_id" in data or "status" in data

    def test_edge_gpu_remove_gpu(self, runner, mock_config, edge_available):
        """Test removing a GPU"""
        result = runner.invoke(
            edge, ["gpu", "remove-gpu", "--gpu-id", "gpu_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "gpu_id" in data or "status" in data

    def test_edge_gpu_scan_gpus(self, runner, mock_config, edge_available):
        """Test scanning for available GPUs"""
        result = runner.invoke(edge, ["gpu", "scan-gpus"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "gpus" in data or "scan_results" in data

    def test_edge_gpu_gpu_metrics(self, runner, mock_config, edge_available):
        """Test getting GPU metrics"""
        result = runner.invoke(
            edge, ["gpu", "gpu-metrics", "--gpu-id", "gpu_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "metrics" in data or "gpu_id" in data

    # Database operations
    def test_edge_database_init_db(self, runner, mock_config, edge_available):
        """Test initializing a database"""
        result = runner.invoke(
            edge, ["database", "init_db", "--db-name", "test_db"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "db_id" in data or "status" in data

    def test_edge_database_list_dbs(self, runner, mock_config, edge_available):
        """Test listing databases"""
        result = runner.invoke(edge, ["database", "list-dbs"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "databases" in data or isinstance(data, list)

    def test_edge_database_get_db(self, runner, mock_config, edge_available):
        """Test getting database info"""
        result = runner.invoke(
            edge, ["database", "get-db", "--db-id", "db_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "db_id" in data or "status" in data

    def test_edge_database_delete_db(self, runner, mock_config, edge_available):
        """Test deleting a database"""
        result = runner.invoke(
            edge, ["database", "delete-db", "--db-id", "db_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "db_id" in data or "status" in data

    def test_edge_database_sync_db(self, runner, mock_config, edge_available):
        """Test syncing a database"""
        result = runner.invoke(
            edge, ["database", "sync-db", "--db-id", "db_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "db_id" in data or "sync_status" in data

    # Serve operations
    def test_edge_serve_submit_request(self, runner, mock_config, edge_available):
        """Test submitting a serve request"""
        result = runner.invoke(
            edge,
            ["serve", "submit_request", "--request-type", "compute", "--parameters", '{"gpu_count": 2}'],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "request_id" in data or "status" in data

    def test_edge_serve_list_requests(self, runner, mock_config, edge_available):
        """Test listing serve requests"""
        result = runner.invoke(edge, ["serve", "list-requests"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "requests" in data or isinstance(data, list)

    def test_edge_serve_get_request(self, runner, mock_config, edge_available):
        """Test getting serve request info"""
        result = runner.invoke(
            edge, ["serve", "get-request", "--request-id", "req_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "request_id" in data or "status" in data

    def test_edge_serve_cancel_request(self, runner, mock_config, edge_available):
        """Test cancelling a serve request"""
        result = runner.invoke(
            edge, ["serve", "cancel-request", "--request-id", "req_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "request_id" in data or "status" in data

    def test_edge_serve_get_result(self, runner, mock_config, edge_available):
        """Test getting serve request result"""
        result = runner.invoke(
            edge, ["serve", "get-result", "--request-id", "req_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "result" in data or "request_id" in data

    # Metrics operations
    def test_edge_metrics_record(self, runner, mock_config, edge_available):
        """Test recording a metric"""
        result = runner.invoke(
            edge,
            ["metrics", "record", "--metric-name", "test_metric", "--value", "100"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "metric_id" in data or "status" in data

    def test_edge_metrics_list_metrics(self, runner, mock_config, edge_available):
        """Test listing metrics"""
        result = runner.invoke(edge, ["metrics", "list-metrics"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "metrics" in data or isinstance(data, list)

    def test_edge_metrics_get_metric(self, runner, mock_config, edge_available):
        """Test getting a specific metric"""
        result = runner.invoke(
            edge, ["metrics", "get-metric", "--metric-id", "metric_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "metric_id" in data or "value" in data

    def test_edge_metrics_delete_metric(self, runner, mock_config, edge_available):
        """Test deleting a metric"""
        result = runner.invoke(
            edge, ["metrics", "delete-metric", "--metric-id", "metric_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "metric_id" in data or "status" in data

    # Error handling tests
    def test_edge_island_leave_nonexistent(self, runner, mock_config):
        """Test leaving non-existent island"""
        result = runner.invoke(
            edge, ["island", "leave", "--island-id", "nonexistent_island"], obj={"config": mock_config, "output": "json"}
        )

        # Should handle gracefully
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_edge_gpu_get_nonexistent(self, runner, mock_config):
        """Test getting non-existent GPU"""
        result = runner.invoke(
            edge, ["gpu", "get-gpu", "--gpu-id", "nonexistent_gpu"], obj={"config": mock_config, "output": "json"}
        )

        # Should handle gracefully
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_edge_api_error_handling(self, runner, mock_config):
        """Test edge command handles edge-api errors gracefully"""
        # Use invalid edge URL to trigger error
        mock_config.coordinator_url = "http://invalid:9999"

        result = runner.invoke(edge, ["gpu", "list-gpus"], obj={"config": mock_config, "output": "json"})

        # Should either fail gracefully or skip with appropriate message
        assert result.exit_code != 0 or "error" in result.output.lower() or "unavailable" in result.output.lower()

    # Output format tests
    def test_edge_gpu_list_table_format(self, runner, mock_config, edge_available):
        """Test GPU list in table format"""
        result = runner.invoke(edge, ["gpu", "list-gpus"], obj={"config": mock_config, "output": "table"})

        assert result.exit_code == 0
        assert "GPU" in result.output or "gpus" in result.output.lower()

    def test_edge_database_list_table_format(self, runner, mock_config, edge_available):
        """Test database list in table format"""
        result = runner.invoke(edge, ["database", "list-dbs"], obj={"config": mock_config, "output": "table"})

        assert result.exit_code == 0
        assert "Database" in result.output or "databases" in result.output.lower()

    @patch("aitbc_cli.commands.edge.get_config")
    @patch("aitbc_cli.commands.edge.AITBCHTTPClient")
    def test_edge_gpu_list_via_edge_api(self, mock_http_client_class, mock_get_config, runner):
        """Test GPU listing via edge-api"""
        # Setup mocks
        mock_config = Mock()
        mock_config.coordinator_url = "http://127.0.0.1:18000"
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_http_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "gpus": [{"id": "gpu_1", "type": "NVIDIA", "memory": 16}, {"id": "gpu_2", "type": "NVIDIA", "memory": 32}]
        }

        result = runner.invoke(edge, ["gpu", "list-gpus"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
