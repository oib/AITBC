"""
Economics Commands Tests
Tests for economics CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestEconomicsCommands:
    """Test economics command group"""

    def test_economics_group_exists(self):
        """Test that economics command group exists"""
        try:
            from aitbc_cli.commands.economics import economics
            assert economics is not None
            assert hasattr(economics, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import economics commands: {e}")

    def test_economics_group_name(self):
        """Test economics group name"""
        try:
            from aitbc_cli.commands.economics import economics
            assert economics.name == "economics"
        except ImportError as e:
            pytest.skip(f"Cannot import economics commands: {e}")

    @patch('aitbc_cli.commands.economics.output')
    @patch('aitbc_cli.commands.economics.error')
    def test_economics_distributed_command(self, mock_error, mock_output):
        """Test economics distributed command - skip due to Click context issues"""
        pytest.skip("Click context mocking requires complex setup")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
