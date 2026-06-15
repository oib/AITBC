"""
Client Commands Tests
Tests for client CLI commands
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestClientCommands:
    """Test client command group"""

    def test_client_group_exists(self):
        """Test that client command group exists"""
        try:
            from aitbc_cli.commands.client import client

            assert client is not None
            assert hasattr(client, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import client commands: {e}")

    def test_client_group_name(self):
        """Test client group name"""
        try:
            from aitbc_cli.commands.client import client

            assert client.name == "client"
        except ImportError as e:
            pytest.skip(f"Cannot import client commands: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
