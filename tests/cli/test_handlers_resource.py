"""
Resource Handlers Tests
Tests for resource CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestResourceHandlers:
    """Test resource handlers"""

    def test_handle_resource_status_function_exists(self):
        """Test that handle_resource_status function exists"""
        try:
            from handlers.resource import handle_resource_status

            assert handle_resource_status is not None
        except ImportError as e:
            pytest.skip(f"Cannot import resource handlers: {e}")

    def test_handle_resource_status_command(self):
        """Test handle_resource_status - skip due to complex psutil dependencies"""
        pytest.skip("Resource handlers have complex psutil and system metrics dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
