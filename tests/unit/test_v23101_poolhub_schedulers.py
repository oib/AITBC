"""V23-101 — Pool Hub's SLA background scheduler had never been constructed.

``SLACollectorScheduler`` was defined with ``start()``, ``stop()`` and a loop,
and a repo-wide search found exactly one reference to it: its own ``class``
statement.  Pool Hub's lifespan created the engine, the Redis client and the
tables, and nothing else, so SLA metrics were collected only when someone
called ``POST /v1/sla/metrics/collect``, and ``sla_collection_interval_seconds``
-- a setting whose only purpose is to configure this loop -- was read by
nothing.

Three defects sat behind that, each reachable the moment the loop is started:

1. The scheduler took an already-constructed service, and therefore one
   ``AsyncSession``, held for the life of the process: one pooled connection
   pinned, one identity map growing, and a failed transaction carried from one
   pass into the next.
2. ``stop()`` cleared a flag.  The loop was parked in ``asyncio.sleep`` for up
   to a full interval, so shutdown returned with the task still pending.

(#3077 removed the second scheduler, ``BillingIntegrationScheduler``, along
with the whole billing surface: the ``/v1/sla/billing/*`` endpoints, the
``POOLHUB_ENABLE_BILLING_SYNC`` flag, and ``services/billing_integration.py``.
It POSTed usage to ``/api/billing/*`` routes coordinator-api does not serve,
so every event went nowhere while looking like a billing record.)
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest

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


# --- the shape of the scheduler ---------------------------------------------------


def test_a_scheduler_takes_a_session_factory_not_a_session() -> None:
    """A process-lifetime loop must be able to open a session per pass."""
    params = list(inspect.signature(SLACollectorScheduler.__init__).parameters)
    assert params == ["self", "session_factory"], f"SLACollectorScheduler{params}"


def test_a_scheduler_keeps_a_handle_on_its_task() -> None:
    """Without the handle there is nothing for stop() to cancel."""
    scheduler = SLACollectorScheduler(_SessionFactory())
    assert scheduler._task is None
    assert scheduler.running is False


# --- session per pass ------------------------------------------------------------


@pytest.mark.asyncio
async def test_sla_collection_opens_and_closes_a_session_for_each_pass() -> None:
    factory = _SessionFactory()
    scheduler = SLACollectorScheduler(factory)

    await scheduler.start(collection_interval_seconds=0)
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert len(factory.sessions) >= 2, "the loop reused one session across passes"
    assert all(s.closed for s in factory.sessions), "a pass left its session open"


# --- shutdown --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_does_not_leave_the_loop_parked_in_a_sleep() -> None:
    """The interval is long enough that only cancellation can end the task."""
    factory = _SessionFactory([[_StubResult(rows=[])]])
    scheduler = SLACollectorScheduler(factory)

    await scheduler.start(collection_interval_seconds=3600)
    await asyncio.sleep(0.02)
    task = scheduler._task
    assert task is not None and not task.done()

    await asyncio.wait_for(scheduler.stop(), timeout=1.0)

    assert task.done(), "stop() returned with the loop task still pending"
    assert scheduler.running is False
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_stop_is_safe_before_start() -> None:
    await SLACollectorScheduler(_SessionFactory()).stop()


@pytest.mark.asyncio
async def test_start_twice_runs_one_loop() -> None:
    factory = _SessionFactory([[_StubResult(rows=[])] for _ in range(4)])
    scheduler = SLACollectorScheduler(factory)

    await scheduler.start()
    first = scheduler._task
    await scheduler.start()

    assert scheduler._task is first
    await scheduler.stop()


# --- the wiring ------------------------------------------------------------------


def test_the_scheduler_is_constructed_by_the_app_lifespan() -> None:
    """The finding itself: the class was named nowhere but its own def."""
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "SLACollectorScheduler(" in source, "SLACollectorScheduler is still constructed nowhere"


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


def test_the_interval_setting_is_read_by_the_app() -> None:
    """The field existed for this loop and nothing had ever read it."""
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "settings.sla_collection_interval_seconds" in source


# --- the flag ---------------------------------------------------------------------


def test_the_scheduler_is_off_by_default() -> None:
    """The loop has never run on a deployment; an upgrade must not start one."""
    fields = Settings.model_fields
    assert fields["enable_sla_collection"].default is False


def test_the_flag_is_settable_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POOLHUB_ENABLE_SLA_COLLECTION", "true")
    settings = Settings()
    assert settings.enable_sla_collection is True


def test_the_lifespan_gates_the_scheduler_on_its_flag() -> None:
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "settings.enable_sla_collection" in source


# --- the billing surface stays gone (#3077) ----------------------------------------


def test_no_billing_routes_remain_on_the_sla_router() -> None:
    """The zombie middle state is the finding: endpoints that POST to routes
    coordinator-api does not serve must not come back."""
    from poolhub.app.routers import sla as sla_module

    billing_paths = [route.path for route in sla_module.router.routes if "billing" in route.path]
    assert billing_paths == [], f"billing routes reappeared: {billing_paths}"


def test_the_billing_service_and_flag_stay_removed() -> None:
    assert not (POOLHUB_SRC / "services/billing_integration.py").exists()
    fields = Settings.model_fields
    assert "enable_billing_sync" not in fields
    assert "billing_sync_interval_hours" not in fields


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
