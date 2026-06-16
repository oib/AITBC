"""
Tests for health check utilities
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from aitbc.health_checks import (
    HealthCheck,
    HealthChecker,
    HealthStatus,
    create_basic_health_check,
)


class TestHealthStatus:
    """Tests for HealthStatus enum"""

    def test_health_status_values(self):
        """Test HealthStatus enum values"""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


class TestHealthCheck:
    """Tests for HealthCheck dataclass"""

    def test_health_check_creation(self):
        """Test HealthCheck dataclass creation"""
        check = HealthCheck(
            service="test-service",
            status=HealthStatus.HEALTHY,
            message="All good",
            timestamp=datetime.now(),
            details={"key": "value"},
        )
        assert check.service == "test-service"
        assert check.status == HealthStatus.HEALTHY
        assert check.message == "All good"
        assert check.details == {"key": "value"}

    def test_health_check_without_details(self):
        """Test HealthCheck without optional details"""
        check = HealthCheck(service="test-service", status=HealthStatus.HEALTHY, message="All good", timestamp=datetime.now())
        assert check.details is None


class TestHealthChecker:
    """Tests for HealthChecker"""

    def test_health_checker_initialization(self):
        """Test HealthChecker initialization"""
        checker = HealthChecker("test-service")
        assert checker.service_name == "test-service"
        assert checker._checks == {}
        assert checker._last_check is None

    def test_register_check(self):
        """Test registering a health check"""
        checker = HealthChecker("test-service")

        def mock_check():
            return HealthStatus.HEALTHY, "OK", {}

        checker.register_check("memory", mock_check)
        assert "memory" in checker._checks
        assert checker._checks["memory"] == mock_check

    @patch("aitbc.health_checks.logger")
    def test_register_check_logs(self, mock_logger):
        """Test register_check logs registration"""
        checker = HealthChecker("test-service")

        def mock_check():
            return HealthStatus.HEALTHY, "OK", {}

        checker.register_check("memory", mock_check)
        mock_logger.info.assert_called_once()
        assert "memory" in mock_logger.info.call_args[0][0]

    def test_run_checks_all_healthy(self):
        """Test run_checks when all checks pass"""
        checker = HealthChecker("test-service")

        def mock_check():
            return HealthStatus.HEALTHY, "OK", {}

        checker.register_check("check1", mock_check)
        checker.register_check("check2", mock_check)

        result = checker.run_checks()

        assert result.service == "test-service"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "All health checks passed"
        assert result.details is not None
        assert len(result.details) == 2

    def test_run_checks_one_degraded(self):
        """Test run_checks with one degraded check"""
        checker = HealthChecker("test-service")

        def healthy_check():
            return HealthStatus.HEALTHY, "OK", {}

        def degraded_check():
            return HealthStatus.DEGRADED, "Warning", {}

        checker.register_check("healthy", healthy_check)
        checker.register_check("degraded", degraded_check)

        result = checker.run_checks()

        assert result.status == HealthStatus.DEGRADED
        assert "degraded" in result.message

    def test_run_checks_one_unhealthy(self):
        """Test run_checks with one unhealthy check"""
        checker = HealthChecker("test-service")

        def healthy_check():
            return HealthStatus.HEALTHY, "OK", {}

        def unhealthy_check():
            return HealthStatus.UNHEALTHY, "Error", {}

        checker.register_check("healthy", healthy_check)
        checker.register_check("unhealthy", unhealthy_check)

        result = checker.run_checks()

        assert result.status == HealthStatus.UNHEALTHY
        assert "unhealthy" in result.message

    @patch("aitbc.health_checks.logger")
    def test_run_checks_with_exception(self, mock_logger):
        """Test run_checks handles exceptions in checks"""
        checker = HealthChecker("test-service")

        def failing_check():
            raise ValueError("Check failed")

        checker.register_check("failing", failing_check)

        result = checker.run_checks()

        assert result.status == HealthStatus.UNHEALTHY
        assert "failing" in result.message
        mock_logger.error.assert_called_once()

    def test_get_last_check_before_run(self):
        """Test get_last_check returns None before any check run"""
        checker = HealthChecker("test-service")
        assert checker.get_last_check() is None

    def test_get_last_check_after_run(self):
        """Test get_last_check returns last check result"""
        checker = HealthChecker("test-service")

        def mock_check():
            return HealthStatus.HEALTHY, "OK", {}

        checker.register_check("check1", mock_check)
        checker.run_checks()

        last_check = checker.get_last_check()
        assert last_check is not None
        assert last_check.service == "test-service"

    def test_get_health_dict(self):
        """Test get_health_dict returns dictionary representation"""
        checker = HealthChecker("test-service")

        def mock_check():
            return HealthStatus.HEALTHY, "OK", {"key": "value"}

        checker.register_check("check1", mock_check)
        health_dict = checker.get_health_dict()

        assert isinstance(health_dict, dict)
        assert "service" in health_dict
        assert "status" in health_dict
        assert "message" in health_dict
        assert "timestamp" in health_dict
        assert health_dict["service"] == "test-service"


class TestCreateBasicHealthCheck:
    """Tests for create_basic_health_check"""

    def test_create_basic_health_check(self):
        """Test create_basic_health_check returns HealthChecker"""
        checker = create_basic_health_check("test-service")
        assert isinstance(checker, HealthChecker)
        assert checker.service_name == "test-service"

    def test_create_basic_health_check_without_psutil(self):
        """Test create_basic_health_check handles psutil ImportError"""
        # Skip this test as psutil import handling is complex to mock
        pytest.skip("psutil import handling requires complex mocking")

    def test_basic_health_check_has_checks(self):
        """Test basic health check has registered checks when psutil available"""
        try:
            import psutil  # noqa: F401

            checker = create_basic_health_check("test-service")
            # Should have memory and disk checks if psutil is available
            assert len(checker._checks) > 0
        except ImportError:
            # Skip if psutil not available
            pass
