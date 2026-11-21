"""#1860: Tests for ``AtomicSettlementCoordinator`` orchestration (v0.9.0 B8).

``settlement_coordinator.py`` had zero direct coverage: it wraps
``CrossChainSettlementService`` and drives create → lock → verify →
execute → settle, refunds on failure, and runs a background timeout
monitor. These tests exercise that orchestration with a recording stub
service (branch coverage of the coordinator itself) plus two tests
against the real service for the ``escrow_enabled`` gate and the
current retired-HTLC failure path.
"""

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

from aitbc_chain.config import settings  # noqa: E402
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
    """Async stub recording call order and injecting failures.

    Mirrors the public surface ``AtomicSettlementCoordinator`` consumes:
    ``create_escrow``, ``lock_escrow``, ``verify_lock``, ``execute_trade``,
    ``settle``, ``refund``, ``check_timeouts``.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.create_kwargs: dict = {}
        self.fail_on: set[str] = set()
        self.refund_error: Exception | None = None
        self.create_result: dict = {"escrow_id": "esc_fake1", "secret": "preimage-secret"}
        self.refund_result: dict = {
            "escrow_id": "esc_fake1",
            "status": "refunded",
            "tx_hash": None,
            "release_proof": None,
        }
        # Queue of check_timeouts outcomes: a list (refunded ids) or an
        # Exception instance to raise. Exhausted → returns [].
        self.timeout_script: list = []

    async def _record(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail_on:
            raise RuntimeError(f"{name} failed (injected)")

    async def create_escrow(self, **kwargs) -> dict:
        await self._record("create_escrow")
        self.create_kwargs = dict(kwargs)
        return dict(self.create_result)

    async def lock_escrow(self, escrow_id: str) -> dict:
        await self._record("lock_escrow")
        return {"escrow_id": escrow_id, "status": "locked"}

    async def verify_lock(self, escrow_id: str) -> dict:
        await self._record("verify_lock")
        return {"escrow_id": escrow_id, "status": "verified"}

    async def execute_trade(self, escrow_id: str) -> dict:
        await self._record("execute_trade")
        return {"escrow_id": escrow_id, "status": "completed"}

    async def settle(self, escrow_id: str, secret: str) -> dict:
        await self._record("settle")
        self.settle_secret = secret
        return {"escrow_id": escrow_id, "status": "completed"}

    async def refund(self, escrow_id: str) -> dict:
        self.calls.append("refund")
        self.refund_escrow_id = escrow_id
        if self.refund_error is not None:
            raise self.refund_error
        return dict(self.refund_result)

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


_RUN_KWARGS = {
    "trade_id": "trade-1",
    "source_chain": "ait-hub",
    "dest_chain": "ait-island-1",
    "sender": "alice",
    "recipient": "bob",
    "amount": 1000,
    "timeout_seconds": 3600,
}


# ---------------------------------------------------------------------------
# run_settlement — happy path and per-step failure semantics
# ---------------------------------------------------------------------------


class TestRunSettlement:
    async def test_happy_path_completes_in_order(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        result = await coordinator.run_settlement(**_RUN_KWARGS)

        assert result == {
            "escrow_id": "esc_fake1",
            "status": "completed",
            "secret": "preimage-secret",
        }
        assert fake_service.calls == [
            "create_escrow",
            "lock_escrow",
            "verify_lock",
            "execute_trade",
            "settle",
        ]
        # The secret returned by create_escrow is what settle reveals.
        assert fake_service.settle_secret == "preimage-secret"

    async def test_create_escrow_receives_all_trade_params(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        await coordinator.run_settlement(**_RUN_KWARGS)

        assert fake_service.create_kwargs == _RUN_KWARGS

    async def test_create_failure_returns_failed_without_refund(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        """If escrow creation itself fails there is nothing to refund —
        refund must not be attempted and no later step may run."""
        fake_service.fail_on = {"create_escrow"}

        result = await coordinator.run_settlement(**_RUN_KWARGS)

        assert result["status"] == "failed"
        assert result["escrow_id"] is None
        assert "create_escrow failed" in result["error"]
        assert fake_service.calls == ["create_escrow"]

    @pytest.mark.parametrize("step", ["lock_escrow", "verify_lock", "execute_trade", "settle"])
    async def test_mid_lifecycle_failure_refunds_created_escrow(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService, step: str
    ) -> None:
        """Any failure after create_escrow leaves the escrow for the
        monitor; the coordinator additionally attempts an immediate
        refund of the escrow it created."""
        fake_service.fail_on = {step}

        result = await coordinator.run_settlement(**_RUN_KWARGS)

        assert result["status"] == "failed"
        assert result["escrow_id"] == "esc_fake1"
        assert f"{step} failed" in result["error"]
        assert fake_service.calls[-1] == "refund"
        assert fake_service.refund_escrow_id == "esc_fake1"
        # Steps after the failing one never ran.
        order = ["create_escrow", "lock_escrow", "verify_lock", "execute_trade", "settle"]
        assert fake_service.calls[:-1] == order[: order.index(step) + 1]

    async def test_refund_failure_still_reports_original_error(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        """A failing compensating refund is logged but must not mask the
        original settlement error in the returned dict."""
        fake_service.fail_on = {"verify_lock"}
        fake_service.refund_error = ValueError("refund refused")

        result = await coordinator.run_settlement(**_RUN_KWARGS)

        assert result["status"] == "failed"
        assert "verify_lock failed" in result["error"]
        assert "refund refused" not in result["error"]

    async def test_missing_secret_defaults_to_empty_string(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        """create_escrow results without a ``secret`` key still settle —
        the coordinator tolerates the missing preimage (settle will then
        fail downstream on hashlock mismatch, which is the service's job)."""
        fake_service.create_result = {"escrow_id": "esc_nosecret"}

        result = await coordinator.run_settlement(**_RUN_KWARGS)

        assert result["status"] == "completed"
        assert result["secret"] == ""
        assert fake_service.settle_secret == ""


# ---------------------------------------------------------------------------
# run_refund — manual refund passthrough
# ---------------------------------------------------------------------------


class TestRunRefund:
    async def test_delegates_to_service(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        result = await coordinator.run_refund("esc_manual")

        assert result == fake_service.refund_result
        assert fake_service.calls == ["refund"]
        assert fake_service.refund_escrow_id == "esc_manual"

    async def test_service_error_propagates(
        self, coordinator: AtomicSettlementCoordinator, fake_service: _FakeSettlementService
    ) -> None:
        """run_refund does not swallow service errors — callers (e.g.
        dispute resolution) need the refusal."""
        fake_service.refund_error = ValueError("escrow is in terminal state")

        with pytest.raises(ValueError, match="terminal state"):
            await coordinator.run_refund("esc_done")


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


# ---------------------------------------------------------------------------
# Real CrossChainSettlementService — gates and the live failure path
# ---------------------------------------------------------------------------


class TestRealServiceIntegration:
    """Exercise the coordinator against the real settlement service.

    These need no DB for the disabled-flag case; the retired-HTLC case
    reuses the in-memory MockSession from test_settlement.py.
    """

    async def test_escrow_disabled_fails_before_any_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``settings.escrow_enabled=False`` is the dormant gate: every
        service method raises ``RuntimeError("Settlement not enabled")``
        before touching the DB, so run_settlement reports a clean failure
        with no escrow_id and no refund attempt."""
        monkeypatch.setattr(settings, "escrow_enabled", False)
        coordinator = AtomicSettlementCoordinator(chain_id="ait-hub")

        result = await coordinator.run_settlement(**_RUN_KWARGS)

        assert result["status"] == "failed"
        assert result["escrow_id"] is None
        assert "Settlement not enabled" in result["error"]

    async def test_real_service_create_refused_by_retired_htlc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """#2385: ``create_escrow`` fails fast with ``RetiredProtocolTransfer``
        (the HTLC rail cannot seal at block version ≥ 9), so the happy path
        cannot even mint an escrow — ``run_settlement`` reports ``failed``
        with no escrow_id, writes no row, and attempts no refund."""
        from contextlib import contextmanager

        from test_settlement import MockSession

        session = MockSession()

        @contextmanager
        def fake_scope(chain_id: str = ""):
            yield session

        monkeypatch.setattr("aitbc_chain.cross_chain.settlement.session_scope", fake_scope)
        monkeypatch.setattr(settings, "escrow_enabled", True)
        coordinator = AtomicSettlementCoordinator(chain_id="ait-hub")

        result = await coordinator.run_settlement(**_RUN_KWARGS)

        assert result["status"] == "failed"
        assert result["escrow_id"] is None
        assert "retired" in result["error"].lower() or "cannot seal" in result["error"]
        # Fail-fast: no escrow row was minted, no proof recorded.
        assert session.escrows == {}
        assert session.proofs == []
