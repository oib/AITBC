"""
Client Commands Tests
Tests for client CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).

The ``client`` command group is a stub module with no subcommands registered
yet, so only group-level tests are applicable.
"""

import pytest


class TestClientCommands:
    """Test client command group"""

    def test_client_group_exists(self):
        """Test that client command group exists"""
        from aitbc_cli.commands.client import client

        assert client is not None
        assert hasattr(client, "name")

    def test_client_group_name(self):
        """Test client group name"""
        from aitbc_cli.commands.client import client

        assert client.name == "client"

    def test_client_group_has_no_subcommands(self):
        """The ``client`` group is a stub with no subcommands registered yet."""
        from aitbc_cli.commands.client import client

        assert len(client.commands) == 0

    def test_client_group_invokes_without_error(self, runner):
        """Invoking the ``client`` group with ``--help`` exits cleanly."""
        from aitbc_cli.commands.client import client

        result = runner.invoke(client, ["--help"])
        assert result.exit_code == 0
        assert "Client commands" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
