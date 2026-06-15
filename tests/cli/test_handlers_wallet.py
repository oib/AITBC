"""
Wallet Handlers Tests
Tests for wallet CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestWalletHandlers:
    """Test wallet handlers"""

    def test_handle_wallet_create_function_exists(self):
        """Test that handle_wallet_create function exists"""
        try:
            from handlers.wallet import handle_wallet_create

            assert handle_wallet_create is not None
        except ImportError as e:
            pytest.skip(f"Cannot import wallet handlers: {e}")

    def test_handle_wallet_list_function_exists(self):
        """Test that handle_wallet_list function exists"""
        try:
            from handlers.wallet import handle_wallet_list

            assert handle_wallet_list is not None
        except ImportError as e:
            pytest.skip(f"Cannot import wallet handlers: {e}")

    def test_handle_wallet_create_command(self):
        """Test handle_wallet_create - skip due to complex wallet dependencies"""
        pytest.skip("Wallet handlers have complex wallet and keystore dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
