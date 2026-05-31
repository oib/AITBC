"""
Security utilities for AITBC
Provides security hardening features including input validation, sanitization, and audit logging
"""

import html
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .aitbc_logging import get_logger

logger = get_logger(__name__)


class SecurityValidator:
    """
    Security validator for input validation and sanitization.
    Provides methods to validate and sanitize user inputs.
    """

    # Patterns for validation
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    URL_PATTERN = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    ETHEREUM_ADDRESS_PATTERN = re.compile(r'^0x[a-fA-F0-9]{40}$')
    TX_HASH_PATTERN = re.compile(r'^0x[a-fA-F0-9]{64}$')

    @staticmethod
    def validate_email(email: str) -> bool:
        """
        Validate email address format
        
        Args:
            email: Email address to validate
            
        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.EMAIL_PATTERN.match(email))

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL format
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.URL_PATTERN.match(url))

    @staticmethod
    def validate_ethereum_address(address: str) -> bool:
        """
        Validate Ethereum address format
        
        Args:
            address: Ethereum address to validate
            
        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.ETHEREUM_ADDRESS_PATTERN.match(address))

    @staticmethod
    def validate_tx_hash(tx_hash: str) -> bool:
        """
        Validate transaction hash format
        
        Args:
            tx_hash: Transaction hash to validate
            
        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.TX_HASH_PATTERN.match(tx_hash))

    @staticmethod
    def sanitize_html(html_content: str) -> str:
        """
        Sanitize HTML content to prevent XSS attacks
        
        Args:
            html_content: HTML content to sanitize
            
        Returns:
            Sanitized HTML content
        """
        return html.escape(html_content)

    @staticmethod
    def sanitize_json_string(json_string: str) -> str:
        """
        Sanitize JSON string to prevent injection attacks
        
        Args:
            json_string: JSON string to sanitize
            
        Returns:
            Sanitized JSON string
        """
        # Remove potentially dangerous characters
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_string)
        return sanitized

    @staticmethod
    def validate_json_structure(data: Any, required_fields: list[str]) -> bool:
        """
        Validate JSON structure has required fields
        
        Args:
            data: Data to validate
            required_fields: List of required field names
            
        Returns:
            True if valid, False otherwise
        """
        if not isinstance(data, dict):
            return False

        return all(field in data for field in required_fields)

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename to prevent path traversal attacks
        
        Args:
            filename: Filename to sanitize
            
        Returns:
            Sanitized filename
        """
        # Remove path separators and dangerous characters
        sanitized = re.sub(r'[\\/\0]', '', filename)
        # Remove control characters
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
        return sanitized


@dataclass
class SecurityAuditLog:
    """Security audit log entry"""
    timestamp: datetime
    action: str
    user: str | None
    ip_address: str | None
    details: dict[str, Any]
    severity: str = "INFO"  # INFO, WARNING, ERROR, CRITICAL


class SecurityAuditor:
    """
    Security auditor for logging sensitive operations.
    Provides audit logging for security-relevant events.
    """

    def __init__(self, log_file: Path | None = None):
        """
        Initialize security auditor
        
        Args:
            log_file: Path to audit log file
        """
        self.log_file = log_file
        self._logs: list[SecurityAuditLog] = []

    def log_security_event(
        self,
        action: str,
        user: str | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
        severity: str = "INFO"
    ) -> None:
        """
        Log a security event
        
        Args:
            action: Action performed
            user: User who performed the action
            ip_address: IP address of the user
            details: Additional details about the event
            severity: Severity level (INFO, WARNING, ERROR, CRITICAL)
        """
        log_entry = SecurityAuditLog(
            timestamp=datetime.now(),
            action=action,
            user=user,
            ip_address=ip_address,
            details=details or {},
            severity=severity
        )

        self._logs.append(log_entry)

        # Log to file if configured
        if self.log_file:
            self._write_to_file(log_entry)

        # Log to application logger
        logger.info(
            f"Security Event: {action} | User: {user} | IP: {ip_address} | Severity: {severity}"
        )

    def _write_to_file(self, log_entry: SecurityAuditLog) -> None:
        """
        Write log entry to file
        
        Args:
            log_entry: Log entry to write
        """
        if not self.log_file:
            return

        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.log_file, 'a') as f:
            f.write(json.dumps(asdict(log_entry), default=str) + '\n')

    def get_logs(
        self,
        action: str | None = None,
        user: str | None = None,
        severity: str | None = None,
        limit: int = 100
    ) -> list[SecurityAuditLog]:
        """
        Get filtered audit logs
        
        Args:
            action: Filter by action
            user: Filter by user
            severity: Filter by severity
            limit: Maximum number of logs to return
            
        Returns:
            List of matching audit logs
        """
        filtered_logs = self._logs

        if action:
            filtered_logs = [log for log in filtered_logs if log.action == action]

        if user:
            filtered_logs = [log for log in filtered_logs if log.user == user]

        if severity:
            filtered_logs = [log for log in filtered_logs if log.severity == severity]

        return filtered_logs[-limit:]

    def get_critical_logs(self, limit: int = 50) -> list[SecurityAuditLog]:
        """
        Get only critical security logs
        
        Args:
            limit: Maximum number of logs to return
            
        Returns:
            List of critical audit logs
        """
        critical_logs = [log for log in self._logs if log.severity == "CRITICAL"]
        return critical_logs[-limit:]


class RateLimiter:
    """
    Rate limiter for API endpoints.
    Implements token bucket algorithm for rate limiting.
    """

    def __init__(self, rate: int, per: int = 60):
        """
        Initialize rate limiter
        
        Args:
            rate: Number of requests allowed
            per: Time period in seconds
        """
        self.rate = rate
        self.per = per
        self._requests: dict[str, list[datetime]] = {}

    def is_allowed(self, identifier: str) -> bool:
        """
        Check if request is allowed for identifier
        
        Args:
            identifier: Unique identifier (IP address, user ID, etc.)
            
        Returns:
            True if request is allowed, False otherwise
        """
        now = datetime.now()

        # Get or create request list for identifier
        if identifier not in self._requests:
            self._requests[identifier] = []

        # Remove old requests outside time window
        cutoff_time = now - timedelta(seconds=self.per)
        self._requests[identifier] = [
            req_time for req_time in self._requests[identifier]
            if req_time > cutoff_time
        ]

        # Check if rate limit exceeded
        if len(self._requests[identifier]) >= self.rate:
            logger.warning(f"Rate limit exceeded for {identifier}")
            return False

        # Add current request
        self._requests[identifier].append(now)
        return True

    def reset(self, identifier: str) -> None:
        """
        Reset rate limit for identifier
        
        Args:
            identifier: Unique identifier to reset
        """
        if identifier in self._requests:
            del self._requests[identifier]
            logger.info(f"Rate limit reset for {identifier}")

    def get_remaining_requests(self, identifier: str) -> int:
        """
        Get remaining requests for identifier
        
        Args:
            identifier: Unique identifier
            
        Returns:
            Number of remaining requests
        """
        if identifier not in self._requests:
            return self.rate

        now = datetime.now()
        cutoff_time = now - timedelta(seconds=self.per)
        recent_requests = [
            req_time for req_time in self._requests[identifier]
            if req_time > cutoff_time
        ]

        return max(0, self.rate - len(recent_requests))


# Global security auditor instance
_global_security_auditor = SecurityAuditor()


def log_security_event(
    action: str,
    user: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
    severity: str = "INFO"
) -> None:
    """
    Log a security event using global auditor
    
    Args:
        action: Action performed
        user: User who performed the action
        ip_address: IP address of the user
        details: Additional details about the event
        severity: Severity level
    """
    _global_security_auditor.log_security_event(
        action, user, ip_address, details, severity
    )


def get_security_auditor() -> SecurityAuditor:
    """
    Get the global security auditor instance
    
    Returns:
        Global SecurityAuditor instance
    """
    return _global_security_auditor
