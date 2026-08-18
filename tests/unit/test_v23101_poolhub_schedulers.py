"""V23-101 — Pool Hub's two background schedulers had never been constructed.

``SLACollectorScheduler`` and ``BillingIntegrationScheduler`` were both defined
with ``start()``, ``stop()`` and a loop, and a repo-wide search found exactly one
reference to each: its own ``class`` statement.  Pool Hub's lifespan created the
engine, the Redis client and the tables, and nothing else, so:

* SLA metrics were collected only when someone called ``POST /v1/sla/metrics/collect``.
* Usage was synced only by ``POST /v1/sla/billing/sync``.
* ``sla_collection_interval_seconds`` and ``billing_sync_interval_hours`` -- two
  settings whose only purpose is to configure these loops -- were read by nothing.

Three defects sat behind that, each reachable the moment either loop is started:

1. The schedulers took an already-constructed service, and therefore one
   ``AsyncSession``, held for the life of the process: one pooled connection
   pinned, one identity map growing, and a failed transaction carried from one
   pass into the next.
2. ``stop()`` cleared a flag.  The loop was parked in ``asyncio.sleep`` for up to
   a full interval, so shutdown returned with the task still pending.
3. ``sync_all_miners_usage`` called ``record_usage``, which catches a send failure
   and *returns* ``{"status": "failed"}``.  A returning call read as a delivered
   event, so a sync in which every single event was dropped reported
   ``miners_processed=1, miners_failed=0, total_usage_records=3``.

Defect 3 is the one that was live before this change: it is on the manual
``POST /v1/sla/billing/sync`` path, which is the only billing path Pool Hub had.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from poolhub.services.billing_integration import BillingIntegration, BillingIntegrationScheduler
from poolhub.services.sla_collector import SLACollectorScheduler
from poolhub.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
POOLHUB_SRC = REPO_ROOT / "apps/pool-hub/src/poolhub"
MAIN_PY = POOLHUB_SRC / "app/main.py"


# --- stubs ----------------------------------------------------------------------


class _StubResult:
    def __init__(self, rows: list[Any] | None = None, scalar_value: Any = None) -> None:
        self._rows = list(rows or [])
        self._scalar = scalar_value

    def scalars(self) -> _StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar(self) -> Any:
        return self._scalar


class _Transaction:
    async def __aenter__(self) -> _Transaction:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _Session:
    """AsyncSession stand-in that records whether it was closed."""

    def __init__(self, results: list[_StubResult] | None = None) -> None:
        self._results = list(results or [])
        self.closed = False

    async def execute(self, stmt: Any) -> _StubResult:
        return self._results.pop(0) if self._results else _StubResult()

    def begin(self) -> _Transaction:
        return _Transaction()

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        self.closed = True
        return False


class _SessionFactory:
    """async_sessionmaker stand-in: a fresh session per call, all of them kept."""

    def __init__(self, results_per_call: list[list[_StubResult]] | None = None) -> None:
        self._results = list(results_per_call or [])
        self.sessions: list[_Session] = []

    def __call__(self) -> _Session:
        results = self._results.pop(0) if self._results else []
        session = _Session(results)
        self.sessions.append(session)
        return session


# --- the shape of the schedulers -------------------------------------------------


@pytest.mark.parametrize("scheduler_cls", [SLACollectorScheduler, BillingIntegrationScheduler])
def test_a_scheduler_takes_a_session_factory_not_a_session(scheduler_cls: type) -> None:
    """A process-lifetime loop must be able to open a session per pass."""
    params = list(inspect.signature(scheduler_cls.__init__).parameters)
    assert params == ["self", "session_factory"], f"{scheduler_cls.__name__}{params}"


@pytest.mark.parametrize("scheduler_cls", [SLACollectorScheduler, BillingIntegrationScheduler])
def test_a_scheduler_keeps_a_handle_on_its_task(scheduler_cls: type) -> None:
    """Without the handle there is nothing for stop() to cancel."""
    scheduler = scheduler_cls(_SessionFactory())
    assert scheduler._task is None
    assert scheduler.running is False


# --- session per pass ------------------------------------------------------------


async def test_sla_collection_opens_and_closes_a_session_for_each_pass() -> None:
    factory = _SessionFactory()
    scheduler = SLACollectorScheduler(factory)

    await scheduler.start(collection_interval_seconds=0)
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert len(factory.sessions) >= 2, "the loop reused one session across passes"
    assert all(s.closed for s in factory.sessions), "a pass left its session open"


async def test_billing_sync_opens_and_closes_a_session_for_each_pass() -> None:
    # An empty miner list ends sync_all_miners_usage at its early return.
    factory = _SessionFactory([[_StubResult(rows=[])] for _ in range(8)])
    scheduler = BillingIntegrationScheduler(factory)

    await scheduler.start(sync_interval_hours=0)
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert len(factory.sessions) >= 2
    assert all(s.closed for s in factory.sessions)


# --- shutdown --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scheduler_cls", "kwargs"),
    [
        (SLACollectorScheduler, {"collection_interval_seconds": 3600}),
        (BillingIntegrationScheduler, {"sync_interval_hours": 24}),
    ],
)
async def test_stop_does_not_leave_the_loop_parked_in_a_sleep(scheduler_cls: type, kwargs: dict[str, Any]) -> None:
    """The interval is long enough that only cancellation can end the task."""
    factory = _SessionFactory([[_StubResult(rows=[])]])
    scheduler = scheduler_cls(factory)

    await scheduler.start(**kwargs)
    await asyncio.sleep(0.02)
    task = scheduler._task
    assert task is not None and not task.done()

    await asyncio.wait_for(scheduler.stop(), timeout=1.0)

    assert task.done(), "stop() returned with the loop task still pending"
    assert scheduler.running is False
    assert scheduler._task is None


@pytest.mark.parametrize("scheduler_cls", [SLACollectorScheduler, BillingIntegrationScheduler])
async def test_stop_is_safe_before_start(scheduler_cls: type) -> None:
    await scheduler_cls(_SessionFactory()).stop()


@pytest.mark.parametrize("scheduler_cls", [SLACollectorScheduler, BillingIntegrationScheduler])
async def test_start_twice_runs_one_loop(scheduler_cls: type) -> None:
    factory = _SessionFactory([[_StubResult(rows=[])] for _ in range(4)])
    scheduler = scheduler_cls(factory)

    await scheduler.start()
    first = scheduler._task
    await scheduler.start()

    assert scheduler._task is first
    await scheduler.stop()


# --- honest billing accounting ---------------------------------------------------


def _one_miner_with_usage() -> _Session:
    """A miner with two hours of compute, so all three quantities are > 0."""
    return _Session(
        [
            _StubResult(rows=[SimpleNamespace(miner_id="miner-1")]),
            _StubResult(scalar_value=42),
            _StubResult(rows=[SimpleNamespace(miner_id="miner-1", eta_ms=7_200_000)]),
        ]
    )


async def test_a_sync_whose_events_all_fail_is_not_reported_as_processed() -> None:
    """The V23-101 defect: three dropped events read as three usage records."""
    integration = BillingIntegration(_one_miner_with_usage())

    async def _refuse(_event: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("All connection attempts failed")

    integration._send_billing_event = _refuse  # type: ignore[method-assign]

    result = await integration.sync_all_miners_usage(hours_back=2)

    assert result["miners_processed"] == 0
    assert result["miners_failed"] == 1
    assert result["total_usage_records"] == 0


async def test_a_sync_whose_events_land_is_reported_as_processed() -> None:
    """The success path still counts, so the test above is about the failure."""
    integration = BillingIntegration(_one_miner_with_usage())
    sent: list[dict[str, Any]] = []

    async def _accept(event: dict[str, Any]) -> dict[str, Any]:
        sent.append(event)
        return {"status": "recorded"}

    integration._send_billing_event = _accept  # type: ignore[method-assign]

    result = await integration.sync_all_miners_usage(hours_back=2)

    assert result["miners_processed"] == 1
    assert result["miners_failed"] == 0
    assert result["total_usage_records"] == 3
    assert len(sent) == 3


async def test_record_usage_still_swallows_so_its_other_callers_are_unchanged() -> None:
    """record_usage keeps its reporting contract; send_usage is the raising one."""
    integration = BillingIntegration(_Session())

    async def _refuse(_event: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("nope")

    integration._send_billing_event = _refuse  # type: ignore[method-assign]

    swallowed = await integration.record_usage(tenant_id="t", resource_type="gpu_hours", quantity=Decimal("1"))
    assert swallowed["status"] == "failed"

    with pytest.raises(ConnectionError):
        await integration.send_usage(tenant_id="t", resource_type="gpu_hours", quantity=Decimal("1"))


# --- the wiring ------------------------------------------------------------------


def test_both_schedulers_are_constructed_by_the_app_lifespan() -> None:
    """The finding itself: neither class was named anywhere but its own def."""
    source = MAIN_PY.read_text(encoding="utf-8")
    for name in ("SLACollectorScheduler", "BillingIntegrationScheduler"):
        assert f"{name}(" in source, f"{name} is still constructed nowhere"


def test_every_poolhub_scheduler_class_is_wired_into_the_app() -> None:
    """A scheduler added later is caught the day it lands, not months after."""
    main_source = MAIN_PY.read_text(encoding="utf-8")
    unwired = []
    for path in POOLHUB_SRC.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Scheduler"):
                if f"{node.name}(" not in main_source:
                    unwired.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {node.name}")
    assert unwired == [], f"scheduler classes nothing starts: {unwired}"


def test_the_lifespan_stops_what_it_starts() -> None:
    source = MAIN_PY.read_text(encoding="utf-8")
    assert ".stop()" in source, "schedulers are started but never stopped on shutdown"
    assert "finally:" in source


def test_the_interval_settings_are_read_by_the_app() -> None:
    """Both fields existed for these loops and nothing had ever read either one."""
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "settings.sla_collection_interval_seconds" in source
    assert "settings.billing_sync_interval_hours" in source


# --- the flags -------------------------------------------------------------------


def test_both_schedulers_are_off_by_default() -> None:
    """Neither loop has ever run on a deployment; an upgrade must not start one."""
    fields = Settings.model_fields
    assert fields["enable_sla_collection"].default is False
    assert fields["enable_billing_sync"].default is False


def test_the_flags_are_settable_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POOLHUB_ENABLE_SLA_COLLECTION", "true")
    monkeypatch.setenv("POOLHUB_ENABLE_BILLING_SYNC", "true")
    settings = Settings()
    assert settings.enable_sla_collection is True
    assert settings.enable_billing_sync is True


def test_the_lifespan_gates_each_scheduler_on_its_own_flag() -> None:
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "settings.enable_sla_collection" in source
    assert "settings.enable_billing_sync" in source


# --- the endpoint billing sync posts to ------------------------------------------


def test_the_billing_endpoint_is_documented_as_absent_from_coordinator_api() -> None:
    """Turning billing sync on today can only produce failures; say so in the docs.

    ``_send_billing_event`` posts to ``/api/billing/usage``.  coordinator-api
    serves no such route -- everything it publishes is under ``/v1`` -- so this
    test pins the fact and the warning together: if the route is ever added, the
    spec assertion fails and the warning gets removed with it.
    """
    spec = json.loads((REPO_ROOT / "docs/api/coordinator/openapi.json").read_text(encoding="utf-8"))
    billing_paths = [p for p in spec.get("paths", {}) if "billing" in p or "usage" in p]
    assert billing_paths == [], f"coordinator-api now serves {billing_paths}; drop the warning in sla-monitoring.md"

    doc = (REPO_ROOT / "docs/deployment/sla-monitoring.md").read_text(encoding="utf-8")
    # Not merely that the path is named -- the doc named it before this change, as a
    # working integration ("Pool-hub sends usage events to ... `/api/billing/usage`").
    # What has to be there is the warning, next to the flag that starts the loop.
    assert "does not serve" in doc or "coordinator-api does not" in doc, "the doc still presents the route as working"
    assert "check that the coordinator named by" in doc, "no warning where operators enable POOLHUB_ENABLE_BILLING_SYNC"


def test_the_posted_path_has_not_silently_changed() -> None:
    source = (POOLHUB_SRC / "services/billing_integration.py").read_text(encoding="utf-8")
    assert re.search(r'client\.post\(\s*"/api/billing/usage"', source), "update the doc warning: the billing path moved"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
