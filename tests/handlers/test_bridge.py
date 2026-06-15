"""
Bridge Handler Tests
Tests for blockchain event bridge handlers
"""

from unittest.mock import Mock, patch

import pytest


class TestHandleBridgeRestart:
    """Test handle_bridge_restart function"""

    @patch("handlers.bridge.logger")
    def test_handle_bridge_restart_test_mode(self, mock_logger):
        """Test bridge restart in test mode"""
        # Import here to avoid import errors
        from handlers.bridge import handle_bridge_restart

        args = Mock()
        args.test_mode = True

        handle_bridge_restart(args)

        assert mock_logger.info.call_count > 0

    @patch("subprocess.run")
    @patch("handlers.bridge.logger")
    def test_handle_bridge_restart_success(self, mock_logger, mock_subprocess):
        """Test successful bridge restart"""
        from handlers.bridge import handle_bridge_restart

        args = Mock()
        args.test_mode = False

        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        handle_bridge_restart(args)

        assert mock_logger.info.call_count > 0

    @patch("subprocess.run")
    @patch("handlers.bridge.logger")
    def test_handle_bridge_restart_failure(self, mock_logger, mock_subprocess):
        """Test bridge restart with failure"""
        from handlers.bridge import handle_bridge_restart

        args = Mock()
        args.test_mode = False

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Service not found"
        mock_subprocess.return_value = mock_result

        handle_bridge_restart(args)

        mock_logger.error.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
