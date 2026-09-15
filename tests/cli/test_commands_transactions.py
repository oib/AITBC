"""
Transactions Commands Tests
Tests for transactions CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest
from aitbc.utils import ait_to_units


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

        result = runner.invoke(transactions, ["status", "--tx-hash", "0xabc123"])

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
            ["status", "--tx-hash", "0xabc123", "--rpc-url", "http://custom-node:8202"],
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

        result = runner.invoke(transactions, ["status", "--tx-hash", "0xabc123"])

        # NetworkError is caught and an error message is printed (exit 0).
        assert result.exit_code == 0, result.output
        assert "Error" in result.output

    @patch("aitbc_cli.commands.transactions.AITBCHTTPClient")
    def test_transactions_pending_command(self, mock_http_class, runner):
        """``transactions pending`` fetches pending transactions from RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {
            "transactions": [
                {"hash": "0xtx1", "type": "TRANSFER", "amount": 100, "from": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1"},
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
                "--from",
                "test-wallet",
                "--to",
                "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C",
                "--amount",
                "100",
            ],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        assert "/rpc/estimateFee" in mock_client.post.call_args[0][0]
        # --amount is AIT; the node is asked in compute-units
        assert mock_client.post.call_args[1]["json"]["value"] == ait_to_units(100)
        # ...and the node's answer comes back in compute-units, so 50 units is not 50 AIT
        assert "0.00000139 AIT" in result.output

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
                "--from",
                "test-wallet",
                "--to",
                "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C",
                "--amount",
                "100",
            ],
        )

        assert result.exit_code == 0, result.output
        # the default fee is 0.01 AIT (360_000 compute-units)
        assert "0.01 AIT (default)" in result.output

    def _write_batch_file(self, tmp_path, entries):
        import json

        batch_file = tmp_path / "batch.json"
        batch_file.write_text(json.dumps(entries))
        return str(batch_file)

    @patch("aitbc_cli.commands.transactions._send_transaction_impl")
    def test_batch_rejects_duplicate_entries(self, mock_send, runner, tmp_path):
        """Identical batch entries are rejected, not reported as two successes."""
        from aitbc_cli.commands.transactions import transactions

        entry = {
            "from_wallet": "w1",
            "to_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C",
            "amount": 1.5,
            "fee": 0.001,
        }
        batch_file = self._write_batch_file(tmp_path, [entry, dict(entry)])
        mock_send.side_effect = ["0xhash1"]

        result = runner.invoke(transactions, ["batch", "--transactions-file", batch_file, "--password", "pw"])

        assert result.exit_code == 0, result.output
        # Only one submission reaches the chain; the duplicate is reported.
        assert mock_send.call_count == 1
        assert "Duplicate batch entry skipped" in result.output
        assert "1/2 successful" in result.output

    @patch("aitbc_cli.commands.transactions._send_transaction_impl")
    def test_batch_detects_duplicate_tx_hash(self, mock_send, runner, tmp_path):
        """If two distinct entries still produce the same tx hash, the second is not a success."""
        from aitbc_cli.commands.transactions import transactions

        entries = [
            {"from_wallet": "w1", "to_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C", "amount": 1.5},
            {"from_wallet": "w1", "to_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C", "amount": 2.5},
        ]
        batch_file = self._write_batch_file(tmp_path, entries)
        mock_send.side_effect = ["0xsamehash", "0xsamehash"]

        result = runner.invoke(transactions, ["batch", "--transactions-file", batch_file, "--password", "pw"])

        assert result.exit_code == 0, result.output
        assert mock_send.call_count == 2
        assert "duplicate hash" in result.output
        assert "1/2 successful" in result.output

    @patch("aitbc_cli.commands.transactions._send_transaction_impl")
    def test_batch_increments_nonce_offset_per_sender(self, mock_send, runner, tmp_path):
        """Same-wallet entries get increasing nonce offsets so all can be mined."""
        from aitbc_cli.commands.transactions import transactions

        entries = [
            {"from_wallet": "w1", "to_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C", "amount": 1.0},
            {"from_wallet": "w1", "to_address": "0x6E3D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8D", "amount": 2.0},
            {"from_wallet": "w2", "to_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C", "amount": 3.0},
        ]
        batch_file = self._write_batch_file(tmp_path, entries)
        mock_send.side_effect = ["0xh1", "0xh2", "0xh3"]

        result = runner.invoke(transactions, ["batch", "--transactions-file", batch_file, "--password", "pw"])

        assert result.exit_code == 0, result.output
        assert "3/3 successful" in result.output
        offsets = [call.kwargs["nonce_offset"] for call in mock_send.call_args_list]
        # Entries from w1 get offsets 0,1; the w2 entry starts at 0 again.
        assert offsets == [0, 1, 0]

    @patch("aitbc_cli.commands.transactions._send_transaction_impl")
    def test_batch_default_fee_matches_send(self, mock_send, runner, tmp_path):
        """An omitted ``fee`` defaults to 0.001 AIT (like ``send --fee``), not 10 AIT."""
        from decimal import Decimal

        from aitbc_cli.commands.transactions import transactions

        entries = [{"from_wallet": "w1", "to_address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C", "amount": 1.0}]
        batch_file = self._write_batch_file(tmp_path, entries)
        mock_send.side_effect = ["0xh1"]

        result = runner.invoke(transactions, ["batch", "--transactions-file", batch_file, "--password", "pw"])

        assert result.exit_code == 0, result.output
        assert mock_send.call_args[0][3] == Decimal("0.001")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
