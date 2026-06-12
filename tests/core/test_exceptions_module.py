"""
Tests for AITBC exceptions module (exceptions.py)
This module has 0% coverage and 60 statements.
"""

import importlib.util
from pathlib import Path

import pytest


# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

exceptions = load_module_from_path(
    "aitbc.exceptions",
    Path("/opt/aitbc/aitbc/exceptions.py")
)


# ============================================================================
# Exception Class Tests
# ============================================================================

class TestAITBCError:
    """Test AITBCError base exception"""

    def test_aitbc_error_basic(self):
        with pytest.raises(exceptions.AITBCError):
            raise exceptions.AITBCError("Test error")

    def test_aitbc_error_with_message(self):
        try:
            raise exceptions.AITBCError("Custom error message")
        except exceptions.AITBCError as e:
            assert str(e) == "Custom error message"

    def test_aitbc_error_inheritance(self):
        assert issubclass(exceptions.AITBCError, Exception)


class TestConfigurationError:
    """Test ConfigurationError exception"""

    def test_configuration_error_basic(self):
        with pytest.raises(exceptions.ConfigurationError):
            raise exceptions.ConfigurationError("Config error")

    def test_configuration_error_inheritance(self):
        assert issubclass(exceptions.ConfigurationError, exceptions.AITBCError)


class TestNetworkError:
    """Test NetworkError exception"""

    def test_network_error_basic(self):
        with pytest.raises(exceptions.NetworkError):
            raise exceptions.NetworkError("Network failed")

    def test_network_error_inheritance(self):
        assert issubclass(exceptions.NetworkError, exceptions.AITBCError)


class TestAuthenticationError:
    """Test AuthenticationError exception"""

    def test_authentication_error_basic(self):
        with pytest.raises(exceptions.AuthenticationError):
            raise exceptions.AuthenticationError("Auth failed")

    def test_authentication_error_inheritance(self):
        assert issubclass(exceptions.AuthenticationError, exceptions.AITBCError)


class TestEncryptionError:
    """Test EncryptionError exception"""

    def test_encryption_error_basic(self):
        with pytest.raises(exceptions.EncryptionError):
            raise exceptions.EncryptionError("Encryption failed")

    def test_encryption_error_inheritance(self):
        assert issubclass(exceptions.EncryptionError, exceptions.AITBCError)


class TestDatabaseError:
    """Test DatabaseError exception"""

    def test_database_error_basic(self):
        with pytest.raises(exceptions.DatabaseError):
            raise exceptions.DatabaseError("Database failed")

    def test_database_error_inheritance(self):
        assert issubclass(exceptions.DatabaseError, exceptions.AITBCError)


class TestValidationError:
    """Test ValidationError exception"""

    def test_validation_error_basic(self):
        with pytest.raises(exceptions.ValidationError):
            raise exceptions.ValidationError("Validation failed")

    def test_validation_error_inheritance(self):
        assert issubclass(exceptions.ValidationError, exceptions.AITBCError)


class TestBridgeError:
    """Test BridgeError exception"""

    def test_bridge_error_basic(self):
        with pytest.raises(exceptions.BridgeError):
            raise exceptions.BridgeError("Bridge failed")

    def test_bridge_error_inheritance(self):
        assert issubclass(exceptions.BridgeError, exceptions.AITBCError)


class TestRetryError:
    """Test RetryError exception"""

    def test_retry_error_basic(self):
        with pytest.raises(exceptions.RetryError):
            raise exceptions.RetryError("Retry failed")

    def test_retry_error_inheritance(self):
        assert issubclass(exceptions.RetryError, exceptions.AITBCError)


class TestCircuitBreakerOpenError:
    """Test CircuitBreakerOpenError exception"""

    def test_circuit_breaker_open_error_basic(self):
        with pytest.raises(exceptions.CircuitBreakerOpenError):
            raise exceptions.CircuitBreakerOpenError("Circuit breaker open")

    def test_circuit_breaker_open_error_inheritance(self):
        assert issubclass(exceptions.CircuitBreakerOpenError, exceptions.AITBCError)


class TestRateLimitError:
    """Test RateLimitError exception"""

    def test_rate_limit_error_basic(self):
        with pytest.raises(exceptions.RateLimitError):
            raise exceptions.RateLimitError("Rate limit exceeded")

    def test_rate_limit_error_inheritance(self):
        assert issubclass(exceptions.RateLimitError, exceptions.AITBCError)


# ============================================================================
# Exception Hierarchy Tests
# ============================================================================

class TestExceptionHierarchy:
    """Test exception hierarchy relationships"""

    def test_all_exceptions_inherit_from_aitbc_error(self):
        exception_classes = [
            exceptions.ConfigurationError,
            exceptions.NetworkError,
            exceptions.AuthenticationError,
            exceptions.EncryptionError,
            exceptions.DatabaseError,
            exceptions.ValidationError,
            exceptions.BridgeError,
            exceptions.RetryError,
            exceptions.CircuitBreakerOpenError,
            exceptions.RateLimitError
        ]

        for exc_class in exception_classes:
            assert issubclass(exc_class, exceptions.AITBCError)

    def test_catch_base_exception(self):
        """Test that base exception catches all derived exceptions"""
        try:
            raise exceptions.NetworkError("test")
        except exceptions.AITBCError:
            pass  # Should catch NetworkError

    def test_specific_exception_catch(self):
        """Test that specific exceptions don't catch others"""
        with pytest.raises(exceptions.DatabaseError):
            try:
                raise exceptions.DatabaseError("test")
            except exceptions.NetworkError:
                pass  # Should not catch DatabaseError
