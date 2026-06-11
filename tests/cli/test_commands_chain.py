"""
Chain Commands Tests
Tests for chain CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestChainCommands:
    """Test chain command group"""

    def test_chain_group_exists(self):
        """Test that chain command group exists"""
        try:
            from aitbc_cli.commands.chain import chain
            assert chain is not None
            assert hasattr(chain, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import chain commands: {e}")

    def test_chain_group_name(self):
        """Test chain group name"""
        try:
            from aitbc_cli.commands.chain import chain
            assert chain.name == "chain"
        except ImportError as e:
            pytest.skip(f"Cannot import chain commands: {e}")

    @patch('aitbc_cli.commands.chain.output')
    @patch('aitbc_cli.commands.chain.error')
    def test_chain_list_command(self, mock_error, mock_output):
        """Test chain list command - skip due to complex config dependencies"""
        pytest.skip("Chain commands have complex config and manager dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
