"""
Tests for health check utilities
"""

from datetime import datetime
from unittest.mock import patch


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
        assert mock_logger.info.call_args[0][1] == "memory"

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

    @patch("aitbc.health_checks.logger")
    def test_a_missing_psutil_is_reported_unhealthy_not_silently_skipped(self, mock_logger):
        """A missing psutil surfaces as UNHEALTHY, never as a silent skip.

        ``check_memory``/``check_disk`` import psutil lazily *inside* their bodies,
        so ``register_check`` only stores a callable and cannot raise. Registration
        was once wrapped in ``try/except ImportError`` logging "psutil not available,
        skipping system health checks"; that branch could not execute and has been
        removed. Do not re-add it -- it advertised a graceful degradation this module
        does not perform, and the warning never reached anyone's logs.

        What happens instead is asserted below: a missing psutil reaches
        ``run_checks``, whose generic handler turns it into UNHEALTHY naming both
        checks. For a dependency pinned in pyproject.toml that is the honest answer,
        and this test is what stops it drifting back to a silent skip.
        """
        with patch.dict("sys.modules", {"psutil": None}):
            checker = create_basic_health_check("test-service")

            # registration is unconditional -- both checks present despite the stub
            assert sorted(checker._checks) == ["disk", "memory"]
            assert mock_logger.warning.call_count == 0

            result = checker.run_checks()

        assert result.status == HealthStatus.UNHEALTHY
        assert "memory" in result.message
        assert "disk" in result.message
        for name in ("memory", "disk"):
            assert result.details[name]["status"] == "unhealthy"
            assert "psutil" in result.details[name]["message"]

        # surfaced as one error per failing check, never as the skip warning
        assert mock_logger.error.call_count == 2

    def test_basic_health_check_registers_memory_and_disk(self):
        """psutil is a pinned dependency (pyproject.toml), so this is unconditional.

        The previous version wrapped its assertions in ``try/except ImportError`` and
        passed silently when anything inside raised -- including a real failure of
        ``create_basic_health_check`` itself.
        """
        checker = create_basic_health_check("test-service")
        assert sorted(checker._checks) == ["disk", "memory"]
