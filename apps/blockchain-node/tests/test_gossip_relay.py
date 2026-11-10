"""#1065 pins for the standalone gossip relay (aitbc_chain.gossip.relay).

Pre-fix: POST /gossip returned a dict (Starlette Route requires a Response,
so every publish ended in a 500 after logging "Published"), any channel could
be published without credentials, and the WebSocket subscriber did ``async
with`` on a coroutine so no message was ever delivered.
"""

from __future__ import annotations

import threading
import time

import pytest
from starlette.testclient import TestClient

from aitbc_chain.config import settings
from aitbc_chain.gossip import gossip_auth
from aitbc_chain.gossip.relay import create_app

VALIDATOR_KEY = "11" * 32  # secp256k1 private key, test-only


def _validator_address() -> str:
    from eth_keys import keys

    return keys.PrivateKey(bytes.fromhex(VALIDATOR_KEY)).public_key.to_checksum_address()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "validator_set", f'[{{"address": "{_validator_address()}"}}]')
    with TestClient(create_app()) as c:
        yield c


def test_restricted_publish_requires_auth(client: TestClient) -> None:
    resp = client.post("/gossip", json={"channel": "blocks.bc-2", "message": "x"})
    assert resp.status_code == 401


def test_unknown_channel_rejected(client: TestClient) -> None:
    resp = client.post("/gossip", json={"channel": "random", "message": "x"})
    assert resp.status_code == 403


def test_public_channel_publishes(client: TestClient) -> None:
    resp = client.post("/gossip", json={"channel": "transactions", "message": "x"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


def test_restricted_publish_with_validator_signature(client: TestClient) -> None:
    challenge = client.get("/gossip/challenge").json()
    address = _validator_address()
    signature = gossip_auth.sign_challenge(challenge["challenge"], address, challenge["timestamp"], VALIDATOR_KEY)
    resp = client.post(
        "/gossip",
        json={
            "channel": "blocks.bc-2",
            "message": "x",
            "address": address,
            "timestamp": challenge["timestamp"],
            "challenge": challenge["challenge"],
            "signature": signature,
        },
    )
    assert resp.status_code == 200


def test_websocket_delivers_published_message(client: TestClient) -> None:
    with client.websocket_connect("/ws?channel=transactions") as ws:
        time.sleep(0.05)  # let the subscribe() coroutine register
        client.post("/gossip", json={"channel": "transactions", "message": "hello"})

        # receive_text() has no timeout on this starlette — bound the wait
        # with a daemon thread so a broken subscribe fails, not hangs (#1065).
        received: list[str] = []

        def _recv() -> None:
            try:
                received.append(ws.receive_text())
            except Exception:
                pass

        t = threading.Thread(target=_recv, daemon=True)
        t.start()
        t.join(timeout=5)
        assert received == ["hello"], "no message delivered within 5s"


def test_restricted_subscribe_requires_auth(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws?channel=blocks.bc-2"):
            pass
    assert excinfo.value.code == 1008


def test_restricted_subscribe_with_validator_signature(client: TestClient) -> None:
    challenge = client.get("/gossip/challenge").json()
    address = _validator_address()
    signature = gossip_auth.sign_challenge(challenge["challenge"], address, challenge["timestamp"], VALIDATOR_KEY)
    qs = (
        f"channel=blocks.bc-2&address={address}&timestamp={challenge['timestamp']}"
        f"&challenge={challenge['challenge']}&signature={signature}"
    )
    with client.websocket_connect(f"/ws?{qs}"):
        pass  # accepted, not closed


@pytest.mark.asyncio
async def test_simple_broadcast_bounds_subscriber_queue() -> None:
    """#1537: a stalled subscriber must not grow memory or block publishers."""
    from aitbc_chain.gossip.relay import SimpleBroadcast

    bc = SimpleBroadcast()
    sub = await bc.subscribe("transactions")
    # Fill past the bound without consuming; publish must not block or raise.
    for i in range(SimpleBroadcast._MAX_QUEUE_SIZE + 10):
        await bc.publish("transactions", f"m{i}")
    assert sub.queue.qsize() == SimpleBroadcast._MAX_QUEUE_SIZE
    # The buffered head is preserved; only overflow messages are dropped.
    assert await sub.queue.get() == "m0"


# ---------------------------------------------------------------------------
# #1591: POST /gossip body cap, rate limit, non-dict body
# #1537/#1538: subscriber/channel registry caps, channel reaping, ws limits
# ---------------------------------------------------------------------------


def test_non_dict_json_body_rejected(client: TestClient) -> None:
    """#1591: a valid-JSON array body used to 500 on data.get()."""
    resp = client.post("/gossip", json=["not", "a", "dict"])
    assert resp.status_code == 400


def test_oversized_body_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """#1591: Content-Length over the cap is refused before the body is read."""
    monkeypatch.setattr(settings, "gossip_relay_max_body_bytes", 32)
    resp = client.post("/gossip", json={"channel": "transactions", "message": "x" * 100})
    assert resp.status_code == 413


def test_publish_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """#1591: unauthenticated public publishes are throttled per source IP."""
    from aitbc.security import RateLimiter

    from aitbc_chain.gossip import relay as relay_module

    monkeypatch.setattr(relay_module, "_publish_rate", RateLimiter(rate=1, per=60))
    assert client.post("/gossip", json={"channel": "transactions", "message": "a"}).status_code == 200
    assert client.post("/gossip", json={"channel": "transactions", "message": "b"}).status_code == 429


@pytest.mark.asyncio
async def test_simple_broadcast_channel_and_subscriber_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1537/#1538: invented dotted-subtopic names cannot grow the registry
    without bound — per-channel, per-registry and total caps all refuse."""
    from aitbc_chain.gossip.relay import BroadcastCapacityError, SimpleBroadcast

    bc = SimpleBroadcast()
    monkeypatch.setattr(SimpleBroadcast, "_MAX_SUBSCRIBERS_PER_CHANNEL", 2)
    monkeypatch.setattr(SimpleBroadcast, "_MAX_CHANNELS", 3)
    await bc.subscribe("transactions")
    await bc.subscribe("transactions")
    with pytest.raises(BroadcastCapacityError):
        await bc.subscribe("transactions")
    # Two more distinct channels fill the registry to the cap.
    await bc.subscribe("status")
    await bc.subscribe("mempool")
    with pytest.raises(BroadcastCapacityError):
        await bc.subscribe("transactions.extra")


@pytest.mark.asyncio
async def test_simple_broadcast_reaps_empty_channel() -> None:
    """#1538: a channel key is dropped when its last subscriber leaves —
    previously every invented subtopic stayed in _subscribers forever."""
    from aitbc_chain.gossip.relay import SimpleBroadcast

    bc = SimpleBroadcast()
    async with await bc.subscribe("status.ephemeral"):
        assert "status.ephemeral" in bc._subscribers
    assert "status.ephemeral" not in bc._subscribers


def test_websocket_unknown_channel_rejected(client: TestClient) -> None:
    """#1538: /ws subscribes were open to ANY channel string; unknown topics
    are now refused like POST /gossip refuses them."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws?channel=not-a-topic"):
            pass
    assert excinfo.value.code == 1008


def test_websocket_per_ip_cap(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """#1537: public subscribes need no credentials, so sockets per IP are
    capped like the node's /rpc/gossip/ws path."""
    from starlette.websockets import WebSocketDisconnect

    from aitbc_chain.gossip import relay as relay_module

    monkeypatch.setattr(relay_module, "_MAX_WS_CONNECTIONS_PER_IP", 1)
    with client.websocket_connect("/ws?channel=transactions"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws?channel=transactions"):
                pass


# ---------------------------------------------------------------------------
# #1128: scoped signatures + single-use challenges on the relay
# ---------------------------------------------------------------------------


def _signed_publish(client: TestClient, channel: str, message: object) -> dict:
    challenge = client.get("/gossip/challenge").json()
    address = _validator_address()
    scope = gossip_auth.publish_scope(channel, message)
    signature = gossip_auth.sign_challenge(challenge["challenge"], address, challenge["timestamp"], VALIDATOR_KEY, scope)
    return {
        "channel": channel,
        "message": message,
        "address": address,
        "timestamp": challenge["timestamp"],
        "challenge": challenge["challenge"],
        "signature": signature,
    }


def test_replay_of_signed_publish_rejected(client: TestClient) -> None:
    body = _signed_publish(client, "blocks.bc-2", {"h": "0xabc"})
    assert client.post("/gossip", json=body).status_code == 200
    # exact same response replayed: the challenge is consumed (#1128)
    assert client.post("/gossip", json=body).status_code == 401


def test_tampered_message_with_valid_challenge_rejected(client: TestClient) -> None:
    # sign a scope for message A, present message B — binding must catch it
    challenge = client.get("/gossip/challenge").json()
    address = _validator_address()
    scope = gossip_auth.publish_scope("blocks.bc-2", {"h": "0xabc"})
    signature = gossip_auth.sign_challenge(challenge["challenge"], address, challenge["timestamp"], VALIDATOR_KEY, scope)
    resp = client.post(
        "/gossip",
        json={
            "channel": "blocks.bc-2",
            "message": {"h": "0xdef"},
            "address": address,
            "timestamp": challenge["timestamp"],
            "challenge": challenge["challenge"],
            "signature": signature,
        },
    )
    assert resp.status_code == 401


def test_unscoped_signature_flag_compat(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    challenge = client.get("/gossip/challenge").json()
    address = _validator_address()
    signature = gossip_auth.sign_challenge(challenge["challenge"], address, challenge["timestamp"], VALIDATOR_KEY)
    body = {
        "channel": "blocks.bc-2",
        "message": "x",
        "address": address,
        "timestamp": challenge["timestamp"],
        "challenge": challenge["challenge"],
        "signature": signature,
    }
    monkeypatch.setattr(settings, "gossip_auth_require_scope", False)
    assert client.post("/gossip", json=body).status_code == 200

    challenge2 = client.get("/gossip/challenge").json()
    body["challenge"] = challenge2["challenge"]
    body["timestamp"] = challenge2["timestamp"]
    body["signature"] = gossip_auth.sign_challenge(challenge2["challenge"], address, challenge2["timestamp"], VALIDATOR_KEY)
    monkeypatch.setattr(settings, "gossip_auth_require_scope", True)
    assert client.post("/gossip", json=body).status_code == 401


def test_unscoped_subscribe_flag_compat(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.websockets import WebSocketDisconnect

    def _unscoped_ws_params() -> str:
        challenge = client.get("/gossip/challenge").json()
        address = _validator_address()
        signature = gossip_auth.sign_challenge(challenge["challenge"], address, challenge["timestamp"], VALIDATOR_KEY)
        return (
            f"channel=blocks.bc-2&address={address}&timestamp={challenge['timestamp']}"
            f"&challenge={challenge['challenge']}&signature={signature}"
        )

    # flag OFF: compatibility window — unscoped subscribe accepted
    monkeypatch.setattr(settings, "gossip_auth_require_scope", False)
    with client.websocket_connect(f"/ws?{_unscoped_ws_params()}"):
        pass

    # flag ON: unscoped subscribe refused
    monkeypatch.setattr(settings, "gossip_auth_require_scope", True)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(f"/ws?{_unscoped_ws_params()}"):
            pass
    assert excinfo.value.code == 1008
