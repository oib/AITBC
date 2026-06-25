"""
Exchange Island Commands Tests
Tests for exchange_island CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestExchangeIslandCommands:
    """Test exchange_island command group"""

    def test_exchange_island_group_exists(self):
        """Test that exchange_island command group exists"""
        from aitbc_cli.commands.exchange_island import exchange_island

        assert exchange_island is not None
        assert hasattr(exchange_island, "name")

    def test_exchange_island_group_name(self):
        """Test exchange_island group name"""
        from aitbc_cli.commands.exchange_island import exchange_island

        assert exchange_island.name == "exchange-island"

    def test_exchange_island_group_has_orderbook_subcommand(self):
        """The ``orderbook`` subcommand is registered on the exchange_island group."""
        from aitbc_cli.commands.exchange_island import exchange_island

        assert "orderbook" in exchange_island.commands

    def test_exchange_island_group_has_rates_subcommand(self):
        """The ``rates`` subcommand is registered on the exchange_island group."""
        from aitbc_cli.commands.exchange_island import exchange_island

        assert "rates" in exchange_island.commands

    def test_exchange_island_group_has_orders_subcommand(self):
        """The ``orders`` subcommand is registered on the exchange_island group."""
        from aitbc_cli.commands.exchange_island import exchange_island

        assert "orders" in exchange_island.commands

    @patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient")
    @patch("aitbc_cli.commands.exchange_island.get_island_id", return_value="island-test-123")
    @patch("aitbc_cli.commands.exchange_island.get_rpc_endpoint", return_value="http://localhost:8202")
    @patch("aitbc_cli.commands.exchange_island.safe_load_credentials")
    def test_exchange_island_orderbook_command(
        self, mock_creds, mock_rpc, mock_island, mock_http_class, runner
    ):
        """``exchange-island orderbook`` displays the order book from the mocked RPC."""
        mock_creds.return_value = {"island_id": "island-test-123", "credentials": {"p2p_port": 8001}}
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = [
            {"order_id": "ord1", "side": "buy", "amount": 10.0, "max_price": 0.001, "user_id": "user1"},
            {"order_id": "ord2", "side": "sell", "amount": 5.0, "min_price": 0.002, "user_id": "user2"},
        ]

        from aitbc_cli.commands.exchange_island import exchange_island

        result = runner.invoke(exchange_island, ["orderbook", "AIT/BTC"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        called_path = mock_client.get.call_args[0][0]
        assert "/transactions" in called_path

    @patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient")
    @patch("aitbc_cli.commands.exchange_island.get_island_id", return_value="island-test-123")
    @patch("aitbc_cli.commands.exchange_island.get_rpc_endpoint", return_value="http://localhost:8202")
    @patch("aitbc_cli.commands.exchange_island.safe_load_credentials")
    def test_exchange_island_orderbook_empty(
        self, mock_creds, mock_rpc, mock_island, mock_http_class, runner
    ):
        """``exchange-island orderbook`` handles an empty order book gracefully."""
        mock_creds.return_value = {"island_id": "island-test-123", "credentials": {"p2p_port": 8001}}
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = []

        from aitbc_cli.commands.exchange_island import exchange_island

        result = runner.invoke(exchange_island, ["orderbook", "AIT/BTC"])

        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.commands.exchange_island.safe_load_credentials", return_value=None)
    def test_exchange_island_orderbook_no_credentials(self, mock_creds, runner):
        """``exchange-island orderbook`` exits gracefully when credentials are missing."""
        from aitbc_cli.commands.exchange_island import exchange_island

        result = runner.invoke(exchange_island, ["orderbook", "AIT/BTC"])

        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.commands.exchange_island.AITBCHTTPClient")
    @patch("aitbc_cli.commands.exchange_island.get_island_id", return_value="island-test-123")
    @patch("aitbc_cli.commands.exchange_island.get_rpc_endpoint", return_value="http://localhost:8202")
    @patch("aitbc_cli.commands.exchange_island.safe_load_credentials")
    def test_exchange_island_orders_command(
        self, mock_creds, mock_rpc, mock_island, mock_http_class, runner
    ):
        """``exchange-island orders`` lists exchange orders from the mocked RPC."""
        mock_creds.return_value = {"island_id": "island-test-123", "credentials": {"p2p_port": 8001}}
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = [
            {"order_id": "ord1", "side": "buy", "amount": 10.0, "max_price": 0.001, "pair": "AIT/BTC", "status": "open", "user_id": "user1"},
        ]

        from aitbc_cli.commands.exchange_island import exchange_island

        result = runner.invoke(exchange_island, ["orders"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
