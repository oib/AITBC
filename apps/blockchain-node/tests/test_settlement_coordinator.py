"""Exercise startup recovery and the legacy settlement timeout monitor lifecycle."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Ensure blockchain-node source is importable (same pattern as
# test_settlement.py — pytest also puts src/ on pythonpath via pyproject).
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aitbc_chain.cross_chain import settlement_coordinator as sc_module  # noqa: E402
from aitbc_chain.cross_chain.settlement_coordinator import (  # noqa: E402
    AtomicSettlementCoordinator,
)

# The app-level pytest config has no asyncio_mode=auto (the repo root's
# does), and sibling suites carry explicit marks — do the same so the
# file passes from either rootdir.
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Recording stub for CrossChainSettlementService
# ---------------------------------------------------------------------------


class _FakeSettlementService:
    """Record timeout checks and return or raise scripted outcomes."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        # Queue of check_timeouts outcomes: a list (refunded ids) or an
        # Exception instance to raise. Exhausted → returns [].
        self.timeout_script: list = []

    async def check_timeouts(self) -> list:
        self.calls.append("check_timeouts")
        if self.timeout_script:
            outcome = self.timeout_script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return []


@pytest.fixture
def coordinator() -> AtomicSettlementCoordinator:
    return AtomicSettlementCoordinator(chain_id="ait-hub")


@pytest.fixture
def fake_service(coordinator: AtomicSettlementCoordinator) -> _FakeSettlementService:
    fake = _FakeSettlementService()
    coordinator._service = fake  # type: ignore[assignment]
    return fake


# ---------------------------------------------------------------------------
# Monitor lifecycle — start_monitor / stop_monitor / _monitor_loop
# ---------------------------------------------------------------------------


class TestMonitor:
    async def test_start_monitor_runs_startup_recovery(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        """start_monitor performs one immediate check_timeouts sweep
        (startup recovery for escrows that timed out while the node was
        down) before launching the periodic loop."""
        fake_service.timeout_script = [["esc_timed_out"]]

        await coordinator.start_monitor()
        try:
            assert coordinator._running is True
            assert coordinator._task is not None
            assert fake_service.calls == ["check_timeouts"]
        finally:
            await coordinator.stop_monitor()

    async def test_start_monitor_is_idempotent(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        await coordinator.start_monitor()
        try:
            await coordinator.start_monitor()  # no-op while running
            assert fake_service.calls == ["check_timeouts"]  # one recovery sweep only
            assert coordinator._task is not None
        finally:
            await coordinator.stop_monitor()

    async def test_start_monitor_survives_recovery_scan_failure(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        """A check_timeouts failure during startup recovery is logged, not
        fatal — the periodic monitor must still come up."""
        fake_service.timeout_script = [RuntimeError("db gone"), []]

        await coordinator.start_monitor()
        try:
            assert coordinator._running is True
            assert coordinator._task is not None
            assert fake_service.calls == ["check_timeouts"]
        finally:
            await coordinator.stop_monitor()

    async def test_stop_monitor_when_not_running_is_noop(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        await coordinator.stop_monitor()
        assert coordinator._running is False
        assert coordinator._task is None
        assert fake_service.calls == []

    async def test_stop_monitor_cancels_task(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        await coordinator.start_monitor()
        task = coordinator._task
        assert task is not None

        await coordinator.stop_monitor()

        assert coordinator._running is False
        assert coordinator._task is None
        assert task.cancelled() or task.done()

    async def test_monitor_loop_ticks_and_swallows_check_errors(
        self,
        coordinator: AtomicSettlementCoordinator,
        fake_service: _FakeSettlementService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Each tick calls check_timeouts; a raising tick is logged and the
        loop keeps going until stopped."""
        monkeypatch.setattr(sc_module, "_MONITOR_INTERVAL_SECONDS", 0.01)
        # First entry is consumed by the startup recovery sweep; the rest
        # feed loop ticks — including a non-empty refund list and a raising
        # check, to cover both branches inside the loop body.
        fake_service.timeout_script = [
            [],
            ["esc_a"],
            RuntimeError("transient db error"),
            [],
            [],
            [],
        ]

        await coordinator.start_monitor()
        await asyncio.sleep(0.06)
        await coordinator.stop_monitor()

        assert coordinator._running is False
        ticks = fake_service.calls.count("check_timeouts")
        # 1 startup recovery + several loop ticks (>= 2 scripted + empties)
        assert ticks >= 4

    async def test_monitor_loop_sets_running_false_on_exit(
        self,
        coordinator: AtomicSettlementCoordinator,
        fake_service: _FakeSettlementService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The finally block clears _running so a crashed/cancelled loop
        cannot leave the coordinator believing a monitor is alive."""
        monkeypatch.setattr(sc_module, "_MONITOR_INTERVAL_SECONDS", 0.01)

        await coordinator.start_monitor()
        await asyncio.sleep(0.03)
        await coordinator.stop_monitor()

        # A second start after a clean stop must run recovery again.
        fake_service.calls.clear()
        await coordinator.start_monitor()
        try:
            assert fake_service.calls == ["check_timeouts"]
        finally:
            await coordinator.stop_monitor()

    async def test_monitor_loop_crash_clears_running(
        self,
        coordinator: AtomicSettlementCoordinator,
        fake_service: _FakeSettlementService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An exception escaping the loop body (here: the inter-tick
        ``asyncio.sleep``) hits the outer handler, clears ``_running`` in
        ``finally``, and finishes the task instead of wedging the
        coordinator in a half-running state."""
        monkeypatch.setattr(sc_module, "_MONITOR_INTERVAL_SECONDS", 0.01)
        real_sleep = asyncio.sleep

        async def explode_on_monitor_interval(delay: float) -> None:
            # Only the monitor's own 0.01s nap raises; the test's longer
            # sleeps (and anything else in the process) pass through.
            if delay == 0.01:
                raise RuntimeError("sleep exploded")
            await real_sleep(delay)

        monkeypatch.setattr(asyncio, "sleep", explode_on_monitor_interval)

        await coordinator.start_monitor()
        await real_sleep(0.05)  # let the monitor tick and crash

        assert coordinator._running is False
        assert coordinator._task is not None and coordinator._task.done()
        # stop_monitor is a no-op now (_running already False) — the dead
        # task is reaped by the task registry's done-callback logging.
        await coordinator.stop_monitor()
