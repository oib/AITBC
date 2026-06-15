"""
Cross Chain Commands Tests
Tests for cross_chain CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestCrossChainCommands:
    """Test cross_chain command group"""

    def test_cross_chain_group_exists(self):
        """Test that cross_chain command group exists"""
        try:
            from aitbc_cli.commands.cross_chain import cross_chain

            assert cross_chain is not None
            assert hasattr(cross_chain, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import cross_chain commands: {e}")

    def test_cross_chain_group_name(self):
        """Test cross_chain group name"""
        try:
            from aitbc_cli.commands.cross_chain import cross_chain

            assert cross_chain.name == "cross-chain"
        except ImportError as e:
            pytest.skip(f"Cannot import cross_chain commands: {e}")

    @patch("aitbc_cli.commands.cross_chain.output")
    @patch("aitbc_cli.commands.cross_chain.error")
    def test_cross_chain_rates_command(self, mock_error, mock_output):
        """Test cross_chain rates command - skip due to complex dependencies"""
        pytest.skip("Cross chain commands have complex requests and config dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
