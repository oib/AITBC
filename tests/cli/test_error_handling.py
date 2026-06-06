"""
Tests for CLI error handling utilities
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest
from aitbc_cli.utils.error_handling import (
    CLIError,
    NetworkError,
    ConfigurationError,
    ValidationError,
    APIError,
    handle_cli_error,
    handle_async_cli_error,
    safe_execute,
    validate_required_fields,
    validate_url,
    validate_address,
)


class TestCLIError:
    """Test base CLI error class"""

    def test_cli_error_creation(self):
        """Test creating a basic CLI error"""
        error = CLIError("Test error message")
        assert error.message == "Test error message"
        assert error.exit_code == 1

    def test_cli_error_custom_exit_code(self):
        """Test CLI error with custom exit code"""
        error = CLIError("Test error", exit_code=42)
        assert error.exit_code == 42


class TestNetworkError:
    """Test network error class"""

    def test_network_error_creation(self):
        """Test creating a network error"""
        error = NetworkError("Connection failed")
        assert "Network error" in error.message
        assert "Connection failed" in error.message
        assert error.exit_code == 2


class TestConfigurationError:
    """Test configuration error class"""

    def test_configuration_error_creation(self):
        """Test creating a configuration error"""
        error = ConfigurationError("Missing config file")
        assert "Configuration error" in error.message
        assert "Missing config file" in error.message
        assert error.exit_code == 3


class TestValidationError:
    """Test validation error class"""

    def test_validation_error_creation(self):
        """Test creating a validation error"""
        error = ValidationError("Invalid input")
        assert "Validation error" in error.message
        assert "Invalid input" in error.message
        assert error.exit_code == 4


class TestAPIError:
    """Test API error class"""

    def test_api_error_without_status(self):
        """Test API error without status code"""
        error = APIError("Request failed")
        assert "API error" in error.message
        assert "Request failed" in error.message
        assert error.exit_code == 5

    def test_api_error_with_status(self):
        """Test API error with status code"""
        error = APIError("Request failed", status_code=404)
        assert "HTTP 404" in error.message
        assert error.exit_code == 5


class TestHandleCLIError:
    """Test CLI error handling decorator"""

    def test_handle_cli_error_success(self):
        """Test successful function execution"""
        @handle_cli_error
        def successful_func():
            return "success"
        
        result = successful_func()
        assert result == "success"

    def test_handle_cli_error_cli_error(self):
        """Test handling CLIError"""
        @handle_cli_error
        def failing_func():
            raise CLIError("Test error")
        
        with pytest.raises(SystemExit) as exc_info:
            failing_func()
        assert exc_info.value.code == 1

    def test_handle_cli_error_keyboard_interrupt(self):
        """Test handling KeyboardInterrupt"""
        @handle_cli_error
        def interrupt_func():
            raise KeyboardInterrupt()
        
        with pytest.raises(SystemExit) as exc_info:
            interrupt_func()
        assert exc_info.value.code == 130

    def test_handle_cli_error_generic_exception(self):
        """Test handling generic exception"""
        @handle_cli_error
        def error_func():
            raise ValueError("Generic error")
        
        with pytest.raises(SystemExit) as exc_info:
            error_func()
        assert exc_info.value.code == 1


class TestHandleAsyncCLIError:
    """Test async CLI error handling decorator"""

    @pytest.mark.asyncio
    async def test_handle_async_cli_error_success(self):
        """Test successful async function execution"""
        @handle_async_cli_error
        async def successful_func():
            return "success"
        
        result = await successful_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_handle_async_cli_error_cli_error(self):
        """Test handling CLIError in async"""
        @handle_async_cli_error
        async def failing_func():
            raise CLIError("Test error")
        
        with pytest.raises(SystemExit) as exc_info:
            await failing_func()
        assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_handle_async_cli_error_keyboard_interrupt(self):
        """Test handling KeyboardInterrupt in async"""
        @handle_async_cli_error
        async def interrupt_func():
            raise KeyboardInterrupt()
        
        with pytest.raises(SystemExit) as exc_info:
            await interrupt_func()
        assert exc_info.value.code == 130


class TestSafeExecute:
    """Test safe_execute utility"""

    def test_safe_execute_success(self):
        """Test successful operation"""
        result = safe_execute(lambda: 42)
        assert result == 42

    def test_safe_execute_error_default(self):
        """Test operation returning default on error"""
        result = safe_execute(lambda: 1/0, default_return="error")
        assert result == "error"

    def test_safe_execute_error_raise(self):
        """Test operation raising on error"""
        with pytest.raises(ZeroDivisionError):
            safe_execute(lambda: 1/0, raise_on_error=True)

    def test_safe_execute_custom_error_message(self):
        """Test custom error message"""
        result = safe_execute(lambda: 1/0, error_message="Calculation failed")
        assert result is None


class TestValidateRequiredFields:
    """Test required fields validation"""

    def test_validate_all_fields_present(self):
        """Test validation with all required fields present"""
        data = {"name": "test", "value": 123}
        validate_required_fields(data, ["name", "value"])
        # Should not raise

    def test_validate_missing_field(self):
        """Test validation with missing field"""
        data = {"name": "test"}
        with pytest.raises(ValidationError) as exc_info:
            validate_required_fields(data, ["name", "value"])
        assert "Missing required fields" in str(exc_info.value)

    def test_validate_none_field(self):
        """Test validation with None field"""
        data = {"name": "test", "value": None}
        with pytest.raises(ValidationError) as exc_info:
            validate_required_fields(data, ["name", "value"])
        assert "Missing required fields" in str(exc_info.value)

    def test_validate_empty_required_list(self):
        """Test validation with empty required list"""
        data = {"name": "test"}
        validate_required_fields(data, [])
        # Should not raise


class TestValidateURL:
    """Test URL validation"""

    def test_valid_http_url(self):
        """Test valid HTTP URL"""
        assert validate_url("http://example.com") is True

    def test_valid_https_url(self):
        """Test valid HTTPS URL"""
        assert validate_url("https://example.com") is True

    def test_valid_localhost(self):
        """Test localhost URL"""
        assert validate_url("http://localhost:8000") is True

    def test_valid_ip_address(self):
        """Test IP address URL"""
        assert validate_url("http://192.168.1.1") is True

    def test_invalid_url_no_protocol(self):
        """Test URL without protocol"""
        assert validate_url("example.com") is False

    def test_invalid_url_bad_protocol(self):
        """Test URL with invalid protocol"""
        assert validate_url("ftp://example.com") is False

    def test_invalid_url_empty(self):
        """Test empty URL"""
        assert validate_url("") is False


class TestValidateAddress:
    """Test Ethereum address validation"""

    def test_valid_address_lowercase(self):
        """Test valid lowercase address"""
        assert validate_address("0x1234567890abcdef1234567890abcdef12345678") is True

    def test_valid_address_uppercase(self):
        """Test valid uppercase address"""
        assert validate_address("0x1234567890ABCDEF1234567890ABCDEF12345678") is True

    def test_valid_address_mixed_case(self):
        """Test valid mixed case address"""
        assert validate_address("0x1234567890AbCdEf1234567890AbCdEf12345678") is True

    def test_invalid_address_no_prefix(self):
        """Test address without 0x prefix"""
        assert validate_address("1234567890abcdef1234567890abcdef12345678") is False

    def test_invalid_address_too_short(self):
        """Test address too short"""
        assert validate_address("0x1234567890abcdef") is False

    def test_invalid_address_too_long(self):
        """Test address too long"""
        assert validate_address("0x1234567890abcdef1234567890abcdef1234567890") is False

    def test_invalid_address_non_hex(self):
        """Test address with non-hex characters"""
        assert validate_address("0x1234567890ghijk1234567890ghijk12345678") is False

    def test_invalid_address_empty(self):
        """Test empty address"""
        assert validate_address("") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
