"""
Marketplace Cmd Commands Tests
Tests for marketplace_cmd CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestMarketplaceCmdCommands:
    """Test marketplace command group"""

    def test_marketplace_group_exists(self):
        """Test that marketplace command group exists"""
        from aitbc_cli.commands.marketplace_cmd import marketplace

        assert marketplace is not None
        assert hasattr(marketplace, "name")

    def test_marketplace_group_name(self):
        """Test marketplace group name"""
        from aitbc_cli.commands.marketplace_cmd import marketplace

        assert marketplace.name == "marketplace"

    def test_marketplace_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the marketplace group."""
        from aitbc_cli.commands.marketplace_cmd import marketplace

        assert "list" in marketplace.commands

    def test_marketplace_group_has_buy_subcommand(self):
        """The ``buy`` subcommand is registered on the marketplace group."""
        from aitbc_cli.commands.marketplace_cmd import marketplace

        assert "buy" in marketplace.commands

    def test_marketplace_group_has_search_subcommand(self):
        """The ``search`` subcommand is registered on the marketplace group."""
        from aitbc_cli.commands.marketplace_cmd import marketplace

        assert "search" in marketplace.commands

    def test_marketplace_group_has_overview_subcommand(self):
        """The ``overview`` subcommand is registered on the marketplace group."""
        from aitbc_cli.commands.marketplace_cmd import marketplace

        assert "overview" in marketplace.commands

    def test_marketplace_group_has_economy_subcommand(self):
        """The ``economy`` subcommand is registered on the marketplace group."""
        from aitbc_cli.commands.marketplace_cmd import marketplace

        assert "economy" in marketplace.commands

    @patch("aitbc_cli.utils.chain_id.get_chain_id")
    @patch("aitbc_cli.commands.marketplace_cmd.load_multichain_config")
    @patch("aitbc_cli.commands.marketplace_cmd.get_config")
    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_marketplace_list_command(
        self,
        mock_http_class,
        mock_get_config,
        mock_load_config,
        mock_get_chain_id,
        runner,
        mock_blockchain_rpc,
    ):
        """``marketplace list`` creates a listing via the mocked RPC."""
        mock_get_chain_id.return_value = "test-chain"
        mock_load_config.return_value = MagicMock(blockchain_rpc_url="http://localhost:8202")
        mock_get_config.return_value = MagicMock(marketplace_service_url="http://localhost:8102")
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"listing_id": "test123"}

        from aitbc_cli.commands.marketplace_cmd import marketplace

        result = runner.invoke(
            marketplace,
            [
                "list",
                "test-chain",
                "Test Chain",
                "topic",
                "Test Description",
                "seller1",
                "100",
            ],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/v1/transactions" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.utils.chain_id.get_chain_id")
    @patch("aitbc_cli.commands.marketplace_cmd.load_multichain_config")
    @patch("aitbc_cli.commands.marketplace_cmd.get_config")
    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_marketplace_list_with_currency(
        self,
        mock_http_class,
        mock_get_config,
        mock_load_config,
        mock_get_chain_id,
        runner,
        mock_blockchain_rpc,
    ):
        """``marketplace list --currency`` forwards the currency param."""
        mock_get_chain_id.return_value = "test-chain"
        mock_load_config.return_value = MagicMock(blockchain_rpc_url="http://localhost:8202")
        mock_get_config.return_value = MagicMock(marketplace_service_url="http://localhost:8102")
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"listing_id": "test456"}

        from aitbc_cli.commands.marketplace_cmd import marketplace

        result = runner.invoke(
            marketplace,
            [
                "list",
                "test-chain",
                "Test Chain",
                "topic",
                "Test Description",
                "seller1",
                "100",
                "--currency",
                "USDC",
            ],
        )

        assert result.exit_code == 0, result.output
        _, kwargs = mock_client.post.call_args
        assert kwargs["json"]["currency"] == "USDC"

    @patch("aitbc_cli.utils.chain_id.get_chain_id")
    @patch("aitbc_cli.commands.marketplace_cmd.load_multichain_config")
    @patch("aitbc_cli.commands.marketplace_cmd.get_config")
    @patch("aitbc_cli.utils.http_client.AITBCHTTPClient")
    def test_marketplace_list_invalid_chain_type(
        self,
        mock_http_class,
        mock_get_config,
        mock_load_config,
        mock_get_chain_id,
        runner,
        mock_blockchain_rpc,
    ):
        """``marketplace list`` with an invalid chain type aborts."""
        mock_get_chain_id.return_value = "test-chain"
        mock_load_config.return_value = MagicMock(blockchain_rpc_url="http://localhost:8202")
        mock_get_config.return_value = MagicMock(marketplace_service_url="http://localhost:8102")

        from aitbc_cli.commands.marketplace_cmd import marketplace

        result = runner.invoke(
            marketplace,
            [
                "list",
                "test-chain",
                "Test Chain",
                "invalid_type",
                "Test Description",
                "seller1",
                "100",
            ],
        )

        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
