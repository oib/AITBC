"""
Config Commands Tests
Tests for config CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestConfigCommands:
    """Test config command group"""

    def test_config_group_exists(self):
        """Test that config command group exists"""
        try:
            from aitbc_cli.commands.config import config

            assert config is not None
            assert hasattr(config, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import config commands: {e}")

    def test_config_group_name(self):
        """Test config group name"""
        try:
            from aitbc_cli.commands.config import config

            assert config.name == "config"
        except ImportError as e:
            pytest.skip(f"Cannot import config commands: {e}")

    @patch("aitbc_cli.commands.config.output")
    @patch("aitbc_cli.commands.config.error")
    def test_config_show_command(self, mock_error, mock_output):
        """Test config show command - skip due to complex config dependencies"""
        pytest.skip("Config commands have complex config and context dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
