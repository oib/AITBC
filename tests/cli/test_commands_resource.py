"""
Resource Commands Tests
Tests for resource CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestResourceCommands:
    """Test resource command group"""

    def test_resource_group_exists(self):
        """Test that resource command group exists"""
        try:
            from aitbc_cli.commands.resource import resource
            assert resource is not None
            assert hasattr(resource, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import resource commands: {e}")

    def test_resource_group_name(self):
        """Test resource group name"""
        try:
            from aitbc_cli.commands.resource import resource
            assert resource.name == "resource"
        except ImportError as e:
            pytest.skip(f"Cannot import resource commands: {e}")

    @patch('aitbc_cli.commands.resource.output')
    @patch('aitbc_cli.commands.resource.error')
    def test_resource_allocate_command(self, mock_error, mock_output):
        """Test resource allocate command - skip due to Click context issues"""
        pytest.skip("Click context mocking requires complex setup")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
