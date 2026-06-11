"""Service for Hermes self-healing and health monitoring."""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)

from ....schemas.hermes_health import (
    ErrorReport,
    ErrorSeverity,
    ErrorType,
    HealthCheck,
    HealthStatus,
    RecoveryAction,
    RecoveryResult,
)


class HealthService:
    """Service for monitoring agent health and executing self-healing actions."""

    def __init__(self):
        # In-memory storage for health checks (replace with database in production)
        self.health_checks: Dict[str, HealthCheck] = {}
        self.error_reports: List[ErrorReport] = []
        self.recovery_history: List[RecoveryResult] = []

    def report_health(
        self,
        health_check: HealthCheck,
        session: Session
    ) -> str:
        """Report health status for an agent or service."""
        key = f"{health_check.agent_id}:{health_check.service_name}"
        self.health_checks[key] = health_check

        logger.info(
            f"Health report: {health_check.agent_id} - {health_check.service_name} "
            f"- {health_check.status} ({health_check.response_time_ms}ms)"
        )

        # Check if health is degraded or unhealthy
        if health_check.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]:
            self._trigger_self_healing(health_check, session)

        return key

    def report_error(
        self,
        error_report: ErrorReport,
        session: Session
    ) -> str:
        """Report an error for self-healing analysis."""
        error_id = str(uuid.uuid4())
        error_report.timestamp = datetime.utcnow()
        self.error_reports.append(error_report)

        logger.warning(
            f"Error reported: {error_report.agent_id} - {error_report.service_name} "
            f"- {error_report.error_type} ({error_report.severity})"
        )

        # Trigger self-healing for critical errors
        if error_report.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self._trigger_error_recovery(error_report, session)

        return error_id

    def _trigger_self_healing(
        self,
        health_check: HealthCheck,
        session: Session
    ) -> None:
        """Trigger self-healing based on health status."""
        actions = self._determine_recovery_actions(health_check)

        for action in actions:
            result = self._execute_recovery_action(
                action,
                health_check.agent_id,
                session
            )
            self.recovery_history.append(result)

    def _trigger_error_recovery(
        self,
        error_report: ErrorReport,
        session: Session
    ) -> None:
        """Trigger recovery based on error report."""
        actions = self._determine_error_recovery_actions(error_report)

        for action in actions:
            result = self._execute_recovery_action(
                action,
                error_report.agent_id,
                session
            )
            self.recovery_history.append(result)

    def _determine_recovery_actions(
        self,
        health_check: HealthCheck
    ) -> List[RecoveryAction]:
        """Determine appropriate recovery actions based on health status."""
        actions = []

        if health_check.status == HealthStatus.UNHEALTHY:
            # Service is unhealthy - attempt restart
            actions.append(RecoveryAction(
                action_type="restart_service",
                description=f"Restart service {health_check.service_name}",
                parameters={"service": health_check.service_name}
            ))

        elif health_check.status == HealthStatus.DEGRADED:
            # Service is degraded - check resources
            if health_check.response_time_ms > 1000:
                actions.append(RecoveryAction(
                    action_type="optimize_resources",
                    description="Optimize resource allocation",
                    parameters={"target_response_time": 500}
                ))

        return actions

    def _determine_error_recovery_actions(
        self,
        error_report: ErrorReport
    ) -> List[RecoveryAction]:
        """Determine recovery actions based on error type."""
        actions = []

        if error_report.error_type == ErrorType.NETWORK_ERROR:
            actions.append(RecoveryAction(
                action_type="retry_with_backoff",
                description="Retry operation with exponential backoff",
                parameters={"max_retries": 3, "initial_delay": 1000}
            ))

        elif error_report.error_type == ErrorType.TIMEOUT_ERROR:
            actions.append(RecoveryAction(
                action_type="increase_timeout",
                description="Increase timeout threshold",
                parameters={"timeout_multiplier": 2.0}
            ))

        elif error_report.error_type == ErrorType.RESOURCE_ERROR:
            actions.append(RecoveryAction(
                action_type="allocate_more_resources",
                description="Allocate additional resources",
                parameters={"resource_type": "memory", "increase_percent": 50}
            ))

        elif error_report.error_type == ErrorType.SERVICE_UNAVAILABLE:
            actions.append(RecoveryAction(
                action_type="restart_service",
                description="Restart unavailable service",
                parameters={"service": error_report.service_name}
            ))

        elif error_report.error_type == ErrorType.DATABASE_ERROR:
            actions.append(RecoveryAction(
                action_type="reconnect_database",
                description="Reconnect to database",
                parameters={}
            ))

        return actions

    def _execute_recovery_action(
        self,
        action: RecoveryAction,
        agent_id: str,
        session: Session
    ) -> RecoveryResult:
        """Execute a recovery action."""
        action_id = str(uuid.uuid4())
        success = False
        message = ""

        try:
            # Simulate recovery action execution
            # In production, this would call actual recovery logic
            logger.info(f"Executing recovery action: {action.action_type} for {agent_id}")

            # Simulate success for demo
            success = True
            message = f"Recovery action {action.action_type} executed successfully"

        except Exception as e:
            success = False
            message = f"Recovery action failed: {str(e)}"
            logger.error(f"Recovery action failed: {e}")

        return RecoveryResult(
            action_id=action_id,
            agent_id=agent_id,
            success=success,
            message=message,
            timestamp=datetime.utcnow()
        )

    def get_health_status(
        self,
        agent_id: Optional[str] = None,
        service_name: Optional[str] = None
    ) -> List[HealthCheck]:
        """Get health status with optional filtering."""
        results = []

        for key, health_check in self.health_checks.items():
            # Apply filters
            if agent_id and health_check.agent_id != agent_id:
                continue
            if service_name and health_check.service_name != service_name:
                continue

            results.append(health_check)

        return results

    def get_recovery_history(
        self,
        agent_id: Optional[str] = None,
        limit: int = 100
    ) -> List[RecoveryResult]:
        """Get recovery history with optional filtering."""
        results = self.recovery_history[-limit:]

        if agent_id:
            results = [r for r in results if r.agent_id == agent_id]

        return results


# Global service instance
health_service = HealthService()
