from __future__ import annotations

import asyncio
from contextlib import ExitStack

from aitbc_chain.app import create_app
from aitbc_chain.config import settings
from aitbc_chain.gossip import gossip_broker
from aitbc_chain.rpc import websocket as websocket_module
from aitbc.security import RateLimiter
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocket, WebSocketDisconnect


@pytest.fixture(autouse=True)
def _gossip_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable auth and raise rate limits for the functional websocket tests."""
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", 1_000_000)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 100)
    monkeypatch.setattr(
        websocket_module,
        "_gossip_msg_rate",
        RateLimiter(rate=1_000_000, per=60),
    )


def _publish(topic: str, message: dict) -> None:
    """Publish directly to the in-memory backend from the app's event loop.

    This wakes websocket subscribers without depending on cross-loop-safe
    asyncio primitives in the broker's global dedup/priority path.
    """
    loop = getattr(gossip_broker, "_app_loop", None)
    if loop is None:
        loop = asyncio.get_event_loop()

    async def _do_publish():
        backend = gossip_broker._backend
        if backend is None:
            raise RuntimeError("Gossip broker has no backend")
        await backend.publish(topic, message)

    fut = asyncio.run_coroutine_threadsafe(_do_publish(), loop)
    fut.result(timeout=5.0)


def test_gossip_websocket_public_topic_stream() -> None:
    """The /rpc/gossip/ws endpoint supports arbitrary public topics."""
    topic = "transactions"
    with TestClient(create_app()) as client:
        with client.websocket_connect(f"/rpc/gossip/ws?topic={topic}") as websocket:
            payload = {
                "tx_hash": "0x" + "b" * 64,
                "sender": "alice",
                "recipient": "carol",
                "payload": {"amount": 2},
                "nonce": 7,
                "fee": 1,
                "type": "TRANSFER",
            }
            _publish(topic, payload)
            message = websocket.receive_json()
            assert message == payload


def test_gossip_websocket_multiple_subscribers_receive_all_payloads() -> None:
    topic = "transactions"
    with TestClient(create_app()) as client, ExitStack() as stack:
        sockets = [stack.enter_context(client.websocket_connect(f"/rpc/gossip/ws?topic={topic}")) for _ in range(3)]

        payloads = [
            {
                "tx_hash": "0x" + "b" * 64,
                "sender": "alice",
                "recipient": f"user-{i}",
                "payload": {"amount": i},
                "nonce": i,
                "fee": 1,
                "type": "TRANSFER",
            }
            for i in range(5)
        ]

        for payload in payloads:
            _publish(topic, payload)

        for socket in sockets:
            received = [socket.receive_json() for _ in payloads]
            assert received == payloads

        final_payload = {
            "tx_hash": "0x" + "f" * 64,
            "sender": "alice",
            "recipient": "zoe",
            "payload": {"amount": 99},
            "nonce": 99,
            "fee": 1,
            "type": "TRANSFER",
        }
        _publish(topic, final_payload)

        for socket in sockets:
            assert socket.receive_json() == final_payload


def test_gossip_websocket_high_volume_load() -> None:
    message_count = 40
    subscriber_count = 4
    topic = "transactions"

    with TestClient(create_app()) as client, ExitStack() as stack:
        sockets = [
            stack.enter_context(client.websocket_connect(f"/rpc/gossip/ws?topic={topic}")) for _ in range(subscriber_count)
        ]

        payloads = []
        for i in range(message_count):
            payload = {
                "tx_hash": "0x" + f"{i + 100:064x}",
                "sender": "alice",
                "recipient": f"user-{i}",
                "payload": {"amount": i},
                "nonce": i,
                "fee": 1,
                "type": "TRANSFER",
            }
            payloads.append(payload)
            _publish(topic, payload)

        for socket in sockets:
            received = [socket.receive_json() for _ in payloads]
            assert received == payloads


def test_gossip_websocket_topic_isolation() -> None:
    """Subscribers to one gossip topic must not receive messages from another."""
    topic_a = "transactions"
    topic_b = "status.ait-mainnet"
    with TestClient(create_app()) as client:
        with client.websocket_connect(f"/rpc/gossip/ws?topic={topic_a}") as ws_a:
            with client.websocket_connect(f"/rpc/gossip/ws?topic={topic_b}") as ws_b:
                _publish(topic_a, {"msg": "for a"})
                assert ws_a.receive_json() == {"msg": "for a"}
                _publish(topic_b, {"msg": "for b"})
                assert ws_b.receive_json() == {"msg": "for b"}


def test_gossip_websocket_missing_topic_rejects() -> None:
    """The endpoint requires a topic query parameter."""
    with TestClient(create_app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/rpc/gossip/ws"):
                pass


def test_gossip_websocket_publish_failure_keeps_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broker publish failure drops the message but must not close the conn.

    Regression for the 2026-09-27 partition test: an ACL-denied blocks.*
    publish tore down the whole socket and churned the attestation
    transport. The fix catches the publish error only — the socket stays
    open and ``gossip_broker_publish_failed_total`` counts the drop.
    """
    from unittest.mock import AsyncMock

    from aitbc_chain.metrics import metrics_registry

    metrics_registry.reset()
    monkeypatch.setattr(gossip_broker, "publish", AsyncMock(side_effect=RuntimeError("NOPERM")))

    topic = "transactions"
    with TestClient(create_app()) as client:
        with client.websocket_connect(f"/rpc/gossip/ws?topic={topic}") as websocket:
            # This publish hits the patched (failing) broker and is dropped.
            websocket.send_json({"tx_hash": "0x" + "a" * 64, "type": "TRANSFER"})

            # The receive path must still work — the socket is alive when a
            # backend message arrives and is delivered.
            payload = {"tx_hash": "0x" + "c" * 64, "type": "TRANSFER"}
            _publish(topic, payload)
            assert websocket.receive_json() == payload

    assert "gossip_broker_publish_failed_total 1.0" in metrics_registry.render_prometheus()


def test_gossip_websocket_unauthorized_publish_still_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth failures still close: the publish-failure catch must not widen.

    A non-validator publish to a restricted topic without completing the
    challenge/response gets the error frame and a 1008 close.
    """
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    monkeypatch.setattr(
        settings,
        "validator_set",
        '[{"address": "0x1111111111111111111111111111111111111111"}]',
    )

    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?topic=blocks.test") as websocket:
            challenge = websocket.receive_json()
            assert challenge["type"] == "auth_challenge"
            websocket.send_json({"type": "block", "hash": "0x" + "d" * 64})
            error = websocket.receive_json()
            assert "authentication required" in error["error"].lower()
            with pytest.raises(WebSocketDisconnect) as excinfo:
                websocket.receive_json()
            assert excinfo.value.code == 1008


def test_gossip_websocket_bad_auth_response_still_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed challenge/response closes the conn, unaffected by the publish catch."""
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    monkeypatch.setattr(
        settings,
        "validator_set",
        '[{"address": "0x1111111111111111111111111111111111111111"}]',
    )

    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?topic=blocks.test") as websocket:
            websocket.receive_json()  # auth_challenge
            websocket.send_json(
                {
                    "type": "auth_response",
                    "address": "0x2222222222222222222222222222222222222222",  # not in the set
                    "signature": "ab" * 65,
                    "challenge": "bogus",
                    "timestamp": 0.0,
                }
            )
            error = websocket.receive_json()
            assert "not a validator" in error["error"].lower()
            with pytest.raises(WebSocketDisconnect) as excinfo:
                websocket.receive_json()
            assert excinfo.value.code == 1008


def test_gossip_websocket_scoped_auth_and_replay_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1128: a valid scoped auth_response is accepted once; replay fails."""
    from aitbc_chain.gossip import gossip_auth

    key = "33" * 32
    from eth_keys import keys

    address = keys.PrivateKey(bytes.fromhex(key)).public_key.to_checksum_address()
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    monkeypatch.setattr(settings, "gossip_auth_require_scope", False)
    monkeypatch.setattr(settings, "validator_set", f'[{{"address": "{address}"}}]')

    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?topic=blocks.test") as websocket:
            challenge = websocket.receive_json()
            assert challenge["type"] == "auth_challenge"
            scope = gossip_auth.channel_scope("blocks.test")
            signature = gossip_auth.sign_challenge(challenge["challenge"], address, challenge["timestamp"], key, scope)
            response = {
                "type": "auth_response",
                "address": address,
                "signature": signature,
                "timestamp": challenge["timestamp"],
                "challenge": challenge["challenge"],
            }
            websocket.send_json(response)
            ok = websocket.receive_json()
            assert ok.get("type") == "auth_ok"
            # replay of the identical response: the challenge was consumed
            websocket.send_json(response)

            msg = websocket.receive_json()
            assert "error" in msg or msg.get("type") != "auth_ok"


def test_gossip_websocket_unscoped_auth_flag_on_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1128: require_scope ON refuses an unscoped auth_response; OFF accepts it."""
    from aitbc_chain.gossip import gossip_auth

    key = "44" * 32
    from eth_keys import keys

    address = keys.PrivateKey(bytes.fromhex(key)).public_key.to_checksum_address()
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    monkeypatch.setattr(settings, "validator_set", f'[{{"address": "{address}"}}]')

    def _try(flag: bool) -> dict:
        monkeypatch.setattr(settings, "gossip_auth_require_scope", flag)
        with TestClient(create_app()) as client:
            with client.websocket_connect("/rpc/gossip/ws?topic=blocks.test") as websocket:
                challenge = websocket.receive_json()
                signature = gossip_auth.sign_challenge(challenge["challenge"], address, challenge["timestamp"], key)
                websocket.send_json(
                    {
                        "type": "auth_response",
                        "address": address,
                        "signature": signature,
                        "timestamp": challenge["timestamp"],
                        "challenge": challenge["challenge"],
                    }
                )
                return websocket.receive_json()

    assert _try(False).get("type") == "auth_ok"
    assert "error" in _try(True)


def _gossip_ws_scope(client_ip: str) -> dict:
    return {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/rpc/gossip/ws",
        "raw_path": b"/rpc/gossip/ws",
        "query_string": b"topic=transactions",
        "root_path": "",
        "headers": [],
        "client": (client_ip, 4444),
        "server": ("testserver", 80),
        "subprotocols": [],
    }


async def _empty_receive() -> dict:
    return {"type": "websocket.disconnect"}


async def _empty_send(message: dict) -> None:
    return None


def _gossip_ws(client_ip: str) -> WebSocket:
    return WebSocket(_gossip_ws_scope(client_ip), receive=_empty_receive, send=_empty_send)


async def _noop(*args: object, **kwargs: object) -> None:
    return None


async def _receive_disconnect() -> str:
    raise WebSocketDisconnect()


async def _send_json_noop(message: dict) -> None:
    return None


async def _hang_forever(*args: object, **kwargs: object) -> None:
    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_gossip_websocket_hung_close_still_releases_ip_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1158: a client that vanishes during teardown close must not strand the count.

    ``websocket.close()`` is bounded by ``asyncio.wait_for``; without the
    bound a hung close leaves ``_gossip_ip_connections`` inflated forever.
    """
    monkeypatch.setattr(websocket_module, "_GOSSIP_WS_OP_TIMEOUT", 0.05)
    ip = "198.51.100.23"
    websocket_module._gossip_ip_connections.pop(ip, None)

    ws = _gossip_ws(ip)
    ws.accept = _noop  # type: ignore[method-assign]
    ws.receive_text = _receive_disconnect  # type: ignore[method-assign]
    ws.send_json = _send_json_noop  # type: ignore[method-assign]
    ws.close = _hang_forever  # type: ignore[method-assign]

    try:
        await asyncio.wait_for(websocket_module.gossip_websocket(ws), timeout=5.0)
        assert websocket_module._gossip_ip_connections.get(ip, 0) == 0
    finally:
        websocket_module._gossip_ip_connections.pop(ip, None)


@pytest.mark.asyncio
async def test_gossip_websocket_hung_send_still_releases_ip_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1165: a peer that stops reading must not park the broker->client forwarder.

    ``send_json`` is bounded by ``_GOSSIP_WS_OP_TIMEOUT``; without the bound a
    hung send leaves the forwarder (and the per-IP slot) wedged forever. The
    client side stays connected (receive hangs) so the broker->client send is
    the path under test; subscription.close() must still run on unwind.
    """
    monkeypatch.setattr(websocket_module, "_GOSSIP_WS_OP_TIMEOUT", 0.05)
    ip = "198.51.100.25"
    websocket_module._gossip_ip_connections.pop(ip, None)
    closed: list[bool] = []

    class _Subscription:
        def __aiter__(self):
            async def _gen():
                yield {"type": "test"}
                await asyncio.Event().wait()

            return _gen()

        def close(self) -> None:
            closed.append(True)

    async def _subscribe(topic: str, max_queue_size: int = 100) -> _Subscription:
        return _Subscription()

    monkeypatch.setattr(websocket_module.gossip_broker, "subscribe", _subscribe)

    ws = _gossip_ws(ip)
    ws.accept = _noop  # type: ignore[method-assign]
    ws.receive_text = _hang_forever  # type: ignore[method-assign]
    ws.send_json = _hang_forever  # type: ignore[method-assign]
    ws.close = _noop  # type: ignore[method-assign]

    try:
        await asyncio.wait_for(websocket_module.gossip_websocket(ws), timeout=5.0)
        assert websocket_module._gossip_ip_connections.get(ip, 0) == 0
        assert closed == [True]
    finally:
        websocket_module._gossip_ip_connections.pop(ip, None)


@pytest.mark.asyncio
async def test_gossip_websocket_hung_accept_still_releases_ip_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1158: a client that never completes the accept handshake must not strand the count."""
    monkeypatch.setattr(websocket_module, "_GOSSIP_WS_OP_TIMEOUT", 0.05)
    ip = "198.51.100.24"
    websocket_module._gossip_ip_connections.pop(ip, None)

    ws = _gossip_ws(ip)
    ws.accept = _hang_forever  # type: ignore[method-assign]
    ws.receive_text = _receive_disconnect  # type: ignore[method-assign]
    ws.send_json = _send_json_noop  # type: ignore[method-assign]
    ws.close = _noop  # type: ignore[method-assign]

    try:
        await asyncio.wait_for(websocket_module.gossip_websocket(ws), timeout=5.0)
        assert websocket_module._gossip_ip_connections.get(ip, 0) == 0
    finally:
        websocket_module._gossip_ip_connections.pop(ip, None)
