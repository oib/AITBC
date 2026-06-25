"""
Transactions Commands Tests
Tests for transactions CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestTransactionsCommands:
    """Test transactions command group"""

    def test_transactions_group_exists(self):
        """Test that transactions command group exists"""
        from aitbc_cli.commands.transactions import transactions

        assert transactions is not None
        assert hasattr(transactions, "name")

    def test_transactions_group_name(self):
        """Test transactions group name"""
        from aitbc_cli.commands.transactions import transactions

        assert transactions.name == "transactions"

    def test_transactions_group_has_send_subcommand(self):
        """The ``send`` subcommand is registered on the transactions group."""
        from aitbc_cli.commands.transactions import transactions

        assert "send" in transactions.commands

    def test_transactions_group_has_batch_subcommand(self):
        """The ``batch`` subcommand is registered on the transactions group."""
        from aitbc_cli.commands.transactions import transactions

        assert "batch" in transactions.commands

    def test_transactions_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the transactions group."""
        from aitbc_cli.commands.transactions import transactions

        assert "status" in transactions.commands

    def test_transactions_group_has_pending_subcommand(self):
        """The ``pending`` subcommand is registered on the transactions group."""
        from aitbc_cli.commands.transactions import transactions

        assert "pending" in transactions.commands

    def test_transactions_group_has_estimate_fee_subcommand(self):
        """The ``estimate-fee`` subcommand is registered on the transactions group."""
        from aitbc_cli.commands.transactions import transactions

        assert "estimate-fee" in transactions.commands

    @patch("aitbc_cli.commands.transactions.AITBCHTTPClient")
    def test_transactions_status_command(self, mock_http_class, runner):
        """``transactions status`` fetches transaction status from RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {
            "tx_hash": "0xabc123",
            "status": "confirmed",
            "block_height": 12345,
        }

        from aitbc_cli.commands.transactions import transactions

        result = runner.invoke(transactions, ["status", "0xabc123"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "0xabc123" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.transactions.AITBCHTTPClient")
    def test_transactions_status_command_with_rpc_url(self, mock_http_class, runner):
        """``transactions status --rpc-url`` uses the custom RPC URL."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"tx_hash": "0xabc123", "status": "confirmed"}

        from aitbc_cli.commands.transactions import transactions

        result = runner.invoke(
            transactions,
            ["status", "0xabc123", "--rpc-url", "http://custom-node:8202"],
        )

        assert result.exit_code == 0, result.output
        assert mock_http_class.call_args.kwargs["base_url"] == "http://custom-node:8202"

    @patch("aitbc_cli.commands.transactions.AITBCHTTPClient")
    def test_transactions_status_network_error(self, mock_http_class, runner):
        """``transactions status`` handles NetworkError gracefully."""
        from aitbc_cli.commands.transactions import transactions
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(transactions, ["status", "0xabc123"])

        # NetworkError is caught and an error message is printed (exit 0).
        assert result.exit_code == 0, result.output
        assert "Error" in result.output

    @patch("aitbc_cli.commands.transactions.AITBCHTTPClient")
    def test_transactions_pending_command(self, mock_http_class, runner):
        """``transactions pending`` fetches pending transactions from RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {
            "transactions": [
                {"hash": "0xtx1", "type": "TRANSFER", "amount": 100, "from": "ait1qsender"},
            ],
        }

        from aitbc_cli.commands.transactions import transactions

        result = runner.invoke(transactions, ["pending"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/pending" in mock_client.get.call_args[0][0]
        assert "0xtx1" in result.output

    @patch("aitbc_cli.commands.transactions.AITBCHTTPClient")
    def test_transactions_pending_empty(self, mock_http_class, runner):
        """``transactions pending`` handles empty pending list."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"transactions": []}

        from aitbc_cli.commands.transactions import transactions

        result = runner.invoke(transactions, ["pending"])

        assert result.exit_code == 0, result.output
        assert "Pending transactions: 0" in result.output

    @patch("aitbc_cli.commands.transactions.AITBCHTTPClient")
    def test_transactions_estimate_fee_command(self, mock_http_class, runner):
        """``transactions estimate-fee`` estimates the transaction fee."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"estimated_fee": 50.0}

        from aitbc_cli.commands.transactions import transactions

        result = runner.invoke(
            transactions,
            [
                "estimate-fee",
                "--from", "test-wallet",
                "--to", "ait1qtestaddress0000000000000000000000000",
                "--amount", "100",
            ],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/rpc/estimateFee" in mock_client.post.call_args[0][0]

    @patch("aitbc_cli.commands.transactions.AITBCHTTPClient")
    def test_transactions_estimate_fee_network_error_default(self, mock_http_class, runner):
        """``transactions estimate-fee`` falls back to default on NetworkError."""
        from aitbc_cli.commands.transactions import transactions
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(
            transactions,
            [
                "estimate-fee",
                "--from", "test-wallet",
                "--to", "ait1qtestaddress0000000000000000000000000",
                "--amount", "100",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "36.0" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
