"""
Exception classes and error response schemas for AITBC coordinator

Provides structured error responses for consistent API error handling.
"""

from datetime import datetime
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error information."""
    field: Optional[str] = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code for programmatic handling")


class ErrorResponse(BaseModel):
    """Standardized error response for all API errors."""
    error: Dict[str, Any] = Field(..., description="Error information")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid input data",
                    "status": 422,
                    "details": [
                        {"field": "email", "message": "Invalid email format", "code": "invalid_format"}
                    ]
                },
                "timestamp": "2026-02-13T21:00:00Z",
                "request_id": "req_abc123"
            }
        }


class AITBCError(Exception):
    """Base exception for all AITBC errors"""
    error_code: str = "INTERNAL_ERROR"
    status_code: int = 500
    
    def to_response(self, request_id: Optional[str] = None) -> ErrorResponse:
        """Convert exception to standardized error response."""
        return ErrorResponse(
            error={
                "code": self.error_code,
                "message": str(self),
                "status": self.status_code,
                "details": []
            },
            request_id=request_id
        )


class AuthenticationError(AITBCError):
    """Raised when authentication fails"""
    error_code: str = "AUTHENTICATION_ERROR"
    status_code: int = 401
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class AuthorizationError(AITBCError):
    """Raised when authorization fails"""
    error_code: str = "AUTHORIZATION_ERROR"
    status_code: int = 403
    
    def __init__(self, message: str = "Not authorized to perform this action"):
        super().__init__(message)


class RateLimitError(AITBCError):
    """Raised when rate limit is exceeded"""
    error_code: str = "RATE_LIMIT_EXCEEDED"
    status_code: int = 429
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after
    
    def to_response(self, request_id: Optional[str] = None) -> ErrorResponse:
        return ErrorResponse(
            error={
                "code": self.error_code,
                "message": str(self),
                "status": self.status_code,
                "details": [{"retry_after": self.retry_after}]
            },
            request_id=request_id
        )


class APIError(AITBCError):
    """Raised when API request fails"""
    error_code: str = "API_ERROR"
    status_code: int = 500
    
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code or self.status_code
        self.response = response


class ConfigurationError(AITBCError):
    """Raised when configuration is invalid"""
    error_code: str = "CONFIGURATION_ERROR"
    status_code: int = 500
    
    def __init__(self, message: str = "Invalid configuration"):
        super().__init__(message)


class ConnectorError(AITBCError):
    """Raised when connector operation fails"""
    error_code: str = "CONNECTOR_ERROR"
    status_code: int = 502
    
    def __init__(self, message: str = "Connector operation failed"):
        super().__init__(message)


class PaymentError(ConnectorError):
    """Raised when payment operation fails"""
    error_code: str = "PAYMENT_ERROR"
    status_code: int = 402
    
    def __init__(self, message: str = "Payment operation failed"):
        super().__init__(message)


class ValidationError(AITBCError):
    """Raised when data validation fails"""
    error_code: str = "VALIDATION_ERROR"
    status_code: int = 422
    
    def __init__(self, message: str = "Validation failed", details: List[ErrorDetail] = None):
        super().__init__(message)
        self.details = details or []
    
    def to_response(self, request_id: Optional[str] = None) -> ErrorResponse:
        return ErrorResponse(
            error={
                "code": self.error_code,
                "message": str(self),
                "status": self.status_code,
                "details": [{"field": d.field, "message": d.message, "code": d.code} for d in self.details]
            },
            request_id=request_id
        )


class WebhookError(AITBCError):
    """Raised when webhook processing fails"""
    error_code: str = "WEBHOOK_ERROR"
    status_code: int = 500
    
    def __init__(self, message: str = "Webhook processing failed"):
        super().__init__(message)


class ERPError(ConnectorError):
    """Raised when ERP operation fails"""
    error_code: str = "ERP_ERROR"
    status_code: int = 502
    
    def __init__(self, message: str = "ERP operation failed"):
        super().__init__(message)


class SyncError(ConnectorError):
    """Raised when synchronization fails"""
    error_code: str = "SYNC_ERROR"
    status_code: int = 500
    
    def __init__(self, message: str = "Synchronization failed"):
        super().__init__(message)


class TimeoutError(AITBCError):
    """Raised when operation times out"""
    error_code: str = "TIMEOUT_ERROR"
    status_code: int = 504
    
    def __init__(self, message: str = "Operation timed out"):
        super().__init__(message)


class TenantError(ConnectorError):
    """Raised when tenant operation fails"""
    error_code: str = "TENANT_ERROR"
    status_code: int = 400
    
    def __init__(self, message: str = "Tenant operation failed"):
        super().__init__(message)


class QuotaExceededError(ConnectorError):
    """Raised when resource quota is exceeded"""
    error_code: str = "QUOTA_EXCEEDED"
    status_code: int = 429
    
    def __init__(self, message: str = "Quota exceeded", limit: int = None):
        super().__init__(message)
        self.limit = limit
    
    def to_response(self, request_id: Optional[str] = None) -> ErrorResponse:
        details = [{"limit": self.limit}] if self.limit else []
        return ErrorResponse(
            error={
                "code": self.error_code,
                "message": str(self),
                "status": self.status_code,
                "details": details
            },
            request_id=request_id
        )


class BillingError(ConnectorError):
    """Raised when billing operation fails"""
    error_code: str = "BILLING_ERROR"
    status_code: int = 402
    
    def __init__(self, message: str = "Billing operation failed"):
        super().__init__(message)


class NotFoundError(AITBCError):
    """Raised when a resource is not found"""
    error_code: str = "NOT_FOUND"
    status_code: int = 404
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class ConflictError(AITBCError):
    """Raised when there's a conflict (e.g., duplicate resource)"""
    error_code: str = "CONFLICT"
    status_code: int = 409
    
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message)
