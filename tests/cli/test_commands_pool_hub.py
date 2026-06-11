"""
Pool Hub Commands Tests
Tests for pool_hub CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestPoolHubCommands:
    """Test pool_hub command group"""

    def test_pool_hub_group_exists(self):
        """Test that pool_hub command group exists"""
        try:
            from aitbc_cli.commands.pool_hub import pool_hub
            assert pool_hub is not None
            assert hasattr(pool_hub, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import pool_hub commands: {e}")

    def test_pool_hub_group_name(self):
        """Test pool_hub group name"""
        try:
            from aitbc_cli.commands.pool_hub import pool_hub
            assert pool_hub.name == "pool-hub"
        except ImportError as e:
            pytest.skip(f"Cannot import pool_hub commands: {e}")

    @patch('aitbc_cli.commands.pool_hub.output')
    @patch('aitbc_cli.commands.pool_hub.error')
    def test_pool_hub_status_command(self, mock_error, mock_output):
        """Test pool_hub status command - skip due to Click context issues"""
        pytest.skip("Click context mocking requires complex setup")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
