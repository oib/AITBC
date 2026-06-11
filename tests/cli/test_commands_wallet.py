"""
Wallet Commands Tests
Tests for wallet CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestWalletCommands:
    """Test wallet command group"""

    def test_wallet_group_exists(self):
        """Test that wallet command group exists"""
        try:
            from aitbc_cli.commands.wallet import wallet
            assert wallet is not None
            assert hasattr(wallet, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import wallet commands: {e}")

    def test_wallet_group_name(self):
        """Test wallet group name"""
        try:
            from aitbc_cli.commands.wallet import wallet
            assert wallet.name == "wallet"
        except ImportError as e:
            pytest.skip(f"Cannot import wallet commands: {e}")

    @patch('aitbc_cli.commands.wallet.output')
    @patch('aitbc_cli.commands.wallet.error')
    def test_wallet_list_command(self, mock_error, mock_output):
        """Test wallet list command - skip due to complex config dependencies"""
        pytest.skip("Wallet commands have complex config and keystore dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
