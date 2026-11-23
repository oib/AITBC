"""#2753: transport-level RPC failures are warning-class, not error-class.

A routine ``aitbc-blockchain-rpc`` restart made every wallet monitor poll
fail with ``httpx.ConnectError`` ("All connection attempts failed") — four
ERROR lines in one cycle tripped AITBCJournalErrors even though the next
poll self-healed. ``is_transient_rpc_error`` classifies ``httpx.
TransportError`` (connect/timeout/pool/protocol — no response received)
so poll lanes log WARNING; real failures (HTTPStatusError, ValueError,
DB errors) still log ERROR.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from wallet_app.bridge import bridge_withdraw_monitor as wdm
from wallet_app.bridge import exchange_settlement_monitor as esm


def test_transient_rpc_error_classes() -> None:
    assert wdm.is_transient_rpc_error(httpx.ConnectError("All connection attempts failed"))
    assert wdm.is_transient_rpc_error(httpx.ConnectTimeout("timed out"))
    assert wdm.is_transient_rpc_error(httpx.PoolTimeout("pool exhausted"))
    assert wdm.is_transient_rpc_error(httpx.RemoteProtocolError("server disconnected"))


def test_non_transient_failures_stay_errors() -> None:
    assert not wdm.is_transient_rpc_error(httpx.HTTPStatusError("boom", request=None, response=None))
    assert not wdm.is_transient_rpc_error(ValueError("bad row"))
    assert not wdm.is_transient_rpc_error(RuntimeError("scan bug"))


@pytest.mark.asyncio
async def test_run_lane_transport_failure_warns_not_errors(caplog: pytest.LogCaptureFixture) -> None:
    async def _boom() -> None:
        raise httpx.ConnectError("All connection attempts failed")

    summary: dict = {}
    with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.exchange_settlement_monitor"):
        await esm._run_lane(summary, "locks", "Escrow lock scan", _boom())

    assert summary["locks"].startswith("failed:")
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not errors
    assert any("Escrow lock scan failed this poll" in r.getMessage() for r in warnings)


@pytest.mark.asyncio
async def test_run_lane_real_failure_still_errors(caplog: pytest.LogCaptureFixture) -> None:
    async def _boom() -> None:
        raise ValueError("corrupt settlement row")

    summary: dict = {}
    with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.exchange_settlement_monitor"):
        await esm._run_lane(summary, "locks", "Escrow lock scan", _boom())

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("Escrow lock scan failed this poll" in r.getMessage() for r in errors)
