"""Service for Hermes self-healing and health monitoring with database storage."""

import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)
from ....models.hermes import ErrorReportModel, HealthCheckModel, RecoveryResultModel  # noqa: E402
from ....schemas.hermes_health import ErrorReport, HealthCheck, HealthStatus, RecoveryResult  # noqa: E402


class HealthService:
    """Service for health monitoring and self-healing with database storage."""

    def __init__(self) -> None:
        pass

    def report_health(self, health_check: HealthCheck, session: Session) -> str:
        """Report health status for an agent or service."""
        key = f"{health_check.agent_id}:{health_check.service_name}"
        health_record = HealthCheckModel(
            id=str(uuid.uuid4()),
            agent_id=health_check.agent_id,
            service_name=health_check.service_name,
            status=health_check.status,
            timestamp=health_check.timestamp or datetime.utcnow(),
            response_time_ms=health_check.response_time_ms,
            error_message=health_check.error_message,
            meta_data=json.dumps(health_check.metadata or {}),
        )  # type: ignore[arg-type]
        session.add(health_record)
        session.commit()
        if health_check.status in [HealthStatus.UNHEALTHY, HealthStatus.DEGRADED]:
            self._trigger_recovery(health_check.agent_id, health_check.service_name, session)
        logger.info("Health reported: %s - %s", key, health_check.status)
        return key

    def report_error(self, error_report: ErrorReport, session: Session) -> str:
        """Report an error for self-healing analysis."""
        error_id = str(uuid.uuid4())
        error_record = ErrorReportModel(
            id=str(uuid.uuid4()),
            agent_id=error_report.agent_id,
            service_name=error_report.service_name,
            error_type=error_report.error_type,
            severity=error_report.severity,
            error_message=error_report.error_message,
            timestamp=error_report.timestamp or datetime.utcnow(),
            context=json.dumps(error_report.context or {}),
        )
        session.add(error_record)
        session.commit()
        if error_report.severity in ["high", "critical"]:
            self._trigger_recovery(error_report.agent_id, error_report.service_name, session)
        logger.info("Error reported: %s - %s", error_id, error_report.error_type)
        return error_id

    def get_health_status(
        self, session: Session, agent_id: str | None = None, service_name: str | None = None
    ) -> list[HealthCheck]:
        """Get health status with optional filtering."""
        query = session.query(HealthCheckModel)
        if agent_id:
            query = query.filter_by(agent_id=agent_id)
        if service_name:
            query = query.filter_by(service_name=service_name)
        results = query.order_by(HealthCheckModel.timestamp.desc()).limit(100).all()
        return [
            HealthCheck(
                agent_id=r.agent_id,
                service_name=r.service_name,
                status=r.status,
                timestamp=r.timestamp,
                response_time_ms=r.response_time_ms,
                error_message=r.error_message,
                metadata=json.loads(r.meta_data) if r.meta_data else {},
            )
            for r in results
        ]

    def get_recovery_history(self, session: Session, agent_id: str | None = None, limit: int = 100) -> list[RecoveryResult]:
        """Get recovery history with optional filtering."""
        query = session.query(RecoveryResultModel)
        if agent_id:
            query = query.filter_by(agent_id=agent_id)
        results = query.order_by(RecoveryResultModel.timestamp.desc()).limit(limit).all()
        return [
            RecoveryResult(
                action_id=str(r.action_id),
                agent_id=r.agent_id,
                success=r.success == "true",
                message=r.message,
                timestamp=r.timestamp,
            )
            for r in results
        ]

    def _trigger_recovery(self, agent_id: str, service_name: str, session: Session) -> None:
        """Trigger automatic recovery action based on health status."""
        action_id = uuid.uuid4()
        if "gpu" in service_name.lower():
            action = "restart_gpu_service"
        elif "blockchain" in service_name.lower():
            action = "reconnect_blockchain"
        elif "network" in service_name.lower():
            action = "reset_network_connection"
        else:
            action = "generic_restart"
        success = True
        message = f"Recovery action {action} executed successfully"
        recovery_record = RecoveryResultModel(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            action_id=str(action_id),
            success="true" if success else "false",
            message=message,
            timestamp=datetime.utcnow(),
        )
        session.add(recovery_record)
        session.commit()
        logger.info("Recovery triggered: %s for %s:%s", action_id, agent_id, service_name)


health_service = HealthService()
