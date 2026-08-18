"""V23-102: MarketplaceMonitor was unreachable, and starting it would have flooded the log.

``contexts/marketplace/services/marketplace_monitor.py`` defined a 280-line real-time
monitor ending in a module-level ``monitor = MarketplaceMonitor()``.  No module imported
it, so that singleton was never constructed and none of its recorders were ever called.

The obvious repair -- start it from the lifespan -- was the wrong one twice over:

1. coordinator-api already collects the same signals on the live request path, via
   ``PrometheusMetricsMiddleware`` and the ``metrics_collector`` that
   ``request_metrics_middleware`` drives on every request.  Starting the monitor would
   have created a second, disagreeing source of truth for latency and error rate.

2. Three of its eight thresholds were ``<`` comparisons against ``get_average()``, which
   returns 0.0 for an empty series.  Four of its thirteen series were pool-hub SLA
   metrics that coordinator-api has no feeder for, so those comparisons would have been
   0.0 < threshold forever.  Measured on this host before deletion: 27 ``MARKETPLACE
   ALERT`` warnings in 10 seconds -- one of them critical -- on a completely idle
   process, and ``get_realtime_dashboard_data()`` permanently reporting "degraded".

So the module is deleted, and the one capability it had that the live collector lacked --
response-time percentiles -- is ported onto ``MetricsCollector``, where requests actually
arrive.  These tests pin both halves.
"""

from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
COORDINATOR_SRC = REPO_ROOT / "apps" / "coordinator-api" / "src"
COORDINATOR_PKG = COORDINATOR_SRC / "coordinator_api"
MONITOR_PATH = COORDINATOR_PKG / "contexts" / "marketplace" / "services" / "marketplace_monitor.py"


def _iter_source_files() -> list[pathlib.Path]:
    return [
        path
        for path in sorted(COORDINATOR_PKG.rglob("*.py"))
        if "__pycache__" not in path.parts and ".venv" not in path.parts and "site-packages" not in path.parts
    ]


class TestTheDeadMonitorIsGone:
    def test_the_marketplace_monitor_module_no_longer_exists(self) -> None:
        assert not MONITOR_PATH.exists(), (
            f"{MONITOR_PATH.relative_to(REPO_ROOT)} is back. It is a second metrics system that nothing "
            "imports; coordinator-api already measures latency and error rate on the live request path "
            "through metrics_collector. See V23-102."
        )

    def test_the_marketplace_monitor_module_is_not_importable(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("coordinator_api.contexts.marketplace.services.marketplace_monitor")

    def test_no_code_still_references_the_deleted_module(self) -> None:
        """Checked over the AST, not the raw text.

        Comments and docstrings are allowed to name ``MarketplaceMonitor`` -- ``metrics.py``
        does exactly that, to record where its percentile code came from and why the alert
        thresholds are the numbers they are.  What must not survive is an import of the
        module or a use of the identifier.
        """
        offenders: list[str] = []
        for path in _iter_source_files():
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:  # pragma: no cover - a parse failure is another test's problem
                continue
            for node in ast.walk(tree):
                hit = False
                if isinstance(node, ast.ImportFrom):
                    hit = "marketplace_monitor" in (node.module or "") or any(
                        a.name in {"MarketplaceMonitor", "TimeSeriesData"} for a in node.names
                    )
                elif isinstance(node, ast.Import):
                    hit = any("marketplace_monitor" in a.name for a in node.names)
                elif isinstance(node, ast.Name):
                    hit = node.id == "MarketplaceMonitor"
                elif isinstance(node, ast.Attribute):
                    hit = node.attr in {"marketplace_monitor", "MarketplaceMonitor"}
                if hit:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
        assert offenders == [], f"code references to the deleted monitor survive: {sorted(set(offenders))}"

    def test_the_marketplace_services_package_does_not_export_it(self) -> None:
        init = (COORDINATOR_PKG / "contexts" / "marketplace" / "services" / "__init__.py").read_text()
        assert "marketplace_monitor" not in init
        assert "MarketplaceMonitor" not in init


class TestNoBackgroundLoopIsBuiltAtImportTime:
    """The structural defect behind V23-102, stated as an invariant.

    A module-level instance of a class with an ``async start()`` is a background service
    constructed by the import system.  It has exactly two fates and both are bugs: nobody
    calls ``start()`` and the code is dead (what happened here), or importing the module
    quietly brings a loop to life outside the lifespan that is supposed to own it.  The
    working pattern is the one pool-hub adopted in V23-101 -- construct the scheduler in
    the lifespan, behind a setting, and await ``stop()`` on the way out.
    """

    def test_no_module_constructs_a_background_service_at_import_time(self) -> None:
        offenders: list[str] = []
        for path in _iter_source_files():
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:  # pragma: no cover - a parse failure is another test's problem
                continue
            starters = {
                node.name
                for node in tree.body
                if isinstance(node, ast.ClassDef)
                and any(isinstance(m, ast.AsyncFunctionDef) and m.name == "start" for m in node.body)
            }
            if not starters:
                continue
            for node in tree.body:
                if (
                    isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id in starters
                ):
                    target = node.targets[0]
                    name = target.id if isinstance(target, ast.Name) else "<expr>"
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {name} = {node.value.func.id}()")
        assert offenders == [], (
            "background services constructed at import time (construct them in the lifespan instead, "
            f"as pool-hub does since V23-101): {offenders}"
        )


class TestPercentilesLandedOnTheCollectorThatRuns:
    def _collector(self):
        from coordinator_api.utils.metrics import MetricsCollector

        return MetricsCollector()

    def test_percentile_of_an_empty_window_is_zero(self) -> None:
        assert self._collector().get_response_time_percentile(0.95) == 0.0

    def test_percentile_reads_the_recorded_samples(self) -> None:
        collector = self._collector()
        for value_ms in range(1, 101):  # 1ms .. 100ms
            collector.record_api_response_time(value_ms / 1000.0)
        # idx = int(100 * 0.95) = 95 -> the 96th smallest sample, i.e. 96ms.
        assert collector.get_response_time_percentile(0.95) == pytest.approx(0.096)
        assert collector.get_response_time_percentile(0.50) == pytest.approx(0.051)

    def test_percentiles_are_monotonic(self) -> None:
        collector = self._collector()
        for value_ms in (5, 500, 12, 900, 3, 44, 120, 7):
            collector.record_api_response_time(value_ms / 1000.0)
        values = [collector.get_response_time_percentile(p) for p in (0.0, 0.25, 0.5, 0.75, 0.95, 1.0)]
        assert values == sorted(values)

    def test_percentile_is_clamped_at_both_ends(self) -> None:
        collector = self._collector()
        for value_ms in (10, 20, 30):
            collector.record_api_response_time(value_ms / 1000.0)
        assert collector.get_response_time_percentile(0.0) == pytest.approx(0.010)
        assert collector.get_response_time_percentile(1.0) == pytest.approx(0.030)

    def test_percentile_honours_the_hundred_sample_retention_window(self) -> None:
        collector = self._collector()
        collector.record_api_response_time(99.0)  # one enormous outlier, then 100 fast requests
        for _ in range(100):
            collector.record_api_response_time(0.001)
        assert collector.get_response_time_percentile(1.0) == pytest.approx(0.001), (
            "the outlier should have been evicted with the rest of the pre-window samples"
        )

    def test_get_metrics_publishes_both_percentiles(self) -> None:
        collector = self._collector()
        for value_ms in range(1, 101):
            collector.record_api_response_time(value_ms / 1000.0)
        metrics = collector.get_metrics()
        assert metrics["p50_response_time_ms"] == pytest.approx(51.0)
        assert metrics["p95_response_time_ms"] == pytest.approx(96.0)
        assert metrics["avg_response_time_ms"] == pytest.approx(50.5)


class TestAlertsStayQuietOnAnEmptySeries:
    """The half of V23-102 that would have caused the outage-shaped log flood."""

    def _collector(self):
        from coordinator_api.utils.metrics import MetricsCollector

        return MetricsCollector()

    def test_a_fresh_collector_triggers_no_data_driven_alert(self) -> None:
        # memory_usage is excluded deliberately: it reads real RSS, so its state depends on
        # the host rather than on recorded samples. Every other alert must be quiet.
        alerts = self._collector().get_alert_states()
        triggered = {name: state for name, state in alerts.items() if name != "memory_usage" and state["triggered"]}
        assert triggered == {}, f"alerts firing with nothing recorded (the V23-102 defect): {triggered}"

    def test_the_p95_alert_exists_and_is_quiet_when_nothing_was_recorded(self) -> None:
        alert = self._collector().get_alert_states()["p95_response_time"]
        assert alert["triggered"] is False
        assert alert["threshold"] == 500.0
        assert alert["value"] == 0.0

    def test_the_p95_alert_catches_tail_latency_the_average_hides(self) -> None:
        collector = self._collector()
        for _ in range(95):
            collector.record_api_response_time(0.010)  # 10ms
        for _ in range(5):
            collector.record_api_response_time(5.0)  # 5s
        alerts = collector.get_alert_states()
        assert alerts["avg_response_time"]["triggered"] is False, "mean is 259.5ms, under the 500ms bound"
        assert alerts["p95_response_time"]["triggered"] is True, (
            "5% of requests took five seconds; that is exactly the signal a mean cannot show"
        )
        assert alerts["p95_response_time"]["status"] == "critical"

    def test_the_existing_average_alert_is_unchanged(self) -> None:
        collector = self._collector()
        for _ in range(10):
            collector.record_api_response_time(0.600)  # 600ms, over the bound
        alerts = collector.get_alert_states()
        assert alerts["avg_response_time"]["triggered"] is True
        assert alerts["avg_response_time"]["threshold"] == 500.0
        assert alerts["avg_response_time"]["value"] == pytest.approx(600.0)

    def test_the_error_rate_alert_needs_a_request_before_it_can_fire(self) -> None:
        collector = self._collector()
        collector.increment_api_errors()  # an error with no request recorded
        assert collector.get_alert_states()["error_rate"]["triggered"] is False


class TestDeletingAFileDoesNotCrashTheFloatMoneyLint:
    """Fallout from the deletion, fixed alongside it.

    ``no_float_money.py`` enumerates its inputs with ``git ls-files``, which reads the index.
    A file deleted in the working tree but not yet staged is therefore still handed to the
    scanner, which called ``read_text`` on it and died with ``FileNotFoundError`` partway
    through the run.  Deleting a single ``.py`` file was enough to turn ``pre-commit`` into a
    traceback that named the linter rather than the deletion.
    """

    def _violations_in(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("no_float_money", REPO_ROOT / "scripts" / "lint" / "no_float_money.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module._violations_in

    def test_a_path_that_is_not_on_disk_yields_no_violations(self) -> None:
        violations_in = self._violations_in()
        assert violations_in(pathlib.Path("apps/coordinator-api/src/coordinator_api/does_not_exist.py")) == []

    def test_a_whole_scan_survives_a_tracked_file_that_is_not_on_disk(self) -> None:
        """End to end, because the per-file check alone would pass for the wrong reason.

        Asserting ``_violations_in(<the deleted monitor>) == []`` looks like a test of this
        fix but is not: on any branch where the file still exists it parses cleanly and
        returns ``[]`` anyway.  Forcing a missing path into the file list is what actually
        distinguishes the fixed scanner from the crashing one.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location("no_float_money", REPO_ROOT / "scripts" / "lint" / "no_float_money.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        module._tracked_python_files = lambda: [pathlib.Path("apps/coordinator-api/src/coordinator_api/deleted_here.py")]
        assert module._scan() == {}
