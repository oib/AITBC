"""Unit tests for aitbc.health_checks async and remaining behavior."""

import pytest

from aitbc.health_checks import (
    HealthChecker,
    HealthStatus,
    create_basic_health_check,
)


class TestAsyncHealthChecker:
    @pytest.mark.asyncio
    async def test_async_run_checks_sync_healthy(self):
        checker = HealthChecker("test")

        def healthy_check():
            return HealthStatus.HEALTHY, "OK", {}

        checker.register_check("sync", healthy_check)
        result = await checker.async_run_checks()
        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_async_run_checks_async_healthy(self):
        checker = HealthChecker("test")

        async def healthy_check():
            return HealthStatus.HEALTHY, "OK", {}

        checker.register_async_check("async", healthy_check)
        result = await checker.async_run_checks()
        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_async_run_checks_async_string_result(self):
        checker = HealthChecker("test")

        async def healthy_check():
            return "all good"

        checker.register_async_check("async", healthy_check)
        result = await checker.async_run_checks()
        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_async_run_checks_exception(self):
        checker = HealthChecker("test")

        async def failing_check():
            raise RuntimeError("boom")

        checker.register_async_check("failing", failing_check)
        result = await checker.async_run_checks()
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_async_get_health_dict(self):
        checker = HealthChecker("test")

        def healthy_check():
            return HealthStatus.HEALTHY, "OK", {"key": "value"}

        checker.register_check("sync", healthy_check)
        health_dict = await checker.async_get_health_dict()
        assert health_dict["service"] == "test"
        assert health_dict["status"] == HealthStatus.HEALTHY


class TestCreateBasicHealthCheck:
    def test_creates_checker_with_checks(self):
        try:
            import psutil  # noqa: F401
        except ImportError:
            pytest.skip("psutil not available")

        checker = create_basic_health_check("test-service")
        assert checker.service_name == "test-service"
        assert len(checker._checks) > 0
