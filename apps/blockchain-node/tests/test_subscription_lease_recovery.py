"""Regression tests for missing-lease re-registration in SubscriptionClient.

#705: a heartbeat 404 (lease gone server-side) only switched the client to
pull mode and retried the dead lease forever, and a WebSocket close 1008
("no valid lease") retried the socket with the same missing lease. Both
must route back into the registration path.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
import websockets
from aitbc_chain.subscription_client import SubscriptionClient
from websockets.frames import Close

HUB = "http://hub-a:8202"
NODE = "node-1"
CHAIN = "bc-2"


def _status_response(status: int) -> httpx.Response:
    request = httpx.Request("POST", f"{HUB}/rpc/heartbeat")
    return httpx.Response(status, request=request)


def _close_1008() -> websockets.exceptions.ConnectionClosed:
    return websockets.exceptions.ConnectionClosedError(Close(1008, "no valid lease"), None)


@pytest.mark.asyncio
async def test_heartbeat_404_triggers_re_registration() -> None:
    client = SubscriptionClient(HUB, NODE, CHAIN)
    client._client.post = AsyncMock(return_value=_status_response(404))  # type: ignore[method-assign]
    client._subscribe = AsyncMock(return_value=True)  # type: ignore[method-assign]

    assert await client._heartbeat() is True
    client._subscribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_non_404_does_not_reregister() -> None:
    client = SubscriptionClient(HUB, NODE, CHAIN)
    client._client.post = AsyncMock(return_value=_status_response(503))  # type: ignore[method-assign]
    client._subscribe = AsyncMock(return_value=True)  # type: ignore[method-assign]

    assert await client._heartbeat() is False
    client._subscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_404_failed_reregister_falls_back_to_pull() -> None:
    client = SubscriptionClient(HUB, NODE, CHAIN)
    client._client.post = AsyncMock(return_value=_status_response(404))  # type: ignore[method-assign]
    client._subscribe = AsyncMock(return_value=False)  # type: ignore[method-assign]

    assert await client._heartbeat() is False
    client._subscribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_websocket_1008_returns_to_registration_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Close 1008 must exit the receive loop, not retry the dead lease."""
    client = SubscriptionClient(HUB, NODE, CHAIN)
    client._running = True
    connect_calls = 0

    def fake_connect(*args: object, **kwargs: object) -> object:
        nonlocal connect_calls
        connect_calls += 1
        raise _close_1008()

    monkeypatch.setattr(websockets, "connect", fake_connect)
    # The pre-fix code slept 5s and retried inside the loop — a 1s timeout
    # proves the function now returns promptly instead.
    await asyncio.wait_for(client._receive_via_websocket(), timeout=1.0)
    assert connect_calls == 1


@pytest.mark.asyncio
async def test_subscription_loop_reregisters_after_receive_return(monkeypatch: pytest.MonkeyPatch) -> None:
    """After _receive_via_websocket returns, the loop re-enters _subscribe."""
    client = SubscriptionClient(HUB, NODE, CHAIN)
    client._running = True
    client._transport = "websocket"

    subscribe_calls = 0
    receive_calls = 0

    async def fake_subscribe() -> bool:
        nonlocal subscribe_calls
        subscribe_calls += 1
        return True

    async def fake_receive() -> None:
        # First receive cycle ends (the 1008 break); stop the loop after the
        # second so re-registration is observable.
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls >= 2:
            client._running = False

    client._subscribe = fake_subscribe  # type: ignore[method-assign]
    client._receive_via_websocket = fake_receive  # type: ignore[method-assign]

    await asyncio.wait_for(client._subscription_loop(), timeout=1.0)
    # subscribe → receive → subscribe → receive proves the loop re-enters the
    # registration path each time the receive loop returns.
    assert subscribe_calls == 2
    assert receive_calls == 2
