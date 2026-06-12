"""
Sync Handler Tests
Tests for blockchain sync handler
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestHandleSyncBulk:
    """Test handle_sync_bulk function"""

    @patch('handlers.sync.subprocess.run')
    @patch('handlers.sync.Path')
    def test_handle_sync_bulk_success(self, mock_path, mock_subprocess):
        """Test successful bulk sync"""
        from handlers.sync import handle_sync_bulk

        # Mock path resolution
        mock_path_instance = MagicMock()
        mock_path_instance.parents = [MagicMock(), MagicMock(), MagicMock()]
        mock_path_instance.parents[2] = Path("/opt/aitbc")
        mock_path.return_value = mock_path_instance

        # Mock file existence
        mock_sync_cli = MagicMock()
        mock_sync_cli.exists.return_value = True
        mock_path_instance.__truediv__ = MagicMock(return_value=mock_sync_cli)

        # Mock subprocess
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        # Create args
        args = Mock()
        args.source = "http://source.com"
        args.import_url = "http://import.com"
        args.batch_size = 100
        args.poll_interval = 10

        ctx = Mock()

        result = handle_sync_bulk(args, ctx)

        assert result == 0
        mock_subprocess.assert_called_once()

    @patch('handlers.sync.subprocess.run')
    @patch('handlers.sync.Path')
    def test_handle_sync_bulk_script_not_found(self, mock_path, mock_subprocess):
        """Test bulk sync when script not found"""
        from handlers.sync import handle_sync_bulk

        # Mock path resolution
        mock_path_instance = MagicMock()
        mock_path_instance.parents = [MagicMock(), MagicMock(), MagicMock()]
        mock_path_instance.parents[2] = Path("/opt/aitbc")
        mock_path.return_value = mock_path_instance

        # Mock file not existing
        mock_sync_cli = MagicMock()
        mock_sync_cli.exists.return_value = False
        mock_path_instance.__truediv__ = MagicMock(return_value=mock_sync_cli)

        args = Mock()
        args.source = "http://source.com"
        args.import_url = "http://import.com"
        args.batch_size = 100
        args.poll_interval = 10

        ctx = Mock()

        result = handle_sync_bulk(args, ctx)

        assert result == 1

    @patch('handlers.sync.subprocess.run')
    @patch('handlers.sync.Path')
    def test_handle_sync_bulk_subprocess_failure(self, mock_path, mock_subprocess):
        """Test bulk sync when subprocess fails"""
        from handlers.sync import handle_sync_bulk

        # Mock path resolution
        mock_path_instance = MagicMock()
        mock_path_instance.parents = [MagicMock(), MagicMock(), MagicMock()]
        mock_path_instance.parents[2] = Path("/opt/aitbc")
        mock_path.return_value = mock_path_instance

        # Mock file existence
        mock_sync_cli = MagicMock()
        mock_sync_cli.exists.return_value = True
        mock_path_instance.__truediv__ = MagicMock(return_value=mock_sync_cli)

        # Mock subprocess failure
        mock_result = Mock()
        mock_result.returncode = 1
        mock_subprocess.return_value = mock_result

        args = Mock()
        args.source = "http://source.com"
        args.import_url = "http://import.com"
        args.batch_size = 100
        args.poll_interval = 10

        ctx = Mock()

        result = handle_sync_bulk(args, ctx)

        assert result == 1

    @patch('handlers.sync.subprocess.run')
    @patch('handlers.sync.Path')
    def test_handle_sync_bulk_exception(self, mock_path, mock_subprocess):
        """Test bulk sync when exception occurs"""
        from handlers.sync import handle_sync_bulk

        # Mock path resolution
        mock_path_instance = MagicMock()
        mock_path_instance.parents = [MagicMock(), MagicMock(), MagicMock()]
        mock_path_instance.parents[2] = Path("/opt/aitbc")
        mock_path.return_value = mock_path_instance

        # Mock file existence
        mock_sync_cli = MagicMock()
        mock_sync_cli.exists.return_value = True
        mock_path_instance.__truediv__ = MagicMock(return_value=mock_sync_cli)

        # Mock subprocess exception
        mock_subprocess.side_effect = Exception("Test error")

        args = Mock()
        args.source = "http://source.com"
        args.import_url = "http://import.com"
        args.batch_size = 100
        args.poll_interval = 10

        ctx = Mock()

        result = handle_sync_bulk(args, ctx)

        assert result == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
