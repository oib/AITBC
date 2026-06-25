"""
Network Commands Tests
Tests for network CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestNetworkCommands:
    """Test network command group"""

    def test_network_group_exists(self):
        """Test that network command group exists"""
        from aitbc_cli.commands.network import network

        assert network is not None
        assert hasattr(network, "name")

    def test_network_group_name(self):
        """Test network group name"""
        from aitbc_cli.commands.network import network

        assert network.name == "network"

    def test_network_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the network group."""
        from aitbc_cli.commands.network import network

        assert "status" in network.commands

    def test_network_group_has_peers_subcommand(self):
        """The ``peers`` subcommand is registered on the network group."""
        from aitbc_cli.commands.network import network

        assert "peers" in network.commands

    def test_network_group_has_force_sync_subcommand(self):
        """The ``force-sync`` subcommand is registered on the network group."""
        from aitbc_cli.commands.network import network

        assert "force-sync" in network.commands

    def test_network_group_has_subscribe_subcommand(self):
        """The ``subscribe`` subcommand is registered on the network group."""
        from aitbc_cli.commands.network import network

        assert "subscribe" in network.commands

    def test_network_group_has_subscribers_subcommand(self):
        """The ``subscribers`` subcommand is registered on the network group."""
        from aitbc_cli.commands.network import network

        assert "subscribers" in network.commands

    @patch("aitbc_cli.commands.network.AITBCHTTPClient")
    def test_network_status_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``network status`` returns network status from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"connected_peers": 5, "block_height": 12345}

        from aitbc_cli.commands.network import network

        result = runner.invoke(network, ["status"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/network-info" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.network.AITBCHTTPClient")
    def test_network_status_falls_back_on_network_error(self, mock_http_class, runner):
        """``network status`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.network import network
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(network, ["status"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    @patch("aitbc_cli.commands.network.AITBCHTTPClient")
    def test_network_peers_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``network peers`` lists peers from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"peers": ["peer1", "peer2"]}

        from aitbc_cli.commands.network import network

        result = runner.invoke(network, ["peers"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/network-info" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.network.AITBCHTTPClient")
    def test_network_peers_falls_back_on_network_error(self, mock_http_class, runner):
        """``network peers`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.network import network
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(network, ["peers"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    @patch("aitbc_cli.commands.network.AITBCHTTPClient")
    def test_network_force_sync_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``network force-sync`` triggers sync via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"status": "syncing"}

        from aitbc_cli.commands.network import network

        result = runner.invoke(network, ["force-sync"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/force-sync" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.commands.network.AITBCHTTPClient")
    def test_network_force_sync_aborts_on_network_error(self, mock_http_class, runner):
        """``network force-sync`` aborts on NetworkError (no fallback)."""
        from aitbc_cli.commands.network import network
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(network, ["force-sync"])

        assert result.exit_code != 0

    @patch("aitbc_cli.commands.network.AITBCHTTPClient")
    def test_network_subscribers_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``network subscribers`` lists subscribers from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"subscribers": []}

        from aitbc_cli.commands.network import network

        result = runner.invoke(network, ["subscribers"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/subscription/subscribers" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.network.AITBCHTTPClient")
    def test_network_subscribe_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``network subscribe`` registers a subscriber via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"status": "registered", "lease_duration": 300}

        from aitbc_cli.commands.network import network

        result = runner.invoke(
            network,
            ["subscribe", "--node-id", "test-node", "--chain-id", "test-chain"],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        assert "/rpc/subscribe" in args[0]
        assert kwargs["json"]["node_id"] == "test-node"
        assert kwargs["json"]["chain_id"] == "test-chain"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
