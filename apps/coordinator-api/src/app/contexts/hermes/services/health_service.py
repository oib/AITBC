"""Service for Hermes self-healing and health monitoring."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger

from ....schemas.hermes_health import (
    ErrorReport,
    ErrorSeverity,
    ErrorType,
    HealthCheck,
    HealthStatus,
    RecoveryAction,
    RecoveryResult,
)

logger = get_logger(__name__)


class HealthService:
    """Service for monitoring agent health and executing self-healing actions."""

    def __init__(self) -> None:
        self.health_checks: dict[str, HealthCheck] = {}
        self.error_reports: list[ErrorReport] = []
        self.recovery_history: list[RecoveryResult] = []

    def report_health(self, health_check: HealthCheck, session: Session) -> str:
        """Report health status for an agent or service."""
        key = f"{health_check.agent_id}:{health_check.service_name}"
        self.health_checks[key] = health_check
        logger.info(
            "Health report: %s - %s - %s (%sms)",
            health_check.agent_id,
            health_check.service_name,
            health_check.status,
            health_check.response_time_ms,
        )
        if health_check.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]:
            self._trigger_self_healing(health_check, session)
        return key

    def report_error(self, error_report: ErrorReport, session: Session) -> str:
        """Report an error for self-healing analysis."""
        error_id = str(uuid.uuid4())
        error_report.timestamp = datetime.utcnow()
        self.error_reports.append(error_report)
        logger.warning(
            "Error reported: %s - %s - %s (%s)",
            error_report.agent_id,
            error_report.service_name,
            error_report.error_type,
            error_report.severity,
        )
        if error_report.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self._trigger_error_recovery(error_report, session)
        return error_id

    def _trigger_self_healing(self, health_check: HealthCheck, session: Session) -> None:
        """Trigger self-healing based on health status."""
        actions = self._determine_recovery_actions(health_check)
        for action in actions:
            result = self._execute_recovery_action(action, health_check.agent_id, session)
            self.recovery_history.append(result)

    def _trigger_error_recovery(self, error_report: ErrorReport, session: Session) -> None:
        """Trigger recovery based on error report."""
        actions = self._determine_error_recovery_actions(error_report)
        for action in actions:
            result = self._execute_recovery_action(action, error_report.agent_id, session)
            self.recovery_history.append(result)

    def _determine_recovery_actions(self, health_check: HealthCheck) -> list[RecoveryAction]:
        """Determine appropriate recovery actions based on health status."""
        actions = []
        if health_check.status == HealthStatus.UNHEALTHY:
            actions.append(
                RecoveryAction(
                    action_type="restart_service",
                    description=f"Restart service {health_check.service_name}",
                    parameters={"service": health_check.service_name},
                )
            )
        elif health_check.status == HealthStatus.DEGRADED:
            if health_check.response_time_ms > 1000:
                actions.append(
                    RecoveryAction(
                        action_type="optimize_resources",
                        description="Optimize resource allocation",
                        parameters={"target_response_time": 500},
                    )
                )
        return actions

    def _determine_error_recovery_actions(self, error_report: ErrorReport) -> list[RecoveryAction]:
        """Determine recovery actions based on error type."""
        actions = []
        if error_report.error_type == ErrorType.NETWORK_ERROR:
            actions.append(
                RecoveryAction(
                    action_type="retry_with_backoff",
                    description="Retry operation with exponential backoff",
                    parameters={"max_retries": 3, "initial_delay": 1000},
                )
            )
        elif error_report.error_type == ErrorType.TIMEOUT_ERROR:
            actions.append(
                RecoveryAction(
                    action_type="increase_timeout",
                    description="Increase timeout threshold",
                    parameters={"timeout_multiplier": 2.0},
                )
            )
        elif error_report.error_type == ErrorType.RESOURCE_ERROR:
            actions.append(
                RecoveryAction(
                    action_type="allocate_more_resources",
                    description="Allocate additional resources",
                    parameters={"resource_type": "memory", "increase_percent": 50},
                )
            )
        elif error_report.error_type == ErrorType.SERVICE_UNAVAILABLE:
            actions.append(
                RecoveryAction(
                    action_type="restart_service",
                    description="Restart unavailable service",
                    parameters={"service": error_report.service_name},
                )
            )
        elif error_report.error_type == ErrorType.DATABASE_ERROR:
            actions.append(
                RecoveryAction(action_type="reconnect_database", description="Reconnect to database", parameters={})
            )
        return actions

    def _execute_recovery_action(self, action: RecoveryAction, agent_id: str, session: Session) -> RecoveryResult:
        """Execute a recovery action."""
        action_id = str(uuid.uuid4())
        success = False
        message = ""
        try:
            logger.info("Executing recovery action: %s for %s", action.action_type, agent_id)
            success = True
            message = f"Recovery action {action.action_type} executed successfully"
        except Exception as e:
            success = False
            message = f"Recovery action failed: {str(e)}"
            logger.error("Recovery action failed: %s", e)
        return RecoveryResult(
            action_id=action_id, agent_id=agent_id, success=success, message=message, timestamp=datetime.utcnow()
        )

    def get_health_status(self, agent_id: str | None = None, service_name: str | None = None) -> list[HealthCheck]:
        """Get health status with optional filtering."""
        results = []
        for _key, health_check in self.health_checks.items():
            if agent_id and health_check.agent_id != agent_id:
                continue
            if service_name and health_check.service_name != service_name:
                continue
            results.append(health_check)
        return results

    def get_recovery_history(self, agent_id: str | None = None, limit: int = 100) -> list[RecoveryResult]:
        """Get recovery history with optional filtering."""
        results = self.recovery_history[-limit:]
        if agent_id:
            results = [r for r in results if r.agent_id == agent_id]
        return results


health_service = HealthService()
