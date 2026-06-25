"""
Bridge Commands Tests
Tests for bridge CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestBridgeCommands:
    """Test bridge command group"""

    def test_bridge_group_exists(self):
        """Test that bridge command group exists"""
        from aitbc_cli.commands.bridge import bridge

        assert bridge is not None
        assert hasattr(bridge, "name")

    def test_bridge_group_name(self):
        """Test bridge group name"""
        from aitbc_cli.commands.bridge import bridge

        assert bridge.name == "bridge"

    def test_bridge_group_has_start_subcommand(self):
        """The ``start`` subcommand is registered on the bridge group."""
        from aitbc_cli.commands.bridge import bridge

        assert "start" in bridge.commands

    def test_bridge_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the bridge group."""
        from aitbc_cli.commands.bridge import bridge

        assert "status" in bridge.commands

    def test_bridge_group_has_stop_subcommand(self):
        """The ``stop`` subcommand is registered on the bridge group."""
        from aitbc_cli.commands.bridge import bridge

        assert "stop" in bridge.commands

    @patch("aitbc_cli.commands.bridge.AITBCHTTPClient")
    def test_bridge_start_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``bridge start`` posts to the bridge/start RPC endpoint."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = mock_blockchain_rpc.responses["/rpc/bridge/start"]

        from aitbc_cli.commands.bridge import bridge

        result = runner.invoke(bridge, ["start"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/rpc/bridge/start" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.commands.bridge.AITBCHTTPClient")
    def test_bridge_status_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``bridge status`` fetches the bridge status RPC endpoint."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = mock_blockchain_rpc.responses["/rpc/bridge/status"]

        from aitbc_cli.commands.bridge import bridge

        result = runner.invoke(bridge, ["status"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/bridge/status" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.bridge.AITBCHTTPClient")
    def test_bridge_stop_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``bridge stop`` posts to the bridge/stop RPC endpoint."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = mock_blockchain_rpc.responses["/rpc/bridge/stop"]

        from aitbc_cli.commands.bridge import bridge

        result = runner.invoke(bridge, ["stop"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/rpc/bridge/stop" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.commands.bridge.AITBCHTTPClient")
    def test_bridge_start_falls_back_on_network_error(self, mock_http_class, runner):
        """``bridge start`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.bridge import bridge
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(bridge, ["start"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    @patch("aitbc_cli.commands.bridge.AITBCHTTPClient")
    def test_bridge_start_with_custom_rpc_url(self, mock_http_class, runner):
        """``bridge start --rpc-url`` forwards the custom URL to the client."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"bridge_status": "started"}

        from aitbc_cli.commands.bridge import bridge

        result = runner.invoke(bridge, ["start", "--rpc-url", "http://custom-node:9000"])

        assert result.exit_code == 0, result.output
        # AITBCHTTPClient should have been constructed with the custom URL.
        assert mock_http_class.call_args.kwargs["base_url"] == "http://custom-node:9000"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
