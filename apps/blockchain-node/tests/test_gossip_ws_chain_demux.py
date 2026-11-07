"""Pins for gossip websocket chain demux (#1159, phase 1).

``?chain=<id>`` selects a per-chain GossipBroker; non-default chains resolve
their backend only from explicit per-chain config (``GOSSIP_BACKENDS`` /
chain-tagged ``GOSSIP_MESH_PEER_URLS``). Connection accounting is keyed on
(ip, chain) and auth scopes are chain-bound with a rollout-compat flag.
"""

from __future__ import annotations

import asyncio

from aitbc_chain.app import create_app
from aitbc_chain.config import settings
from aitbc_chain.gossip import gossip_broker
from aitbc_chain.gossip.backends.websocket import WebsocketGossipBackend
from aitbc_chain.rpc import websocket as websocket_module
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect


@pytest.fixture(autouse=True)
def _chain_demux_settings(monkeypatch: pytest.MonkeyPatch):
    """Two extra connectable chains via in-memory backends; clean broker cache."""
    websocket_module._chain_brokers.clear()
    monkeypatch.setattr(settings, "gossip_backends", "chain-a:memory,chain-b:memory")
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", 1_000_000)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 100)
    yield
    websocket_module._chain_brokers.clear()


def _wait_for(predicate, timeout: float = 3.0) -> bool:
    """Poll until ``predicate()`` holds: the server side of a closed test
    websocket releases its slot on the app's loop, a beat after the client."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _publish_on_backend(backend, topic: str, message: dict) -> None:
    """Publish directly to a chain broker's backend from the app's event loop."""
    loop = getattr(gossip_broker, "_app_loop", None)
    if loop is None:
        loop = asyncio.get_event_loop()

    async def _do_publish():
        await backend.publish(topic, message)

    fut = asyncio.run_coroutine_threadsafe(_do_publish(), loop)
    fut.result(timeout=5.0)


def _chain_backend(chain_id: str):
    broker = websocket_module._broker_for_chain(chain_id)
    assert broker is not None, f"no broker for {chain_id}"
    return broker._backend


def test_two_chain_topics_do_not_cross(monkeypatch: pytest.MonkeyPatch) -> None:
    """A publish on chain-a's broker reaches only chain-a subscribers."""
    backend_a = _chain_backend("chain-a")
    backend_b = _chain_backend("chain-b")
    payload_a1 = {"chain": "a", "n": 1}
    payload_b1 = {"chain": "b", "n": 1}
    payload_a2 = {"chain": "a", "n": 2}
    payload_b2 = {"chain": "b", "n": 2}

    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?topic=transactions&chain=chain-a") as ws_a:
            with client.websocket_connect("/rpc/gossip/ws?topic=transactions&chain=chain-b") as ws_b:
                _publish_on_backend(backend_a, "transactions", payload_a1)
                assert ws_a.receive_json() == payload_a1
                _publish_on_backend(backend_b, "transactions", payload_b1)
                assert ws_b.receive_json() == payload_b1
                # If B's message leaked into A's broker, ws_a's next frame
                # would be payload_b1 — the ordering pin catches the leak.
                _publish_on_backend(backend_a, "transactions", payload_a2)
                assert ws_a.receive_json() == payload_a2
                _publish_on_backend(backend_b, "transactions", payload_b2)
                assert ws_b.receive_json() == payload_b2


def test_missing_chain_rejected_on_multi_chain_host() -> None:
    """No ?chain= on a host serving >1 chain is a policy violation, not a default."""
    with TestClient(create_app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/rpc/gossip/ws?topic=transactions"):
                pass


def test_unknown_and_unbacked_chain_rejected() -> None:
    """?chain= for undeclared chains AND declared-but-unbacked chains both fail."""
    with TestClient(create_app()) as client:
        for bad in ("no-such-chain", "chain-c"):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(f"/rpc/gossip/ws?topic=transactions&chain={bad}"):
                    pass


def test_single_chain_default_still_accepts_no_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """With only the default chain connectable, legacy param-less connects work."""
    monkeypatch.setattr(settings, "gossip_backends", "")
    websocket_module._chain_brokers.clear()
    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?topic=transactions") as ws:
            payload = {"tx": "legacy"}
            backend = gossip_broker._backend
            loop = gossip_broker._app_loop or asyncio.get_event_loop()

            async def _pub():
                await backend.publish("transactions", payload)

            asyncio.run_coroutine_threadsafe(_pub(), loop).result(timeout=5.0)
            assert ws.receive_json() == payload


def test_ip_counter_isolated_per_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-IP connection cap is keyed (ip, chain): saturating chain-a
    does not consume chain-b's budget for the same source IP."""
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 1)
    headers = {"x-real-ip": "203.0.113.7"}
    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?topic=transactions&chain=chain-a", headers=headers):
            # Same IP, same chain, second connection -> over the cap.
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/rpc/gossip/ws?topic=transactions&chain=chain-a", headers=headers):
                    pass
            # Same IP, different chain -> independent counter, accepted.
            with client.websocket_connect("/rpc/gossip/ws?topic=transactions&chain=chain-b", headers=headers):
                pass


def test_ip_counter_entry_removed_at_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1256 (G4): a closed connection leaves no zero-count (ip, chain) key,
    while a still-open peer on the same key keeps its count."""
    # Starlette's TestClient peer is the literal host "testclient", not a
    # trusted proxy, so forwarded headers are ignored and that is the key.
    key_a = ("testclient", "chain-a")
    websocket_module._gossip_ip_connections.clear()
    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?topic=transactions&chain=chain-a"):
            with client.websocket_connect("/rpc/gossip/ws?topic=transactions&chain=chain-a"):
                assert websocket_module._gossip_ip_connections.get(key_a) == 2
            assert _wait_for(lambda: websocket_module._gossip_ip_connections.get(key_a) == 1)
        assert _wait_for(lambda: key_a not in websocket_module._gossip_ip_connections)
    assert websocket_module._gossip_ip_connections == {}


def test_rejected_connections_leave_no_counter_entry() -> None:
    """Unknown/unbacked chains must not insert (ip, chain) keys."""
    websocket_module._gossip_ip_connections.clear()
    with TestClient(create_app()) as client:
        for bad in ("no-such-chain", "chain-c"):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(f"/rpc/gossip/ws?topic=transactions&chain={bad}"):
                    pass
    assert websocket_module._gossip_ip_connections == {}


def test_release_ip_connection_unit() -> None:
    key = ("198.51.100.1", "chain-a")
    websocket_module._gossip_ip_connections.clear()
    websocket_module._gossip_ip_connections[key] = 2
    websocket_module._release_ip_connection(key)
    assert websocket_module._gossip_ip_connections[key] == 1
    websocket_module._release_ip_connection(key)
    assert key not in websocket_module._gossip_ip_connections
    websocket_module._release_ip_connection(key)  # already gone: no negative/KeyError
    assert key not in websocket_module._gossip_ip_connections


class _FakeBroker:
    def __init__(self, behaviour: str = "ok") -> None:
        self.behaviour = behaviour
        self.shutdown_calls = 0

    async def shutdown(self) -> None:
        self.shutdown_calls += 1
        if self.behaviour == "hang":
            await asyncio.sleep(60)
        if self.behaviour == "raise":
            raise RuntimeError("boom")


def test_shutdown_chain_brokers_isolates_failures_and_clears_registry() -> None:
    """#1256 (G3): every per-chain broker is shut down once; a raising or
    hanging broker neither blocks the others nor survives in the registry."""
    brokers = {"c-ok": _FakeBroker(), "c-raise": _FakeBroker("raise"), "c-hang": _FakeBroker("hang")}
    websocket_module._chain_brokers.update(brokers)  # type: ignore[arg-type]
    asyncio.run(websocket_module.shutdown_chain_brokers(timeout=0.2))
    assert all(b.shutdown_calls == 1 for b in brokers.values())
    assert websocket_module._chain_brokers == {}


def test_app_shutdown_closes_chain_brokers() -> None:
    """The lifespan wires shutdown_chain_brokers: leaving the app context
    shuts down brokers created while it ran."""
    fake = _FakeBroker()
    with TestClient(create_app()):
        websocket_module._chain_brokers["chain-fake"] = fake  # type: ignore[assignment]
    assert fake.shutdown_calls == 1
    assert "chain-fake" not in websocket_module._chain_brokers


def test_real_chain_broker_backend_shut_down_with_app() -> None:
    """End to end with a real lazily-created broker: its backend is shut down."""
    backend = _chain_backend("chain-a")
    calls: list[int] = []
    orig = backend.shutdown

    async def _spy() -> None:
        calls.append(1)
        await orig()

    backend.shutdown = _spy  # type: ignore[method-assign]
    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?topic=transactions&chain=chain-a"):
            pass
    assert calls == [1]
    assert websocket_module._chain_brokers == {}


def test_topic_namespaced_to_other_chain_rejected() -> None:
    """?chain=chain-a&topic=transactions.bc-2.test crosses chains explicitly."""
    with TestClient(create_app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/rpc/gossip/ws?topic=transactions.bc-2.test&chain=chain-a"):
                pass
        # Same-chain namespaced topic is fine.
        with client.websocket_connect("/rpc/gossip/ws?topic=transactions.chain-a&chain=chain-a") as ws:
            ws.send_json({"type": "noop"})


def test_channel_scope_binds_chain() -> None:
    from aitbc_chain.gossip.gossip_auth import channel_scope

    assert channel_scope("blocks.x", "chain-a") != channel_scope("blocks.x", "chain-b")
    assert channel_scope("blocks.x", "chain-a") != channel_scope("blocks.x")
    assert channel_scope("blocks.x") == channel_scope("blocks.x", "")


def _validator_key() -> tuple[str, str]:
    from eth_keys import keys

    key = "55" * 32
    address = keys.PrivateKey(bytes.fromhex(key)).public_key.to_checksum_address()
    return key, address


def _auth_response(challenge_frame: dict, address: str, key: str, scope: str) -> dict:
    from aitbc_chain.gossip import gossip_auth

    return {
        "type": "auth_response",
        "address": address,
        "signature": gossip_auth.sign_challenge(
            challenge_frame["challenge"], address, challenge_frame["timestamp"], key, scope
        ),
        "timestamp": challenge_frame["timestamp"],
        "challenge": challenge_frame["challenge"],
    }


def test_chain_bound_scope_accepted_and_cross_chain_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A signature scoped to chain-a authenticates on ?chain=chain-a; the
    same key signing for chain-b's scope is rejected on chain-a."""
    from aitbc_chain.gossip import gossip_auth

    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    key, address = _validator_key()
    monkeypatch.setattr(settings, "validator_set", f'[{{"address": "{address}"}}]')

    with TestClient(create_app()) as client:
        # Bound-to-this-chain scope: accepted.
        with client.websocket_connect("/rpc/gossip/ws?topic=blocks.test&chain=chain-a") as ws:
            challenge = ws.receive_json()
            ws.send_json(_auth_response(challenge, address, key, gossip_auth.channel_scope("blocks.test", "chain-a")))
            assert ws.receive_json().get("type") == "auth_ok"
        # Scope minted for chain-b: rejected on chain-a.
        with client.websocket_connect("/rpc/gossip/ws?topic=blocks.test&chain=chain-a") as ws:
            challenge = ws.receive_json()
            ws.send_json(_auth_response(challenge, address, key, gossip_auth.channel_scope("blocks.test", "chain-b")))
            msg = ws.receive_json()
            assert "error" in msg


def test_legacy_scope_accepted_until_flag_flips(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rollout compat: chain-less scope signatures still verify while
    gossip_auth_require_chain_scope is off; flipping it rejects them."""
    from aitbc_chain.gossip import gossip_auth

    key, address = _validator_key()
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    monkeypatch.setattr(settings, "validator_set", f'[{{"address": "{address}"}}]')

    def _attempt() -> dict:
        with TestClient(create_app()) as client:
            with client.websocket_connect("/rpc/gossip/ws?topic=blocks.test&chain=chain-a") as ws:
                challenge = ws.receive_json()
                ws.send_json(_auth_response(challenge, address, key, gossip_auth.channel_scope("blocks.test")))
                return ws.receive_json()

    monkeypatch.setattr(settings, "gossip_auth_require_chain_scope", False)
    assert _attempt().get("type") == "auth_ok"
    monkeypatch.setattr(settings, "gossip_auth_require_chain_scope", True)
    msg = _attempt()
    assert "error" in msg


@pytest.mark.parametrize("server_require", [False, True])
@pytest.mark.parametrize("dialer_sign", [False, True])
def test_sign_require_accept_matrix(monkeypatch: pytest.MonkeyPatch, dialer_sign: bool, server_require: bool) -> None:
    """#1255 accept matrix {dialer sign off,on} x {server require off,on}.

    The dialer's scope comes from the real ``WebsocketGossipBackend._auth_scope``
    under the dialer's flags; the server then verifies under its own flags.
    Accepted iff the server is lenient OR the dialer signed the chain scope.
    The legacy-accept counter moves exactly when the legacy fallback carried
    the handshake (sign off, require off).
    """
    from aitbc_chain.metrics import gossip_auth_legacy_scope_accepted_total as counter

    key, address = _validator_key()
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    monkeypatch.setattr(settings, "validator_set", f'[{{"address": "{address}"}}]')
    monkeypatch.setattr(settings, "chain_id", "chain-a")

    # Dialer host: sign flag only (its own require flag stays off).
    monkeypatch.setattr(settings, "gossip_auth_sign_chain_scope", dialer_sign)
    monkeypatch.setattr(settings, "gossip_auth_require_chain_scope", False)
    scope = WebsocketGossipBackend("wss://peer.example/rpc/gossip/ws", chain_id="chain-a")._auth_scope("blocks.test")

    # Server host: require flag only.
    monkeypatch.setattr(settings, "gossip_auth_sign_chain_scope", False)
    monkeypatch.setattr(settings, "gossip_auth_require_chain_scope", server_require)
    before = counter._value.get()
    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?topic=blocks.test&chain=chain-a") as ws:
            challenge = ws.receive_json()
            ws.send_json(_auth_response(challenge, address, key, scope))
            msg = ws.receive_json()

    accepted = msg.get("type") == "auth_ok"
    assert accepted is (dialer_sign or not server_require)
    legacy_carried = accepted and not dialer_sign
    assert counter._value.get() - before == (1 if legacy_carried else 0)


@pytest.mark.parametrize(
    ("sign", "require", "chain_bound"),
    [(False, False, False), (True, False, True), (False, True, True), (True, True, True)],
)
def test_dialer_scope_flag_truth_table(monkeypatch: pytest.MonkeyPatch, sign: bool, require: bool, chain_bound: bool) -> None:
    """Dialer signs chain scope iff sign OR require (require implies sign);
    both unset keeps the pre-#1255 legacy behaviour byte-for-byte."""
    from aitbc_chain.gossip import gossip_auth

    monkeypatch.setattr(settings, "gossip_auth_sign_chain_scope", sign)
    monkeypatch.setattr(settings, "gossip_auth_require_chain_scope", require)
    backend = WebsocketGossipBackend("wss://peer.example/rpc/gossip/ws", chain_id="chain-a")
    expected = gossip_auth.channel_scope("blocks", "chain-a") if chain_bound else gossip_auth.channel_scope("blocks")
    assert backend._auth_scope("blocks") == expected


def test_sign_flag_defaults_off() -> None:
    assert settings.gossip_auth_sign_chain_scope is False


def test_mesh_peer_url_chain_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    """chain-tagged GOSSIP_MESH_PEER_URLS entries route to their own chain only."""
    monkeypatch.setattr(
        settings,
        "gossip_mesh_peer_urls",
        "wss://peer1.example/rpc/gossip/ws,"
        "bc-2.test:wss://peer2.example/rpc/gossip/ws,"
        "wss://peer3.example/rpc/gossip/ws?chain=chain-b",
    )
    assert settings.mesh_peer_urls_for_chain(None) == ["wss://peer1.example/rpc/gossip/ws"]
    assert settings.mesh_peer_urls_for_chain("bc-2.test") == ["wss://peer2.example/rpc/gossip/ws"]
    assert settings.mesh_peer_urls_for_chain("chain-b") == ["wss://peer3.example/rpc/gossip/ws?chain=chain-b"]
    assert settings.mesh_peer_url_list() == ["wss://peer1.example/rpc/gossip/ws"]


def test_client_backend_sends_chain_param() -> None:
    """WebsocketGossipBackend includes chain= in the dial URL when bound."""
    bound = WebsocketGossipBackend("wss://peer.example/rpc/gossip/ws", chain_id="chain-a")
    url = bound._build_url("transactions")
    assert "chain=chain-a" in url
    assert "topic=transactions" in url
    # Chain already in the base URL is preserved without duplication.
    embedded = WebsocketGossipBackend("wss://peer.example/rpc/gossip/ws?chain=chain-b")
    url2 = embedded._build_url("blocks.x")
    assert url2.count("chain=") == 1
    assert "chain=chain-b" in url2
    # Legacy backend sends no chain param.
    legacy = WebsocketGossipBackend("wss://peer.example/rpc/gossip/ws")
    assert "chain=" not in legacy._build_url("transactions")
