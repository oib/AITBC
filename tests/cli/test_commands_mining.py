"""
Mining Commands Tests
Tests for mining CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestMiningCommands:
    """Test mining command group"""

    def test_mining_group_exists(self):
        """Test that mining command group exists"""
        from aitbc_cli.commands.mining import mining

        assert mining is not None
        assert hasattr(mining, "name")

    def test_mining_group_name(self):
        """Test mining group name"""
        from aitbc_cli.commands.mining import mining

        assert mining.name == "mining"

    def test_mining_group_has_start_subcommand(self):
        """The ``start`` subcommand is registered on the mining group."""
        from aitbc_cli.commands.mining import mining

        assert "start" in mining.commands

    def test_mining_group_has_stop_subcommand(self):
        """The ``stop`` subcommand is registered on the mining group."""
        from aitbc_cli.commands.mining import mining

        assert "stop" in mining.commands

    def test_mining_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the mining group."""
        from aitbc_cli.commands.mining import mining

        assert "status" in mining.commands

    def test_mining_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the mining group."""
        from aitbc_cli.commands.mining import mining

        assert "list" in mining.commands

    @patch("aitbc_cli.commands.mining.AITBCHTTPClient")
    def test_mining_stop_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``mining stop`` stops mining via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"status": "stopped"}

        from aitbc_cli.commands.mining import mining

        result = runner.invoke(mining, ["stop"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/rpc/mining/stop" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.commands.mining.AITBCHTTPClient")
    def test_mining_status_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``mining status`` returns mining status from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"enabled": True, "threads": 4, "hash_rate": 1000}

        from aitbc_cli.commands.mining import mining

        result = runner.invoke(mining, ["status"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/mining/status" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.mining.AITBCHTTPClient")
    def test_mining_list_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``mining list`` lists active miners from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"miners": [{"address": "ait1qtest", "threads": 2}]}

        from aitbc_cli.commands.mining import mining

        result = runner.invoke(mining, ["list"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/mining/miners" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.mining.AITBCHTTPClient")
    def test_mining_start_command_with_wallet(self, mock_http_class, runner, mock_blockchain_rpc, tmp_path):
        """``mining start`` starts mining with a wallet file."""
        import json

        # Create a temporary wallet file
        wallet_dir = tmp_path / "wallets"
        wallet_dir.mkdir()
        wallet_file = wallet_dir / "testwallet.json"
        wallet_file.write_text(json.dumps({"address": "ait1qtestaddress0000000000000000000000000"}))

        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"status": "started"}

        from aitbc_cli.commands.mining import mining

        with patch("aitbc_cli.commands.mining.DEFAULT_KEYSTORE_DIR", wallet_dir):
            result = runner.invoke(mining, ["start", "testwallet", "--threads", "2"])

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/rpc/mining/start" in mock_client.post.call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
