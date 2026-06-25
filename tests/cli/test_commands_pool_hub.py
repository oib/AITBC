"""
Pool Hub Commands Tests
Tests for pool_hub CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestPoolHubCommands:
    """Test pool_hub command group"""

    def test_pool_hub_group_exists(self):
        """Test that pool_hub command group exists"""
        from aitbc_cli.commands.pool_hub import pool_hub

        assert pool_hub is not None
        assert hasattr(pool_hub, "name")

    def test_pool_hub_group_name(self):
        """Test pool_hub group name"""
        from aitbc_cli.commands.pool_hub import pool_hub

        assert pool_hub.name == "pool-hub"

    def test_pool_hub_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the pool_hub group."""
        from aitbc_cli.commands.pool_hub import pool_hub

        assert "status" in pool_hub.commands

    def test_pool_hub_group_has_sla_subcommand(self):
        """The ``sla`` subcommand is registered on the pool_hub group."""
        from aitbc_cli.commands.pool_hub import pool_hub

        assert "sla" in pool_hub.commands

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_status_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``pool-hub status`` returns pool hub status from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"pools": 5, "active_pools": 3}

        from aitbc_cli.commands.pool_hub import pool_hub

        result = runner.invoke(pool_hub, ["status"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/pool_hub/status" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_status_falls_back_on_network_error(self, mock_http_class, runner):
        """``pool-hub status`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.pool_hub import pool_hub
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(pool_hub, ["status"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_sla_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``pool-hub sla`` returns SLA data from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"sla_compliance": 99.5, "pool_id": "default"}

        from aitbc_cli.commands.pool_hub import pool_hub

        result = runner.invoke(pool_hub, ["sla"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/pool_hub/sla" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_sla_with_pool_id(self, mock_http_class, runner, mock_blockchain_rpc):
        """``pool-hub sla --pool-id`` forwards the pool_id param."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"sla_compliance": 99.5, "pool_id": "my-pool"}

        from aitbc_cli.commands.pool_hub import pool_hub

        result = runner.invoke(pool_hub, ["sla", "--pool-id", "my-pool"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        _, kwargs = mock_client.get.call_args
        assert kwargs.get("params", {}).get("pool_id") == "my-pool"

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_sla_falls_back_on_network_error(self, mock_http_class, runner):
        """``pool-hub sla`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.pool_hub import pool_hub
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(pool_hub, ["sla"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
