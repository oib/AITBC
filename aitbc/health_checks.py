"""
Health check utilities for AITBC services
Provides health check endpoints for all services
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .aitbc_logging import get_logger

logger = get_logger(__name__)


class HealthStatus(Enum):
    """Health check status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    """Health check result"""

    service: str
    status: HealthStatus
    message: str
    timestamp: datetime
    details: dict[str, Any] | None = None


class HealthChecker:
    """
    Health checker for monitoring service health.
    Provides health check functionality for AITBC services.
    """

    def __init__(self, service_name: str):
        """
        Initialize health checker

        Args:
            service_name: Name of the service
        """
        self.service_name = service_name
        self._checks: dict[str, callable] = {}
        self._last_check: HealthCheck | None = None

    def register_check(self, name: str, check_func: callable) -> None:
        """
        Register a health check function

        Args:
            name: Name of the health check
            check_func: Function that returns (status, message, details)
        """
        self._checks[name] = check_func
        logger.info("Registered health check: %s", name)

    def run_checks(self) -> HealthCheck:
        """
        Run all registered health checks

        Returns:
            Overall health check result
        """
        results = []
        overall_status = HealthStatus.HEALTHY
        all_details = {}
        for name, check_func in self._checks.items():
            try:
                status, message, details = check_func()
                results.append((name, status, message))
                all_details[name] = {"status": status.value, "message": message, "details": details}
                if status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
            except Exception as e:
                logger.error("Health check %s failed: %s", name, e)
                results.append((name, HealthStatus.UNHEALTHY, str(e)))
                all_details[name] = {"status": HealthStatus.UNHEALTHY.value, "message": str(e), "details": None}
                overall_status = HealthStatus.UNHEALTHY
        if overall_status == HealthStatus.HEALTHY:
            message = "All health checks passed"
        elif overall_status == HealthStatus.DEGRADED:
            failed = [name for name, status, _ in results if status != HealthStatus.HEALTHY]
            message = f"Degraded: {', '.join(failed)}"
        else:
            failed = [name for name, status, _ in results if status != HealthStatus.HEALTHY]
            message = f"Unhealthy: {', '.join(failed)}"
        health_check = HealthCheck(
            service=self.service_name, status=overall_status, message=message, timestamp=datetime.now(), details=all_details
        )
        self._last_check = health_check
        return health_check

    def get_last_check(self) -> HealthCheck | None:
        """
        Get the last health check result

        Returns:
            Last health check result or None
        """
        return self._last_check

    def get_health_dict(self) -> dict[str, Any]:
        """
        Get health check result as dictionary

        Returns:
            Dictionary representation of health check
        """
        health_check = self.run_checks()
        return asdict(health_check)


def create_basic_health_check(service_name: str) -> HealthChecker:
    """
    Create a basic health checker with common checks

    Args:
        service_name: Name of the service

    Returns:
        HealthChecker instance with basic checks
    """
    checker = HealthChecker(service_name)

    def check_memory() -> tuple:
        """Check memory usage"""
        import psutil

        mem = psutil.virtual_memory()
        if mem.percent > 90:
            return (HealthStatus.UNHEALTHY, f"High memory usage: {mem.percent}%", {"percent": mem.percent})
        elif mem.percent > 70:
            return (HealthStatus.DEGRADED, f"Elevated memory usage: {mem.percent}%", {"percent": mem.percent})
        else:
            return (HealthStatus.HEALTHY, f"Memory usage: {mem.percent}%", {"percent": mem.percent})

    def check_disk() -> tuple:
        """Check disk usage"""
        import psutil

        disk = psutil.disk_usage("/")
        percent = disk.used / disk.total * 100
        if percent > 90:
            return (HealthStatus.UNHEALTHY, f"High disk usage: {percent:.1f}%", {"percent": percent})
        elif percent > 80:
            return (HealthStatus.DEGRADED, f"Elevated disk usage: {percent:.1f}%", {"percent": percent})
        else:
            return (HealthStatus.HEALTHY, f"Disk usage: {percent:.1f}%", {"percent": percent})

    try:
        checker.register_check("memory", check_memory)
        checker.register_check("disk", check_disk)
    except ImportError:
        logger.warning("psutil not available, skipping system health checks")
    return checker
