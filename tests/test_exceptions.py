"""
Exceptions Tests
Tests for AITBC exception hierarchy
"""

import pytest

from aitbc.exceptions import (
    AITBCError,
    AuthenticationError,
    BridgeError,
    CircuitBreakerOpenError,
    ConfigurationError,
    DatabaseError,
    EncryptionError,
    NetworkError,
    RateLimitError,
    RetryError,
    ValidationError,
)


class TestAITBCError:
    """Test AITBCError base exception"""

    def test_aitbc_error_can_be_raised(self):
        """Test AITBCError can be raised"""
        with pytest.raises(AITBCError):
            raise AITBCError("Test error")

    def test_aitbc_error_message(self):
        """Test AITBCError stores message"""
        error = AITBCError("Test message")
        assert str(error) == "Test message"


class TestConfigurationError:
    """Test ConfigurationError"""

    def test_configuration_error_inherits_from_aitbc_error(self):
        """Test ConfigurationError inherits from AITBCError"""
        assert issubclass(ConfigurationError, AITBCError)

    def test_configuration_error_can_be_raised(self):
        """Test ConfigurationError can be raised"""
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("Config error")


class TestNetworkError:
    """Test NetworkError"""

    def test_network_error_inherits_from_aitbc_error(self):
        """Test NetworkError inherits from AITBCError"""
        assert issubclass(NetworkError, AITBCError)

    def test_network_error_can_be_raised(self):
        """Test NetworkError can be raised"""
        with pytest.raises(NetworkError):
            raise NetworkError("Network error")


class TestAuthenticationError:
    """Test AuthenticationError"""

    def test_authentication_error_inherits_from_aitbc_error(self):
        """Test AuthenticationError inherits from AITBCError"""
        assert issubclass(AuthenticationError, AITBCError)

    def test_authentication_error_can_be_raised(self):
        """Test AuthenticationError can be raised"""
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("Auth error")


class TestEncryptionError:
    """Test EncryptionError"""

    def test_encryption_error_inherits_from_aitbc_error(self):
        """Test EncryptionError inherits from AITBCError"""
        assert issubclass(EncryptionError, AITBCError)

    def test_encryption_error_can_be_raised(self):
        """Test EncryptionError can be raised"""
        with pytest.raises(EncryptionError):
            raise EncryptionError("Encryption error")


class TestDatabaseError:
    """Test DatabaseError"""

    def test_database_error_inherits_from_aitbc_error(self):
        """Test DatabaseError inherits from AITBCError"""
        assert issubclass(DatabaseError, AITBCError)

    def test_database_error_can_be_raised(self):
        """Test DatabaseError can be raised"""
        with pytest.raises(DatabaseError):
            raise DatabaseError("Database error")


class TestValidationError:
    """Test ValidationError"""

    def test_validation_error_inherits_from_aitbc_error(self):
        """Test ValidationError inherits from AITBCError"""
        assert issubclass(ValidationError, AITBCError)

    def test_validation_error_can_be_raised(self):
        """Test ValidationError can be raised"""
        with pytest.raises(ValidationError):
            raise ValidationError("Validation error")


class TestBridgeError:
    """Test BridgeError"""

    def test_bridge_error_inherits_from_aitbc_error(self):
        """Test BridgeError inherits from AITBCError"""
        assert issubclass(BridgeError, AITBCError)

    def test_bridge_error_can_be_raised(self):
        """Test BridgeError can be raised"""
        with pytest.raises(BridgeError):
            raise BridgeError("Bridge error")


class TestRetryError:
    """Test RetryError"""

    def test_retry_error_inherits_from_aitbc_error(self):
        """Test RetryError inherits from AITBCError"""
        assert issubclass(RetryError, AITBCError)

    def test_retry_error_can_be_raised(self):
        """Test RetryError can be raised"""
        with pytest.raises(RetryError):
            raise RetryError("Retry error")


class TestCircuitBreakerOpenError:
    """Test CircuitBreakerOpenError"""

    def test_circuit_breaker_open_error_inherits_from_aitbc_error(self):
        """Test CircuitBreakerOpenError inherits from AITBCError"""
        assert issubclass(CircuitBreakerOpenError, AITBCError)

    def test_circuit_breaker_open_error_can_be_raised(self):
        """Test CircuitBreakerOpenError can be raised"""
        with pytest.raises(CircuitBreakerOpenError):
            raise CircuitBreakerOpenError("Circuit breaker open")


class TestRateLimitError:
    """Test RateLimitError"""

    def test_rate_limit_error_inherits_from_aitbc_error(self):
        """Test RateLimitError inherits from AITBCError"""
        assert issubclass(RateLimitError, AITBCError)

    def test_rate_limit_error_can_be_raised(self):
        """Test RateLimitError can be raised"""
        with pytest.raises(RateLimitError):
            raise RateLimitError("Rate limit exceeded")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
