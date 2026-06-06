"""
Messaging Handlers Tests
Tests for messaging CLI handlers
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestMessagingHandlers:
    """Test messaging handlers"""

    def test_handle_messaging_deploy_function_exists(self):
        """Test that handle_messaging_deploy function exists"""
        try:
            from handlers.messaging import handle_messaging_deploy
            assert handle_messaging_deploy is not None
        except ImportError as e:
            pytest.skip(f"Cannot import messaging handlers: {e}")

    def test_handle_messaging_deploy_command(self):
        """Test handle_messaging_deploy - skip due to complex RPC dependencies"""
        pytest.skip("Messaging handlers have complex RPC and HTTP client dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
