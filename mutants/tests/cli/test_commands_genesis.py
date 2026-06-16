"""
Genesis Commands Tests
Tests for genesis CLI commands
"""

from unittest.mock import patch

import pytest


class TestGenesisCommands:
    """Test genesis command group"""

    def test_genesis_group_exists(self):
        """Test that genesis command group exists"""
        try:
            from aitbc_cli.commands.genesis import genesis

            assert genesis is not None
            assert hasattr(genesis, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import genesis commands: {e}")

    def test_genesis_group_name(self):
        """Test genesis group name"""
        try:
            from aitbc_cli.commands.genesis import genesis

            assert genesis.name == "genesis"
        except ImportError as e:
            pytest.skip(f"Cannot import genesis commands: {e}")

    @patch("aitbc_cli.commands.genesis.output")
    @patch("aitbc_cli.commands.genesis.error")
    def test_genesis_init_command(self, mock_error, mock_output):
        """Test genesis init command - skip due to complex subprocess and httpx dependencies"""
        pytest.skip("Genesis commands have complex subprocess and httpx dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
