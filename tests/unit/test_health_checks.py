"""Unit tests for aitbc.health_checks async and remaining behavior."""

from types import SimpleNamespace

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


class TestBasicHealthCheckThresholds:
    """Every band of the memory and disk checks, including both exact edges.

    `create_basic_health_check` was only ever asserted to *register* its checks,
    never to run them, so all six branches were uncovered -- the thresholds could
    have been inverted and the suite would still have passed. The edges are worth
    pinning because both comparisons are strict ``>``: a host sitting on exactly
    90% memory is DEGRADED, not UNHEALTHY, and switching either to ``>=`` would
    move real hosts between bands.
    """

    @staticmethod
    def _run(monkeypatch, name, *, memory_percent=0.0, disk_used=0, disk_total=100):
        """Invoke one registered check with psutil's readings replaced."""
        psutil = pytest.importorskip("psutil")
        monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(percent=memory_percent))
        monkeypatch.setattr(psutil, "disk_usage", lambda _path: SimpleNamespace(used=disk_used, total=disk_total))
        return create_basic_health_check("thresholds")._checks[name]()

    @pytest.mark.parametrize(
        "percent, expected",
        [
            (95.0, HealthStatus.UNHEALTHY),
            (90.1, HealthStatus.UNHEALTHY),
            (90.0, HealthStatus.DEGRADED),
            (70.1, HealthStatus.DEGRADED),
            (70.0, HealthStatus.HEALTHY),
            (0.0, HealthStatus.HEALTHY),
        ],
    )
    def test_memory_bands(self, monkeypatch, percent, expected):
        status, message, details = self._run(monkeypatch, "memory", memory_percent=percent)
        assert status is expected
        assert details["percent"] == percent
        assert str(percent) in message

    @pytest.mark.parametrize(
        "used, expected",
        [
            (95, HealthStatus.UNHEALTHY),
            (90, HealthStatus.DEGRADED),
            (85, HealthStatus.DEGRADED),
            (80, HealthStatus.HEALTHY),
            (0, HealthStatus.HEALTHY),
        ],
    )
    def test_disk_bands(self, monkeypatch, used, expected):
        """Disk reports a ratio, not a percentage, so the arithmetic is on test too."""
        status, _message, details = self._run(monkeypatch, "disk", disk_used=used, disk_total=100)
        assert status is expected
        assert details["percent"] == pytest.approx(float(used))
