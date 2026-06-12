"""
Error Handling Utils Tests
Tests for error handling utility functions
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestCLIError:
    """Test CLIError exception"""

    def test_cli_error_creation(self):
        """Test creating CLIError"""
        from aitbc_cli.utils.error_handling import CLIError

        error = CLIError("Test error", exit_code=5)

        assert error.message == "Test error"
        assert error.exit_code == 5
        assert str(error) == "Test error"

    def test_cli_error_default_exit_code(self):
        """Test CLIError with default exit code"""
        from aitbc_cli.utils.error_handling import CLIError

        error = CLIError("Test error")

        assert error.exit_code == 1


class TestNetworkError:
    """Test NetworkError exception"""

    def test_network_error_creation(self):
        """Test creating NetworkError"""
        from aitbc_cli.utils.error_handling import NetworkError

        error = NetworkError("Connection failed")

        assert error.message == "Network error: Connection failed"
        assert error.exit_code == 2


class TestConfigurationError:
    """Test ConfigurationError exception"""

    def test_configuration_error_creation(self):
        """Test creating ConfigurationError"""
        from aitbc_cli.utils.error_handling import ConfigurationError

        error = ConfigurationError("Invalid config")

        assert error.message == "Configuration error: Invalid config"
        assert error.exit_code == 3


class TestValidationError:
    """Test ValidationError exception"""

    def test_validation_error_creation(self):
        """Test creating ValidationError"""
        from aitbc_cli.utils.error_handling import ValidationError

        error = ValidationError("Invalid input")

        assert error.message == "Validation error: Invalid input"
        assert error.exit_code == 4


class TestAPIError:
    """Test APIError exception"""

    def test_api_error_without_status(self):
        """Test creating APIError without status code"""
        from aitbc_cli.utils.error_handling import APIError

        error = APIError("Request failed")

        assert error.message == "API error: Request failed"
        assert error.exit_code == 5

    def test_api_error_with_status(self):
        """Test creating APIError with status code"""
        from aitbc_cli.utils.error_handling import APIError

        error = APIError("Request failed", status_code=404)

        assert error.message == "API error: Request failed (HTTP 404)"
        assert error.exit_code == 5


class TestHandleCLIError:
    """Test handle_cli_error decorator"""

    @patch('aitbc_cli.utils.error_handling.error')
    @patch('aitbc_cli.utils.error_handling.sys.exit')
    def test_handle_cli_error_success(self, mock_exit, mock_error):
        """Test successful function execution"""
        from aitbc_cli.utils.error_handling import handle_cli_error

        @handle_cli_error
        def test_func():
            return "success"

        result = test_func()

        assert result == "success"
        mock_exit.assert_not_called()

    @patch('aitbc_cli.utils.error_handling.error')
    @patch('aitbc_cli.utils.error_handling.sys.exit')
    def test_handle_cli_error_cli_error(self, mock_exit, mock_error):
        """Test handling CLIError"""
        from aitbc_cli.utils.error_handling import CLIError, handle_cli_error

        @handle_cli_error
        def test_func():
            raise CLIError("Test error", exit_code=5)

        test_func()

        mock_error.assert_called_once()
        mock_exit.assert_called_once_with(5)

    @patch('aitbc_cli.utils.error_handling.warning')
    @patch('aitbc_cli.utils.error_handling.sys.exit')
    def test_handle_cli_error_keyboard_interrupt(self, mock_exit, mock_warning):
        """Test handling KeyboardInterrupt"""
        from aitbc_cli.utils.error_handling import handle_cli_error

        @handle_cli_error
        def test_func():
            raise KeyboardInterrupt()

        test_func()

        mock_warning.assert_called_once()
        mock_exit.assert_called_once_with(130)

    @patch('aitbc_cli.utils.error_handling.error')
    @patch('aitbc_cli.utils.error_handling.sys.exit')
    def test_handle_cli_error_generic_exception(self, mock_exit, mock_error):
        """Test handling generic exception"""
        from aitbc_cli.utils.error_handling import handle_cli_error

        @handle_cli_error
        def test_func():
            raise ValueError("Generic error")

        test_func()

        mock_error.assert_called_once()
        mock_exit.assert_called_once_with(1)


class TestSafeExecute:
    """Test safe_execute function"""

    @patch('aitbc_cli.utils.error_handling.error')
    def test_safe_execute_success(self, mock_error):
        """Test successful operation execution"""
        from aitbc_cli.utils.error_handling import safe_execute

        def operation():
            return "success"

        result = safe_execute(operation)

        assert result == "success"
        mock_error.assert_not_called()

    @patch('aitbc_cli.utils.error_handling.error')
    def test_safe_execute_error_with_default(self, mock_error):
        """Test operation error with default return"""
        from aitbc_cli.utils.error_handling import safe_execute

        def operation():
            raise ValueError("Error")

        result = safe_execute(operation, default_return="default")

        assert result == "default"
        mock_error.assert_called_once()

    @patch('aitbc_cli.utils.error_handling.error')
    def test_safe_execute_error_with_custom_message(self, mock_error):
        """Test operation error with custom message"""
        from aitbc_cli.utils.error_handling import safe_execute

        def operation():
            raise ValueError("Error")

        safe_execute(operation, error_message="Custom error")

        mock_error.assert_called_once()
        call_args = mock_error.call_args[0][0]
        assert "Custom error" in call_args

    def test_safe_execute_error_with_raise(self):
        """Test operation error with raise_on_error"""
        from aitbc_cli.utils.error_handling import safe_execute

        def operation():
            raise ValueError("Error")

        with pytest.raises(ValueError):
            safe_execute(operation, raise_on_error=True)


class TestValidateRequiredFields:
    """Test validate_required_fields function"""

    def test_validate_required_fields_success(self):
        """Test validation with all required fields present"""
        from aitbc_cli.utils.error_handling import validate_required_fields

        data = {"field1": "value1", "field2": "value2"}
        required = ["field1", "field2"]

        # Should not raise
        validate_required_fields(data, required)

    def test_validate_required_fields_missing(self):
        """Test validation with missing required fields"""
        from aitbc_cli.utils.error_handling import ValidationError, validate_required_fields

        data = {"field1": "value1"}
        required = ["field1", "field2"]

        with pytest.raises(ValidationError, match="Missing required fields"):
            validate_required_fields(data, required)

    def test_validate_required_fields_none_value(self):
        """Test validation with None value for required field"""
        from aitbc_cli.utils.error_handling import ValidationError, validate_required_fields

        data = {"field1": "value1", "field2": None}
        required = ["field1", "field2"]

        with pytest.raises(ValidationError, match="Missing required fields"):
            validate_required_fields(data, required)


class TestValidateURL:
    """Test validate_url function"""

    def test_validate_url_valid_http(self):
        """Test validating valid HTTP URL"""
        from aitbc_cli.utils.error_handling import validate_url

        assert validate_url("http://example.com") is True

    def test_validate_url_valid_https(self):
        """Test validating valid HTTPS URL"""
        from aitbc_cli.utils.error_handling import validate_url

        assert validate_url("https://example.com") is True

    def test_validate_url_valid_localhost(self):
        """Test validating localhost URL"""
        from aitbc_cli.utils.error_handling import validate_url

        assert validate_url("http://localhost:8000") is True

    def test_validate_url_valid_ip(self):
        """Test validating IP address URL"""
        from aitbc_cli.utils.error_handling import validate_url

        assert validate_url("http://192.168.1.1:8000") is True

    def test_validate_url_invalid_no_protocol(self):
        """Test validating URL without protocol"""
        from aitbc_cli.utils.error_handling import validate_url

        assert validate_url("example.com") is False

    def test_validate_url_invalid_protocol(self):
        """Test validating URL with invalid protocol"""
        from aitbc_cli.utils.error_handling import validate_url

        assert validate_url("ftp://example.com") is False

    def test_validate_url_invalid_format(self):
        """Test validating invalid URL format"""
        from aitbc_cli.utils.error_handling import validate_url

        assert validate_url("not a url") is False


class TestValidateAddress:
    """Test validate_address function"""

    def test_validate_address_valid(self):
        """Test validating valid Ethereum address"""
        from aitbc_cli.utils.error_handling import validate_address

        assert validate_address("0x1234567890abcdef1234567890abcdef12345678") is True

    def test_validate_address_valid_uppercase(self):
        """Test validating valid Ethereum address with uppercase"""
        from aitbc_cli.utils.error_handling import validate_address

        assert validate_address("0x1234567890ABCDEF1234567890ABCDEF12345678") is True

    def test_validate_address_invalid_no_prefix(self):
        """Test validating address without 0x prefix"""
        from aitbc_cli.utils.error_handling import validate_address

        assert validate_address("1234567890abcdef1234567890abcdef12345678") is False

    def test_validate_address_invalid_too_short(self):
        """Test validating address that's too short"""
        from aitbc_cli.utils.error_handling import validate_address

        assert validate_address("0x1234567890abcdef") is False

    def test_validate_address_invalid_too_long(self):
        """Test validating address that's too long"""
        from aitbc_cli.utils.error_handling import validate_address

        assert validate_address("0x1234567890abcdef1234567890abcdef1234567890") is False

    def test_validate_address_invalid_chars(self):
        """Test validating address with invalid characters"""
        from aitbc_cli.utils.error_handling import validate_address

        assert validate_address("0x1234567890ghijkl1234567890ghijkl12345678") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
