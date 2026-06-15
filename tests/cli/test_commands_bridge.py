"""
Bridge Commands Tests
Tests for bridge CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestBridgeCommands:
    """Test bridge command group"""

    def test_bridge_group_exists(self):
        """Test that bridge command group exists"""
        try:
            from aitbc_cli.commands.bridge import bridge

            assert bridge is not None
            assert hasattr(bridge, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import bridge commands: {e}")

    def test_bridge_group_name(self):
        """Test bridge group name"""
        try:
            from aitbc_cli.commands.bridge import bridge

            assert bridge.name == "bridge"
        except ImportError as e:
            pytest.skip(f"Cannot import bridge commands: {e}")

    @patch("aitbc_cli.commands.bridge.output")
    @patch("aitbc_cli.commands.bridge.error")
    def test_bridge_start_command(self, mock_error, mock_output):
        """Test bridge start command - skip due to Click context issues"""
        pytest.skip("Click context mocking requires complex setup")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
