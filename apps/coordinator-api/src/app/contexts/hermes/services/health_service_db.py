"""Service for Hermes self-healing and health monitoring with database storage."""

import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from aitbc import get_logger

logger = get_logger(__name__)

from ....schemas.hermes_health import (
    HealthCheck,
    HealthStatus,
    ErrorReport,
    RecoveryResult,
)
from ....models.hermes import (
    HealthCheckModel,
    ErrorReportModel,
    RecoveryResultModel,
)


class HealthService:
    """Service for health monitoring and self-healing with database storage."""

    def __init__(self):
        # Database storage for health data
        pass

    def report_health(
        self,
        health_check: HealthCheck,
        session: Session
    ) -> str:
        """Report health status for an agent or service."""
        key = f"{health_check.agent_id}:{health_check.service_name}"

        # Store health check in database
        health_record = HealthCheckModel(
            agent_id=health_check.agent_id,
            service_name=health_check.service_name,
            status=health_check.status,
            timestamp=health_check.timestamp or datetime.utcnow(),
            response_time_ms=health_check.response_time_ms,
            error_message=health_check.error_message,
            metadata=health_check.metadata or {},
        )

        session.add(health_record)
        session.commit()

        # Trigger self-healing if needed
        if health_check.status in [HealthStatus.UNHEALTHY, HealthStatus.DEGRADED]:
            self._trigger_recovery(health_check.agent_id, health_check.service_name, session)

        logger.info(f"Health reported: {key} - {health_check.status}")
        return key

    def report_error(
        self,
        error_report: ErrorReport,
        session: Session
    ) -> str:
        """Report an error for self-healing analysis."""
        error_id = str(uuid.uuid4())

        # Store error report in database
        error_record = ErrorReportModel(
            id=error_id,
            agent_id=error_report.agent_id,
            service_name=error_report.service_name,
            error_type=error_report.error_type,
            severity=error_report.severity,
            error_message=error_report.error_message,
            timestamp=error_report.timestamp or datetime.utcnow(),
            context=error_report.context or {},
        )

        session.add(error_record)
        session.commit()

        # Trigger self-healing for high/critical errors
        if error_report.severity in ["high", "critical"]:
            self._trigger_recovery(error_report.agent_id, error_report.service_name, session)

        logger.info(f"Error reported: {error_id} - {error_report.error_type}")
        return error_id

    def get_health_status(
        self,
        agent_id: Optional[str] = None,
        service_name: Optional[str] = None
    ) -> List[HealthCheck]:
        """Get health status with optional filtering."""
        from ....storage.db_pg import SessionLocal

        session = SessionLocal()
        try:
            query = session.query(HealthCheckModel)

            if agent_id:
                query = query.filter_by(agent_id=agent_id)
            if service_name:
                query = query.filter_by(service_name=service_name)

            # Get most recent health check per agent/service
            results = query.order_by(HealthCheckModel.timestamp.desc()).limit(100).all()

            return [
                HealthCheck(
                    agent_id=r.agent_id,
                    service_name=r.service_name,
                    status=r.status,
                    timestamp=r.timestamp,
                    response_time_ms=r.response_time_ms,
                    error_message=r.error_message,
                    metadata=r.metadata,
                )
                for r in results
            ]
        finally:
            session.close()

    def get_recovery_history(
        self,
        agent_id: Optional[str] = None,
        limit: int = 100
    ) -> List[RecoveryResult]:
        """Get recovery history with optional filtering."""
        from ....storage.db_pg import SessionLocal

        session = SessionLocal()
        try:
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
        finally:
            session.close()

    def _trigger_recovery(
        self,
        agent_id: str,
        service_name: str,
        session: Session
    ) -> None:
        """Trigger automatic recovery action based on health status."""
        # Simulated recovery actions (implement actual recovery logic in production)
        action_id = uuid.uuid4()

        # Determine recovery action based on service
        if "gpu" in service_name.lower():
            action = "restart_gpu_service"
        elif "blockchain" in service_name.lower():
            action = "reconnect_blockchain"
        elif "network" in service_name.lower():
            action = "reset_network_connection"
        else:
            action = "generic_restart"

        # Simulate recovery execution
        success = True  # In production, execute actual recovery logic
        message = f"Recovery action {action} executed successfully"

        # Store recovery result
        recovery_record = RecoveryResultModel(
            action_id=action_id,
            agent_id=agent_id,
            success="true" if success else "false",
            message=message,
            timestamp=datetime.utcnow(),
        )

        session.add(recovery_record)
        session.commit()

        logger.info(f"Recovery triggered: {action_id} for {agent_id}:{service_name}")


# Global service instance
health_service = HealthService()
