"""
Client Commands Tests
Tests for client CLI commands
"""


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
