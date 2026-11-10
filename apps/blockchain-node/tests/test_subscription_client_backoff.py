"""Regression tests for AUDIT-RETRY (#1576) backoff in SubscriptionClient.

The subscription loop and WebSocket reconnect path used fixed 30s/5s sleeps,
so every follower re-hit a struggling hub on the same cadence. Delays must
now grow exponentially with jitter via ExponentialBackoff and reset on
success.
"""

from __future__ import annotations

import asyncio

import pytest
import websockets
from aitbc_chain.subscription_client import SubscriptionClient
from aitbc.utils.time_utils import ExponentialBackoff
from websockets.frames import Close

HUB = "http://hub-a:8202"
NODE = "node-1"
CHAIN = "bc-2"


def _spy_backoff(backoff: ExponentialBackoff) -> list[float]:
    """Wrap next_delay to record every delay the loop asks for."""
    delays: list[float] = []
    orig = backoff.next_delay

    def spy() -> float:
        delay = orig()
        delays.append(delay)
        return delay

    backoff.next_delay = spy  # type: ignore[method-assign]
    return delays


@pytest.mark.asyncio
async def test_subscription_loop_uses_growing_backoff() -> None:
    client = SubscriptionClient(HUB, NODE, CHAIN)
    client._subscribe_backoff = ExponentialBackoff(base_delay=0.001, max_delay=0.01, jitter=0.0)
    delays = _spy_backoff(client._subscribe_backoff)

    subscribe_calls = 0

    async def failing_subscribe() -> bool:
        nonlocal subscribe_calls
        subscribe_calls += 1
        return False

    client._subscribe = failing_subscribe  # type: ignore[method-assign]
    client._running = True

    task = asyncio.create_task(client._subscription_loop())
    await asyncio.sleep(0.15)
    client._running = False
    await asyncio.wait_for(task, timeout=2)

    assert subscribe_calls >= 3
    # Exponential growth 1ms -> 2ms -> 4ms -> ... capped at 10ms.
    assert delays[0] == pytest.approx(0.001)
    assert delays[1] == pytest.approx(0.002)
    assert delays[2] == pytest.approx(0.004)
    assert all(d <= 0.01 for d in delays)


@pytest.mark.asyncio
async def test_websocket_reconnect_uses_backoff() -> None:
    client = SubscriptionClient(HUB, NODE, CHAIN)
    client._ws_backoff = ExponentialBackoff(base_delay=0.001, max_delay=0.01, jitter=0.0)
    delays = _spy_backoff(client._ws_backoff)
    client._running = True

    conn_closed = websockets.exceptions.ConnectionClosedError(Close(1011, "boom"), None)

    class _FailConnect:
        async def __aenter__(self):  # noqa: ANN204
            raise conn_closed

        async def __aexit__(self, *args):  # noqa: ANN002, ANN204
            return False

    import aitbc_chain.subscription_client as sc_mod

    orig_connect = sc_mod.websockets.connect
    sc_mod.websockets.connect = lambda *a, **k: _FailConnect()  # type: ignore[assignment]
    try:
        task = asyncio.create_task(client._receive_via_websocket())
        await asyncio.sleep(0.15)
        client._running = False
        await asyncio.wait_for(task, timeout=2)
    finally:
        sc_mod.websockets.connect = orig_connect  # type: ignore[assignment]

    assert len(delays) >= 3
    assert delays[0] == pytest.approx(0.001)
    assert delays[1] == pytest.approx(0.002)
    assert all(d <= 0.01 for d in delays)


@pytest.mark.asyncio
async def test_websocket_close_1008_still_breaks_to_resubscribe() -> None:
    """The 1008 policy close must keep its special path: return to the outer
    loop for lease re-registration instead of sleeping in the socket loop."""
    client = SubscriptionClient(HUB, NODE, CHAIN)
    client._ws_backoff = ExponentialBackoff(base_delay=0.001, max_delay=0.01, jitter=0.0)
    delays = _spy_backoff(client._ws_backoff)
    client._running = True

    conn_closed = websockets.exceptions.ConnectionClosedError(Close(1008, "no valid lease"), None)

    class _FailConnect:
        async def __aenter__(self):  # noqa: ANN204
            raise conn_closed

        async def __aexit__(self, *args):  # noqa: ANN002, ANN204
            return False

    import aitbc_chain.subscription_client as sc_mod

    orig_connect = sc_mod.websockets.connect
    sc_mod.websockets.connect = lambda *a, **k: _FailConnect()  # type: ignore[assignment]
    try:
        await asyncio.wait_for(client._receive_via_websocket(), timeout=2)
    finally:
        sc_mod.websockets.connect = orig_connect  # type: ignore[assignment]

    # 1008 breaks immediately — no reconnect sleep was consumed.
    assert delays == []
    assert client._sync_mode == "pull"
