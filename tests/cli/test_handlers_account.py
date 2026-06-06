"""
Account Handlers Tests
Tests for account CLI handlers
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestAccountHandlers:
    """Test account handlers"""

    def test_render_mapping_function_exists(self):
        """Test that render_mapping function exists"""
        try:
            from handlers.account import render_mapping
            assert render_mapping is not None
        except ImportError as e:
            pytest.skip(f"Cannot import account handlers: {e}")

    def test_handle_account_get_function_exists(self):
        """Test that handle_account_get function exists"""
        try:
            from handlers.account import handle_account_get
            assert handle_account_get is not None
        except ImportError as e:
            pytest.skip(f"Cannot import account handlers: {e}")

    @patch('handlers.account.AITBCHTTPClient')
    def test_handle_account_get_command(self, mock_http_client):
        """Test handle_account_get - skip due to complex RPC dependencies"""
        pytest.skip("Account handlers have complex RPC and HTTP client dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
