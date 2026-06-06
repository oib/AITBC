"""
Subprocess Utils Tests
Tests for subprocess utility functions
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestRunSubprocess:
    """Test run_subprocess function"""

    @patch('aitbc_cli.utils.subprocess.subprocess.run')
    @patch('aitbc_cli.utils.subprocess.error')
    def test_run_subprocess_success_capture_output(self, mock_error, mock_run):
        """Test successful subprocess with captured output"""
        from aitbc_cli.utils.subprocess import run_subprocess
        
        mock_result = Mock()
        mock_result.stdout = "test output\n"
        mock_run.return_value = mock_result
        
        result = run_subprocess(["echo", "test"])
        
        assert result == "test output"
        mock_run.assert_called_once_with(["echo", "test"], check=True, capture_output=True, text=True, shell=False)

    @patch('aitbc_cli.utils.subprocess.subprocess.run')
    @patch('aitbc_cli.utils.subprocess.error')
    def test_run_subprocess_success_no_capture(self, mock_error, mock_run):
        """Test successful subprocess without capturing output"""
        from aitbc_cli.utils.subprocess import run_subprocess
        
        mock_result = Mock()
        mock_run.return_value = mock_result
        
        result = run_subprocess(["echo", "test"], capture_output=False)
        
        assert result == mock_result
        mock_run.assert_called_once_with(["echo", "test"], check=True, capture_output=False, text=True, shell=False)

    @patch('aitbc_cli.utils.subprocess.subprocess.run')
    @patch('aitbc_cli.utils.subprocess.error')
    @patch('aitbc_cli.utils.subprocess.sys.exit')
    def test_run_subprocess_called_process_error_check_true(self, mock_exit, mock_error, mock_run):
        """Test subprocess with CalledProcessError when check=True"""
        from aitbc_cli.utils.subprocess import run_subprocess
        import subprocess
        
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
        
        run_subprocess(["false"], check=True)
        
        mock_error.assert_called_once()
        mock_exit.assert_called_once_with(1)

    @patch('aitbc_cli.utils.subprocess.subprocess.run')
    @patch('aitbc_cli.utils.subprocess.error')
    def test_run_subprocess_called_process_error_check_false(self, mock_error, mock_run):
        """Test subprocess with CalledProcessError when check=False"""
        from aitbc_cli.utils.subprocess import run_subprocess
        import subprocess
        
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
        
        result = run_subprocess(["false"], check=False)
        
        assert result is None
        mock_error.assert_called_once()

    @patch('aitbc_cli.utils.subprocess.subprocess.run')
    @patch('aitbc_cli.utils.subprocess.error')
    @patch('aitbc_cli.utils.subprocess.sys.exit')
    def test_run_subprocess_generic_error_check_true(self, mock_exit, mock_error, mock_run):
        """Test subprocess with generic error when check=True"""
        from aitbc_cli.utils.subprocess import run_subprocess
        
        mock_run.side_effect = Exception("Unexpected error")
        
        run_subprocess(["cmd"], check=True)
        
        mock_error.assert_called_once()
        mock_exit.assert_called_once_with(1)

    @patch('aitbc_cli.utils.subprocess.subprocess.run')
    @patch('aitbc_cli.utils.subprocess.error')
    def test_run_subprocess_generic_error_check_false(self, mock_error, mock_run):
        """Test subprocess with generic error when check=False"""
        from aitbc_cli.utils.subprocess import run_subprocess
        
        mock_run.side_effect = Exception("Unexpected error")
        
        result = run_subprocess(["cmd"], check=False)
        
        assert result is None
        mock_error.assert_called_once()

    @patch('aitbc_cli.utils.subprocess.subprocess.run')
    @patch('aitbc_cli.utils.subprocess.error')
    def test_run_subprocess_shell_always_false(self, mock_error, mock_run):
        """Test that shell parameter is always forced to False for security"""
        from aitbc_cli.utils.subprocess import run_subprocess
        
        mock_result = Mock()
        mock_result.stdout = "output"
        mock_run.return_value = mock_result
        
        # Even if shell=True is passed, it should be overridden to False
        run_subprocess(["cmd"], shell=True)
        
        # Check that shell=False was actually used
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs['shell'] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
