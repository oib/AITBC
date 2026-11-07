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
