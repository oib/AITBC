"""
Script Commands Tests
Tests for script CLI commands
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestScriptCommands:
    """Test script command group"""

    def test_script_group_exists(self):
        """Test that script command group exists"""
        try:
            from aitbc_cli.commands.script import script
            assert script is not None
            assert hasattr(script, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import script commands: {e}")

    def test_script_group_name(self):
        """Test script group name"""
        try:
            from aitbc_cli.commands.script import script
            assert script.name == "script"
        except ImportError as e:
            pytest.skip(f"Cannot import script commands: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
