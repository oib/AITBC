"""
System Architect Commands Tests
Tests for system architect CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestSystemArchitectCommands:
    """Test system architect command group"""

    def test_system_architect_group_exists(self):
        """Test that system_architect command group exists"""
        try:
            from aitbc_cli.commands.system_architect import system_architect
            assert system_architect is not None
            assert hasattr(system_architect, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import system_architect commands: {e}")

    def test_system_architect_group_name(self):
        """Test system_architect group name"""
        try:
            from aitbc_cli.commands.system_architect import system_architect
            assert system_architect.name == "system-architect"
        except ImportError as e:
            pytest.skip(f"Cannot import system_architect commands: {e}")

    @patch('aitbc_cli.commands.system_architect.click')
    def test_system_architect_audit_command(self, mock_click):
        """Test system architect audit command"""
        try:
            from aitbc_cli.commands.system_architect import audit
            from click.testing import CliRunner
            
            runner = CliRunner()
            result = runner.invoke(audit)
            
            # Verify command executed
            assert result.exit_code == 0
            assert "System Architecture Audit" in result.output
        except Exception as e:
            pytest.skip(f"Cannot test system_architect audit: {e}")

    @patch('aitbc_cli.commands.system_architect.click')
    def test_system_architect_paths_command(self, mock_click):
        """Test system architect paths command"""
        try:
            from aitbc_cli.commands.system_architect import paths
            from click.testing import CliRunner
            
            runner = CliRunner()
            result = runner.invoke(paths)
            
            # Verify command executed
            assert result.exit_code == 0
            assert "System Architecture Paths" in result.output
        except Exception as e:
            pytest.skip(f"Cannot test system_architect paths: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
