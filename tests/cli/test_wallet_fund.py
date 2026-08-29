"""Tests for the aitbc wallet fund command."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestWalletFund:
    """Test wallet fund command."""

    def _make_response(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"success": True, "address": "0xabc123", "amount": 36000000}
        response.raise_for_status.return_value = None
        return response

    @patch("httpx.post")
    @patch("aitbc_cli.config.get_config")
    def test_wallet_fund_uses_rpc_faucet_and_bech32(self, mock_get_config, mock_post, runner, mock_config):
        mock_get_config.return_value = mock_config
        mock_post.return_value = self._make_response()

        from aitbc_cli.commands.wallet import wallet

        result = runner.invoke(
            wallet,
            ["fund", "--address", "0xAbc1234567890123456789012345678901234567", "--amount-ait", "1.0"],
        )

        assert result.exit_code == 0, result.output
        call = mock_post.call_args
        assert call[0][0] == "http://localhost:8202/rpc/faucet"
        assert call.kwargs["json"]["address"] == "0xabc1234567890123456789012345678901234567"
        assert call.kwargs["json"]["amount"] == 36000000

    @patch("httpx.post")
    @patch("aitbc_cli.config.get_config")
    def test_wallet_fund_amount_in_units(self, mock_get_config, mock_post, runner, mock_config):
        mock_get_config.return_value = mock_config
        response = self._make_response()
        response.json.return_value = {"success": True, "address": "0xabc123", "amount": 7200}
        mock_post.return_value = response

        from aitbc_cli.commands.wallet import wallet

        result = runner.invoke(
            wallet,
            ["fund", "--address", "0xAbc1234567890123456789012345678901234567", "--amount", "7200"],
        )

        assert result.exit_code == 0, result.output
        assert mock_post.call_args.kwargs["json"]["amount"] == 7200
        assert mock_post.call_args.kwargs["json"]["address"].lower() == "0xabc1234567890123456789012345678901234567"

    @patch("aitbc_cli.config.get_config")
    def test_wallet_fund_invalid_address(self, mock_get_config, runner, mock_config):
        mock_get_config.return_value = mock_config

        from aitbc_cli.commands.wallet import wallet

        result = runner.invoke(wallet, ["fund", "--address", "not-an-address"])
        assert "Invalid address" in result.output
