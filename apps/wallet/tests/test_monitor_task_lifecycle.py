"""WALLET-BGTASK-1 (#1606): monitor tasks need error visibility + shutdown.

The four bridge monitor ``start_*`` helpers used bare ``asyncio.create_task``:
an unhandled exception vanished silently ("Task exception was never
retrieved" at best) and the ``while True`` loops outlived the app because
nobody kept a reference to cancel. They now go through
``aitbc.async_tasks.create_task_with_logging`` (done-callback exception
logging) and ``main.lifespan`` cancels every background task on shutdown.

These tests pin both halves: each start helper routes its loop through
``create_task_with_logging`` under a stable name, and a loop that raises
surfaces through the done-callback instead of disappearing.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

import wallet_app.bridge.bridge_monitor as bridge_monitor
import wallet_app.bridge.bridge_withdraw_monitor as withdraw_monitor
import wallet_app.bridge.exchange_settlement_monitor as exchange_monitor
import wallet_app.bridge.sell_escrow_monitor as sell_monitor


def _exploding_loop(calls: list[str], tag: str):
    async def _loop() -> None:
        calls.append(tag)
        raise RuntimeError(f"{tag} exploded")

    return _loop


async def _assert_logged_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    module: object,
    start_attr: str,
    loop_attr: str,
    expected_name: str,
    gate_patches: dict[str, object],
) -> None:
    """Drive one start_* helper with an exploding loop; assert the task is
    returned, raises, and the failure is logged by the done-callback."""
    calls: list[str] = []
    for attr, value in gate_patches.items():
        monkeypatch.setattr(module, attr, value)
    monkeypatch.setattr(module, loop_attr, _exploding_loop(calls, expected_name))

    start = getattr(module, start_attr)
    with caplog.at_level(logging.ERROR):
        task = start()
    assert task is not None, f"{start_attr} returned None despite enabled gates"

    with pytest.raises(RuntimeError, match="exploded"):
        await task
    assert calls == [expected_name], "monitor loop coroutine was never scheduled"
    # Let the done-callback (scheduled via call_soon) run before asserting.
    await asyncio.sleep(0)

    assert any(expected_name in record.getMessage() and record.levelno >= logging.ERROR for record in caplog.records), (
        f"no error log for failed monitor task {expected_name}: {[r.getMessage() for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_bridge_deposit_monitor_task_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _assert_logged_failure(
        monkeypatch,
        caplog,
        bridge_monitor,
        "start_monitoring",
        "monitor_loop",
        "bridge_deposit_monitor",
        {"BRIDGE_ENABLED": True, "DEPOSIT_MONITOR_ENABLED": True},
    )


@pytest.mark.asyncio
async def test_bridge_withdraw_monitor_task_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _assert_logged_failure(
        monkeypatch,
        caplog,
        withdraw_monitor,
        "start_withdrawal_monitoring",
        "withdrawal_monitor_loop",
        "bridge_withdraw_monitor",
        {"BRIDGE_ENABLED": True, "WITHDRAW_ENABLED": True},
    )


@pytest.mark.asyncio
async def test_exchange_settlement_monitor_task_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _assert_logged_failure(
        monkeypatch,
        caplog,
        exchange_monitor,
        "start_exchange_settlement_monitoring",
        "exchange_settlement_loop",
        "exchange_settlement_monitor",
        {
            "exchange_config_status": lambda: (True, ""),
            "_exchange_config": lambda: None,
        },
    )


@pytest.mark.asyncio
async def test_sell_escrow_monitor_task_is_logged(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    await _assert_logged_failure(
        monkeypatch,
        caplog,
        sell_monitor,
        "start_sell_monitoring",
        "sell_monitor_loop",
        "sell_escrow_monitor",
        {
            "sell_config_status": lambda: (True, ""),
            "_sell_config": lambda: None,
        },
    )


@pytest.mark.asyncio
async def test_monitor_tasks_cancel_cleanly() -> None:
    """The loops are ``while True`` — shutdown must cancel them, not leak."""
    started = asyncio.Event()

    async def _loop() -> None:
        started.set()
        await asyncio.sleep(3600)

    task = bridge_monitor.create_task_with_logging(_loop(), name="cancel_probe")
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
