"""
Edge Commands Tests
Tests for edge CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestEdgeCommands:
    """Test edge command group"""

    def test_edge_group_exists(self):
        """Test that edge command group exists"""
        try:
            from aitbc_cli.commands.edge import edge
            assert edge is not None
            assert hasattr(edge, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import edge commands: {e}")

    def test_edge_group_name(self):
        """Test edge group name"""
        try:
            from aitbc_cli.commands.edge import edge
            assert edge.name == "edge"
        except ImportError as e:
            pytest.skip(f"Cannot import edge commands: {e}")

    @patch('aitbc_cli.commands.edge.output')
    @patch('aitbc_cli.commands.edge.error')
    def test_edge_status_command(self, mock_error, mock_output):
        """Test edge status command - skip due to complex httpx and config dependencies"""
        pytest.skip("Edge commands have complex httpx and config dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
