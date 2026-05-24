"""
Security protocols for agent operations.
These protocols define the interface for security management and auditing.
"""

from abc import ABC, abstractmethod
from typing import Any


class ISecurityManager(ABC):
    """Protocol for agent security management"""
    
    @abstractmethod
    async def validate_operation(
        self,
        operation: str,
        context: dict[str, Any]
    ) -> bool:
        """
        Validate if an operation is authorized.
        
        Args:
            operation: The operation being performed
            context: Additional context for validation
            
        Returns:
            True if operation is authorized, False otherwise
        """
        ...
    
    @abstractmethod
    async def audit_event(
        self,
        event_type: str,
        details: dict[str, Any]
    ) -> None:
        """
        Log an audit event for security tracking.
        
        Args:
            event_type: Type of audit event
            details: Event details to log
        """
        ...


class IAuditor(ABC):
    """Protocol for agent auditing"""
    
    @abstractmethod
    async def log_audit(
        self,
        event_type: str,
        details: dict[str, Any]
    ) -> None:
        """
        Log an audit event.
        
        Args:
            event_type: Type of audit event
            details: Event details to log
        """
        ...
