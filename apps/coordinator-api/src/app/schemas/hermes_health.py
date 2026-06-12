"""Schemas for Hermes self-healing and health monitoring."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class HealthStatus(str, Enum):
    """Health status of agents and services."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    RECOVERING = "recovering"


class ErrorSeverity(str, Enum):
    """Severity of errors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorType(str, Enum):
    """Types of errors that can occur."""
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RESOURCE_ERROR = "resource_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    DATABASE_ERROR = "database_error"
    UNKNOWN_ERROR = "unknown_error"


class HealthCheck(BaseModel):
    """Health check result for an agent or service."""
    agent_id: str
    service_name: str
    status: HealthStatus
    timestamp: datetime
    response_time_ms: float
    error_message: str | None = None
    metadata: dict | None = None


class ErrorReport(BaseModel):
    """Error report for self-healing."""
    agent_id: str
    service_name: str
    error_type: ErrorType
    severity: ErrorSeverity
    error_message: str
    timestamp: datetime
    context: dict | None = None


class RecoveryAction(BaseModel):
    """Recovery action to be taken."""
    action_type: str
    description: str
    parameters: dict | None = None


class RecoveryResult(BaseModel):
    """Result of a recovery action."""
    action_id: str
    agent_id: str
    success: bool
    message: str
    timestamp: datetime
