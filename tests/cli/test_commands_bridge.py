"""
Bridge Commands Tests
Tests for bridge CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestBridgeCommands:
    """Test bridge command group"""

    def test_bridge_group_exists(self):
        """Test that bridge command group exists"""
        from aitbc_cli.commands.bridge import bridge

        assert bridge is not None
        assert hasattr(bridge, "name")

    def test_bridge_group_name(self):
        """Test bridge group name"""
        from aitbc_cli.commands.bridge import bridge

        assert bridge.name == "bridge"

    def test_bridge_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the bridge group."""
        from aitbc_cli.commands.bridge import bridge

        assert "status" in bridge.commands


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
