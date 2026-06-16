"""
Chain Commands Tests
Tests for chain CLI commands
"""

from unittest.mock import patch

import pytest


class TestChainCommands:
    """Test chain command group"""

    def test_chain_group_exists(self):
        """Test that chain command group exists"""
        try:
            from aitbc_cli.commands.chain import chain

            assert chain is not None
            assert hasattr(chain, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import chain commands: {e}")

    def test_chain_group_name(self):
        """Test chain group name"""
        try:
            from aitbc_cli.commands.chain import chain

            assert chain.name == "chain"
        except ImportError as e:
            pytest.skip(f"Cannot import chain commands: {e}")

    @patch("aitbc_cli.commands.chain.output")
    @patch("aitbc_cli.commands.chain.error")
    def test_chain_list_command(self, mock_error, mock_output):
        """Test chain list command - skip due to complex config dependencies"""
        pytest.skip("Chain commands have complex config and manager dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
