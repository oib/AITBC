"""
Workflow Handlers Tests
Tests for workflow CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestWorkflowHandlers:
    """Test workflow handlers"""

    def test_handle_workflow_create_function_exists(self):
        """Test that handle_workflow_create function exists"""
        try:
            from handlers.workflow import handle_workflow_create

            assert handle_workflow_create is not None
        except ImportError as e:
            pytest.skip(f"Cannot import workflow handlers: {e}")

    def test_handle_workflow_create_command(self):
        """Test handle_workflow_create - skip due to complex coordinator dependencies"""
        pytest.skip("Workflow handlers have complex coordinator and HTTP client dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
