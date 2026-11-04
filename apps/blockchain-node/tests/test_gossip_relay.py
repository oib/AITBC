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
