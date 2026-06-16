"""
Tests for subprocess utility functions
"""

import subprocess
from unittest.mock import Mock, patch

import pytest
from aitbc_cli.utils.subprocess import run_subprocess


class TestRunSubprocess:
    """Test run_subprocess function"""

    @patch("aitbc_cli.utils.subprocess.subprocess.run")
    def test_run_subprocess_success_capture_output(self, mock_run):
        """Test successful command with captured output"""
        mock_result = Mock()
        mock_result.stdout = "test output\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = run_subprocess(["echo", "test"])

        assert result == "test output"
        mock_run.assert_called_once()

    @patch("aitbc_cli.utils.subprocess.subprocess.run")
    def test_run_subprocess_success_no_capture(self, mock_run):
        """Test successful command without capturing output"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = run_subprocess(["echo", "test"], capture_output=False)

        assert result == mock_result
        mock_run.assert_called_once()

    @patch("aitbc_cli.utils.subprocess.subprocess.run")
    @patch("aitbc_cli.utils.subprocess.sys.exit")
    def test_run_subprocess_failure_with_check(self, mock_exit, mock_run):
        """Test command failure with check=True"""
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")

        run_subprocess(["false"], check=True)

        mock_exit.assert_called_once_with(1)

    @patch("aitbc_cli.utils.subprocess.subprocess.run")
    def test_run_subprocess_failure_without_check(self, mock_run):
        """Test command failure with check=False"""
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")

        result = run_subprocess(["false"], check=False)

        assert result is None

    @patch("aitbc_cli.utils.subprocess.subprocess.run")
    @patch("aitbc_cli.utils.subprocess.sys.exit")
    def test_run_subprocess_generic_exception_with_check(self, mock_exit, mock_run):
        """Test generic exception with check=True"""
        mock_run.side_effect = Exception("Unexpected error")

        run_subprocess(["cmd"], check=True)

        mock_exit.assert_called_once_with(1)

    @patch("aitbc_cli.utils.subprocess.subprocess.run")
    def test_run_subprocess_generic_exception_without_check(self, mock_run):
        """Test generic exception with check=False"""
        mock_run.side_effect = Exception("Unexpected error")

        result = run_subprocess(["cmd"], check=False)

        assert result is None

    @patch("aitbc_cli.utils.subprocess.subprocess.run")
    def test_run_subprocess_shell_always_false(self, mock_run):
        """Test that shell parameter is always False for security"""
        mock_result = Mock()
        mock_result.stdout = "output"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        run_subprocess(["cmd"], shell=True)

        # Verify shell=False was used regardless of input
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["shell"] is False

    @patch("aitbc_cli.utils.subprocess.subprocess.run")
    def test_run_subprocess_text_true(self, mock_run):
        """Test that text=True is always used"""
        mock_result = Mock()
        mock_result.stdout = "output"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        run_subprocess(["cmd"])

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["text"] is True

    @patch("aitbc_cli.utils.subprocess.subprocess.run")
    def test_run_subprocess_passes_kwargs(self, mock_run):
        """Test that additional kwargs are passed through"""
        mock_result = Mock()
        mock_result.stdout = "output"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        run_subprocess(["cmd"], timeout=30, cwd="/tmp")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 30
        assert call_kwargs["cwd"] == "/tmp"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
