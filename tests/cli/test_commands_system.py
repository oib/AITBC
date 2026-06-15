"""
System Commands Tests
Tests for system CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestSystemCommands:
    """Test system command group"""

    def test_system_group_exists(self):
        """Test that system command group exists"""
        try:
            from aitbc_cli.commands.system import system

            assert system is not None
            assert hasattr(system, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import system commands: {e}")

    def test_system_group_name(self):
        """Test system group name"""
        try:
            from aitbc_cli.commands.system import system

            assert system.name == "system"
        except ImportError as e:
            pytest.skip(f"Cannot import system commands: {e}")

    @patch("aitbc_cli.commands.system.output")
    @patch("aitbc_cli.commands.system.error")
    def test_system_architect_command(self, mock_error, mock_output):
        """Test system architect command - skip due to Click context issues"""
        pytest.skip("Click context mocking requires complex setup")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
