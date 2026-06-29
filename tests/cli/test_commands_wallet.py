"""
Wallet Commands Tests
Tests for wallet CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).

The wallet command group is a package (``aitbc_cli.commands.wallet``) whose
group callback performs complex setup (chain-id detection, dual-mode adapter
initialisation).  These dependencies are mocked so the subcommands can be
exercised via ``CliRunner``.
"""

from unittest.mock import patch

import pytest


class TestWalletCommands:
    """Test wallet command group"""

    def test_wallet_group_exists(self):
        """Test that wallet command group exists"""
        from aitbc_cli.commands.wallet import wallet

        assert wallet is not None
        assert hasattr(wallet, "name")

    def test_wallet_group_name(self):
        """Test wallet group name"""
        from aitbc_cli.commands.wallet import wallet

        assert wallet.name == "wallet"

    def test_wallet_group_has_create_subcommand(self):
        """The ``create`` subcommand is registered on the wallet group."""
        from aitbc_cli.commands.wallet import wallet

        assert "create" in wallet.commands

    def test_wallet_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the wallet group."""
        from aitbc_cli.commands.wallet import wallet

        assert "list" in wallet.commands

    def test_wallet_group_has_balance_subcommand(self):
        """The ``balance`` subcommand is registered on the wallet group."""
        from aitbc_cli.commands.wallet import wallet

        assert "balance" in wallet.commands

    def test_wallet_group_has_send_subcommand(self):
        """The ``send`` subcommand is registered on the wallet group."""
        from aitbc_cli.commands.wallet import wallet

        assert "send" in wallet.commands

    def test_wallet_group_has_delete_subcommand(self):
        """The ``delete`` subcommand is registered on the wallet group."""
        from aitbc_cli.commands.wallet import wallet

        assert "delete" in wallet.commands

    def test_wallet_group_has_switch_subcommand(self):
        """The ``switch`` subcommand is registered on the wallet group."""
        from aitbc_cli.commands.wallet import wallet

        assert "switch" in wallet.commands

    def test_wallet_group_has_stake_subcommand(self):
        """The ``stake`` subcommand is registered on the wallet group."""
        from aitbc_cli.commands.wallet import wallet

        assert "stake" in wallet.commands

    @patch("aitbc_cli.utils.dual_mode_wallet_adapter.DualModeWalletAdapter")
    @patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="test-chain")
    @patch("aitbc_cli.commands.wallet.get_config")
    def test_wallet_list_command(self, mock_get_config, mock_get_chain_id, mock_adapter_class, runner):
        """``wallet list`` lists wallets via the dual-mode adapter."""
        mock_config = mock_get_config.return_value
        mock_config.blockchain_rpc_url = "http://localhost:8202"

        mock_adapter = mock_adapter_class.return_value
        mock_adapter.is_daemon_available.return_value = True
        mock_adapter.list_wallets.return_value = [
            {"wallet_name": "test-wallet", "address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"},
        ]

        from aitbc_cli.commands.wallet import wallet

        result = runner.invoke(wallet, ["list"])

        assert result.exit_code == 0, result.output
        assert "test-wallet" in result.output

    @patch("aitbc_cli.utils.dual_mode_wallet_adapter.DualModeWalletAdapter")
    @patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="test-chain")
    @patch("aitbc_cli.commands.wallet.get_config")
    def test_wallet_list_empty(self, mock_get_config, mock_get_chain_id, mock_adapter_class, runner):
        """``wallet list`` handles an empty wallet list."""
        mock_config = mock_get_config.return_value
        mock_config.blockchain_rpc_url = "http://localhost:8202"

        mock_adapter = mock_adapter_class.return_value
        mock_adapter.is_daemon_available.return_value = True
        mock_adapter.list_wallets.return_value = []

        from aitbc_cli.commands.wallet import wallet

        result = runner.invoke(wallet, ["list"])

        assert result.exit_code == 0, result.output
        assert "No wallets found" in result.output

    @patch("aitbc_cli.utils.dual_mode_wallet_adapter.DualModeWalletAdapter")
    @patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="test-chain")
    @patch("aitbc_cli.commands.wallet.get_config")
    def test_wallet_list_daemon_unavailable_fallback(self, mock_get_config, mock_get_chain_id, mock_adapter_class, runner):
        """``wallet list`` falls back to file mode when daemon is unavailable."""
        mock_config = mock_get_config.return_value
        mock_config.blockchain_rpc_url = "http://localhost:8202"

        # First adapter (daemon mode) is unavailable, second (file mode) returns empty list
        mock_daemon_adapter = mock_adapter_class.return_value
        mock_daemon_adapter.is_daemon_available.return_value = False
        mock_daemon_adapter.list_wallets.return_value = []

        from aitbc_cli.commands.wallet import wallet

        result = runner.invoke(wallet, ["list"])

        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.commands.wallet.basic._get_wallet_password", return_value="testpass")
    @patch("aitbc_cli.utils.dual_mode_wallet_adapter.DualModeWalletAdapter")
    @patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="test-chain")
    @patch("aitbc_cli.commands.wallet.get_config")
    def test_wallet_create_command(
        self, mock_get_config, mock_get_chain_id, mock_adapter_class, mock_get_pass, runner, tmp_path
    ):
        """``wallet create`` creates a new wallet file."""
        mock_config = mock_get_config.return_value
        mock_config.blockchain_rpc_url = "http://localhost:8202"

        from aitbc_cli.commands.wallet import wallet

        result = runner.invoke(
            wallet,
            ["--wallet-path", str(tmp_path / "newwallet.json"), "create", "newwallet", "--no-encrypt"],
        )

        assert result.exit_code == 0, result.output
        assert "newwallet" in result.output
        assert (tmp_path / "newwallet.json").exists()

    @patch("aitbc_cli.utils.dual_mode_wallet_adapter.DualModeWalletAdapter")
    @patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="test-chain")
    @patch("aitbc_cli.commands.wallet.get_config")
    def test_wallet_create_already_exists(
        self, mock_get_config, mock_get_chain_id, mock_adapter_class, runner, tmp_path
    ):
        """``wallet create`` reports an error when the wallet already exists."""
        mock_config = mock_get_config.return_value
        mock_config.blockchain_rpc_url = "http://localhost:8202"

        # Pre-create the wallet file
        wallet_path = tmp_path / "existing.json"
        wallet_path.write_text('{"wallet_id": "existing"}')

        from aitbc_cli.commands.wallet import wallet

        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), "create", "existing", "--no-encrypt"],
        )

        assert result.exit_code == 0, result.output
        assert "already exists" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
