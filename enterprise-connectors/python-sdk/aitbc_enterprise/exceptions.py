"""
Exception classes for AITBC Enterprise Connectors
"""


class AITBCError(Exception):
    """Base exception for all AITBC errors"""
    pass


class AuthenticationError(AITBCError):
    """Raised when authentication fails"""
    pass


class RateLimitError(AITBCError):
    """Raised when rate limit is exceeded"""
    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class APIError(AITBCError):
    """Raised when API request fails"""
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class ConfigurationError(AITBCError):
    """Raised when configuration is invalid"""
    pass


class ConnectorError(AITBCError):
    """Raised when connector operation fails"""
    pass


class PaymentError(ConnectorError):
    """Raised when payment operation fails"""
    pass


class ValidationError(AITBCError):
    """Raised when data validation fails"""
    pass


class WebhookError(AITBCError):
    """Raised when webhook processing fails"""
    pass


class ERPError(ConnectorError):
    """Raised when ERP operation fails"""
    pass


class SyncError(ConnectorError):
    """Raised when synchronization fails"""
    pass


class TimeoutError(AITBCError):
    """Raised when operation times out"""
    pass
