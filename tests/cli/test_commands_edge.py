"""
Edge Commands Tests
Tests for edge CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestEdgeCommands:
    """Test edge command group"""

    def test_edge_group_exists(self):
        """Test that edge command group exists"""
        from aitbc_cli.commands.edge import edge

        assert edge is not None
        assert hasattr(edge, "name")

    def test_edge_group_name(self):
        """Test edge group name"""
        from aitbc_cli.commands.edge import edge

        assert edge.name == "edge"

    def test_edge_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the edge group."""
        from aitbc_cli.commands.edge import edge

        assert "status" in edge.commands

    def test_edge_group_has_balance_subcommand(self):
        """The ``balance`` subcommand is registered on the edge group."""
        from aitbc_cli.commands.edge import edge

        assert "balance" in edge.commands

    def test_edge_group_has_transfer_subcommand(self):
        """The ``transfer`` subcommand is registered on the edge group."""
        from aitbc_cli.commands.edge import edge

        assert "transfer" in edge.commands

    @patch("aitbc_cli.commands.edge.AITBCHTTPClient")
    @patch("aitbc_cli.commands.edge.get_config")
    def test_edge_status_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``edge status`` returns edge status from the mocked coordinator API."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"status": "online", "gpus": 4, "load": 0.65}

        from aitbc_cli.commands.edge import edge

        result = runner.invoke(edge, ["status"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        called_path = mock_client.get.call_args[0][0]
        assert "/edge-gpu/metrics" in called_path

    @patch("aitbc_cli.commands.edge.AITBCHTTPClient")
    @patch("aitbc_cli.commands.edge.get_config")
    def test_edge_balance_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``edge balance`` returns edge wallet balance from the mocked coordinator API."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"address": "0xedge123", "balance": 50000}

        from aitbc_cli.commands.edge import edge

        result = runner.invoke(edge, ["balance"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        called_path = mock_client.get.call_args[0][0]
        assert "/edge-gpu/balance" in called_path

    @patch("aitbc_cli.commands.edge.AITBCHTTPClient")
    @patch("aitbc_cli.commands.edge.get_config")
    def test_edge_transfer_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``edge transfer`` submits a transfer via the mocked coordinator API."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"tx_hash": "0xtransfer123", "status": "submitted"}

        from aitbc_cli.commands.edge import edge

        result = runner.invoke(edge, ["transfer", "ait1qrecipient0000000000000000000000000", "100.5"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        called_path = mock_client.post.call_args[0][0]
        assert "/edge-gpu/transfer" in called_path

    @patch("aitbc_cli.commands.edge.AITBCHTTPClient")
    @patch("aitbc_cli.commands.edge.get_config")
    def test_edge_status_network_error_handled(self, mock_get_config, mock_http_class, runner, mock_config):
        """``edge status`` handles NetworkError gracefully (exit 0)."""
        from aitbc_cli.commands.edge import edge
        from aitbc_cli.utils.http_client import NetworkError

        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(edge, ["status"])

        # NetworkError is caught and reported via error(), exit code stays 0.
        assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
