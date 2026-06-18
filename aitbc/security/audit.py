"""
Security audit logging for sensitive operations
"""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class SecurityAuditLog:
    """Security audit log entry"""

    timestamp: datetime
    action: str
    user: str | None
    ip_address: str | None
    details: dict[str, Any]
    severity: str = "INFO"


class SecurityAuditor:
    """
    Security auditor for logging sensitive operations.
    Provides audit logging for security-relevant events.
    """

    def __init__(self, log_file: Path | None = None):
        """
        Initialize security auditor

        Args:
            log_file: Path to audit log file (optional)
        """
        self.log_file = log_file
        self.audit_logs: list[SecurityAuditLog] = []

    def log_event(
        self,
        action: str,
        user: str | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
        severity: str = "INFO",
    ) -> None:
        """
        Log a security event

        Args:
            action: Action being performed
            user: User performing the action
            ip_address: IP address of the user
            details: Additional details about the event
            severity: Severity level (INFO, WARNING, ERROR, CRITICAL)
        """
        log_entry = SecurityAuditLog(
            timestamp=datetime.now(UTC),
            action=action,
            user=user,
            ip_address=ip_address,
            details=details or {},
            severity=severity,
        )

        self.audit_logs.append(log_entry)

        # Log to file if configured
        if self.log_file:
            self._write_to_file(log_entry)

        # Log to application logger
        logger.info(
            "Security Audit: %s - User: %s - IP: %s - Severity: %s - Details: %s",
            action,
            user,
            ip_address,
            severity,
            json.dumps(details),
        )

    def _write_to_file(self, log_entry: SecurityAuditLog) -> None:
        """
        Write audit log entry to file

        Args:
            log_entry: Audit log entry to write
        """
        if not self.log_file:
            return

        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a") as f:
                f.write(json.dumps(asdict(log_entry), default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write audit log to file: %s", e)

    def get_recent_logs(self, hours: int = 24) -> list[SecurityAuditLog]:
        """
        Get audit logs from the last N hours

        Args:
            hours: Number of hours to look back

        Returns:
            List of recent audit log entries
        """
        cutoff_time = datetime.now(UTC) - timedelta(hours=hours)
        return [log for log in self.audit_logs if log.timestamp >= cutoff_time]

    def get_logs_by_user(self, user: str) -> list[SecurityAuditLog]:
        """
        Get all audit logs for a specific user

        Args:
            user: User to filter by

        Returns:
            List of audit log entries for the user
        """
        return [log for log in self.audit_logs if log.user == user]

    def get_logs_by_action(self, action: str) -> list[SecurityAuditLog]:
        """
        Get all audit logs for a specific action

        Args:
            action: Action to filter by

        Returns:
            List of audit log entries for the action
        """
        return [log for log in self.audit_logs if log.action == action]

    def get_logs_by_severity(self, severity: str) -> list[SecurityAuditLog]:
        """
        Get all audit logs for a specific severity level

        Args:
            severity: Severity level to filter by

        Returns:
            List of audit log entries for the severity level
        """
        return [log for log in self.audit_logs if log.severity == severity]

    def clear_old_logs(self, days: int = 30) -> int:
        """
        Clear audit logs older than N days

        Args:
            days: Number of days to keep logs

        Returns:
            Number of logs cleared
        """
        cutoff_time = datetime.now(UTC) - timedelta(days=days)
        original_count = len(self.audit_logs)
        self.audit_logs = [log for log in self.audit_logs if log.timestamp >= cutoff_time]
        return original_count - len(self.audit_logs)

    def get_statistics(self) -> dict[str, Any]:
        """
        Get audit log statistics

        Returns:
            Dictionary with audit log statistics
        """
        if not self.audit_logs:
            return {
                "total_logs": 0,
                "unique_users": 0,
                "unique_actions": 0,
                "severity_breakdown": {},
            }

        unique_users = set(log.user for log in self.audit_logs if log.user)
        unique_actions = set(log.action for log in self.audit_logs)
        severity_breakdown: dict[str, int] = {}

        for log in self.audit_logs:
            severity_breakdown[log.severity] = severity_breakdown.get(log.severity, 0) + 1

        return {
            "total_logs": len(self.audit_logs),
            "unique_users": len(unique_users),
            "unique_actions": len(unique_actions),
            "severity_breakdown": severity_breakdown,
        }
