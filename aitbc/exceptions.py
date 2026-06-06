"""
AITBC Exception Hierarchy
Base exception classes for AITBC applications
"""


class AITBCError(Exception):
    """Base exception for all AITBC errors"""
    pass


class ConfigurationError(AITBCError):
    """Raised when configuration is invalid or missing"""
    pass


class NetworkError(AITBCError):
    """Raised when network operations fail"""
    pass


class AuthenticationError(AITBCError):
    """Raised when authentication fails"""
    pass


class EncryptionError(AITBCError):
    """Raised when encryption or decryption fails"""
    pass


class DatabaseError(AITBCError):
    """Raised when database operations fail"""
    pass


class ValidationError(AITBCError):
    """Raised when input validation fails"""
    pass


class BridgeError(AITBCError):
    """Base exception for bridge errors"""
    pass


class RetryError(AITBCError):
    """Raised when retry attempts are exhausted"""
    pass


class CircuitBreakerOpenError(AITBCError):
    """Raised when circuit breaker is open and requests are rejected"""
    pass


class RateLimitError(AITBCError):
    """Raised when rate limit is exceeded"""
    pass
