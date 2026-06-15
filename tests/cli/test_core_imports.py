"""
Core Imports Tests
Tests for core imports module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestEnsureCoordinatorApiImports:
    """Test ensure_coordinator_api_imports function"""

    @patch("aitbc_cli.core.imports.sys.path")
    def test_ensure_coordinator_api_imports_not_in_path(self, mock_path):
        """Test adding coordinator-api to sys.path when not present"""
        from aitbc_cli.core.imports import ensure_coordinator_api_imports

        mock_path.__contains__ = Mock(return_value=False)

        ensure_coordinator_api_imports()

        mock_path.insert.assert_called_once()

    @patch("aitbc_cli.core.imports.sys.path")
    def test_ensure_coordinator_api_imports_already_in_path(self, mock_path):
        """Test when coordinator-api already in sys.path"""
        from aitbc_cli.core.imports import ensure_coordinator_api_imports

        mock_path.__contains__ = Mock(return_value=True)

        ensure_coordinator_api_imports()

        mock_path.insert.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
