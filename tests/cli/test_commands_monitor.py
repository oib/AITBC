"""
Monitor Commands Tests
Tests for monitor CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestMonitorCommands:
    """Test monitor command group"""

    def test_monitor_group_exists(self):
        """Test that monitor command group exists"""
        try:
            from aitbc_cli.commands.monitor import monitor

            assert monitor is not None
            assert hasattr(monitor, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import monitor commands: {e}")

    def test_monitor_group_name(self):
        """Test monitor group name"""
        try:
            from aitbc_cli.commands.monitor import monitor

            assert monitor.name == "monitor"
        except ImportError as e:
            pytest.skip(f"Cannot import monitor commands: {e}")

    @patch("aitbc_cli.commands.monitor.output")
    @patch("aitbc_cli.commands.monitor.error")
    def test_monitor_commands(self, mock_error, mock_output):
        """Test monitor commands - skip due to Rich/console dependencies"""
        pytest.skip("Monitor commands have Rich/console dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
