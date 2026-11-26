"""Pins for #3028 (AUTHZ-TRADING-WS-NODEID-SELFASSERT-1).

``TRADING_API_KEY`` is a single shared service key, so ``node_id`` in the
subscribe/heartbeat bodies and the first WS frame is self-asserted. Leases
now carry a bearer token: ``POST /v1/trading/offers/subscribe`` (and the WS
ack for a fresh node_id) issues a ``lease_token`` whose SHA-256 hash is the
only thing stored; heartbeat and WS subscribe for an already-active lease
must present it. These pins cover:

- fresh node_id -> lease issued, token returned
- foreign node_id (active lease, no/wrong token) -> 403 / WS close
- own node_id with token -> accepted, token not rotated on re-subscribe
- WS path behaves identically to REST
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _client() -> TestClient:
    from trading_service.main import app

    return TestClient(app, headers={"X-Trading-Api-Key": "test-trading-key"})


def _node_id(tag: str) -> str:
    return f"t3028-{tag}-{uuid.uuid4().hex[:8]}"


def _subscribe(client: TestClient, node_id: str, lease_token: str | None = None) -> dict:
    payload: dict = {"node_id": node_id, "chain_id": "ait-hub"}
    if lease_token is not None:
        payload["lease_token"] = lease_token
    resp = client.post("/v1/trading/offers/subscribe", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestLeaseTokenBinding:
    def test_subscribe_issues_lease_token_for_fresh_node(self) -> None:
        data = _subscribe(_client(), _node_id("fresh"))
        assert data["node_id"].startswith("t3028-fresh-")
        assert isinstance(data["lease_token"], str) and len(data["lease_token"]) > 20

    def test_heartbeat_without_token_on_bound_lease_is_rejected(self) -> None:
        client = _client()
        node_id = _node_id("hb")
        token = _subscribe(client, node_id)["lease_token"]

        # No token at all -> 403 (foreign node_id assertion).
        resp = client.post("/v1/trading/offers/heartbeat", json={"node_id": node_id, "chain_id": "ait-hub"})
        assert resp.status_code == 403
        # Wrong token -> 403.
        resp = client.post(
            "/v1/trading/offers/heartbeat",
            json={"node_id": node_id, "chain_id": "ait-hub", "lease_token": "wrong-token"},
        )
        assert resp.status_code == 403
        # Correct token -> 200 and no rotation.
        resp = client.post(
            "/v1/trading/offers/heartbeat",
            json={"node_id": node_id, "chain_id": "ait-hub", "lease_token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["lease_token"] is None

    def test_subscribe_existing_lease_requires_token_and_does_not_rotate(self) -> None:
        client = _client()
        node_id = _node_id("resub")
        token = _subscribe(client, node_id)["lease_token"]

        # Re-subscribe without the token must not hijack the lease.
        resp = client.post("/v1/trading/offers/subscribe", json={"node_id": node_id, "chain_id": "ait-hub"})
        assert resp.status_code == 403

        # With the token: accepted, and the binding is NOT rotated — the
        # original token still works for heartbeat afterwards.
        data = _subscribe(client, node_id, lease_token=token)
        assert data["lease_token"] is None
        resp = client.post(
            "/v1/trading/offers/heartbeat",
            json={"node_id": node_id, "chain_id": "ait-hub", "lease_token": token},
        )
        assert resp.status_code == 200

    def test_heartbeat_on_unknown_node_issues_fresh_bound_lease(self) -> None:
        """A node_id with no active lease gets a new bound lease — same
        contract as subscribe. This is the fresh-node path, not a bypass."""
        client = _client()
        node_id = _node_id("hbfresh")
        resp = client.post("/v1/trading/offers/heartbeat", json={"node_id": node_id, "chain_id": "ait-hub"})
        assert resp.status_code == 200
        token = resp.json()["lease_token"]
        assert isinstance(token, str) and token
        # The issued token now guards the lease.
        resp = client.post("/v1/trading/offers/heartbeat", json={"node_id": node_id, "chain_id": "ait-hub"})
        assert resp.status_code == 403
        resp = client.post(
            "/v1/trading/offers/heartbeat",
            json={"node_id": node_id, "chain_id": "ait-hub", "lease_token": token},
        )
        assert resp.status_code == 200

    def test_foreign_node_id_cannot_register_lease_for_victim(self) -> None:
        """Lease squatting pin: a second holder of the shared key asserting
        the victim's node_id gets 403 on every mutating path."""
        client = _client()
        victim = _node_id("victim")
        _subscribe(client, victim)

        for path in ("/v1/trading/offers/subscribe", "/v1/trading/offers/heartbeat"):
            resp = client.post(path, json={"node_id": victim, "chain_id": "ait-hub"})
            assert resp.status_code == 403, f"{path}: {resp.status_code} {resp.text}"


class TestWebSocketLeaseTokenBinding:
    def _ws_handshake(self, client: TestClient, node_id: str, lease_token: str | None = None):
        frame: dict = {"node_id": node_id, "chain_id": "ait-hub"}
        if lease_token is not None:
            frame["lease_token"] = lease_token
        ws = client.websocket_connect("/v1/trading/offers/subscribe/ws")
        ws.__enter__()
        ws.send_json(frame)
        return ws

    def test_ws_fresh_node_gets_token_in_ack(self) -> None:
        client = _client()
        node_id = _node_id("wsfresh")
        ws = self._ws_handshake(client, node_id)
        ack = ws.receive_json()
        assert ack["status"] == "subscribed"
        assert isinstance(ack["lease_token"], str) and ack["lease_token"]
        ws.__exit__(None, None, None)

    def test_ws_foreign_node_id_without_token_is_rejected(self) -> None:
        """Cross-tenant feed/lease pin: asserting a victim's node_id on the
        WS path without its bearer token is closed before any subscriber
        or refcount side effects."""
        client = _client()
        node_id = _node_id("wsvictim")
        token = _subscribe(client, node_id)["lease_token"]

        ws = self._ws_handshake(client, node_id)  # no token
        try:
            msg = ws.receive_json()
            assert "error" in msg
            assert "lease_token" in msg["error"]
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
        finally:
            ws.__exit__(None, None, None)

        # Wrong token is rejected the same way.
        ws = self._ws_handshake(client, node_id, lease_token="forged")
        try:
            assert "error" in ws.receive_json()
        finally:
            ws.__exit__(None, None, None)

        # The real holder still works — the rejected sockets must not have
        # disturbed the lease or the refcount.
        ws = self._ws_handshake(client, node_id, lease_token=token)
        ack = ws.receive_json()
        assert ack["status"] == "subscribed"
        assert ack["lease_token"] is None  # joined existing lease, no rotation
        ws.__exit__(None, None, None)

        # And REST heartbeat with the same token still succeeds.
        resp = client.post(
            "/v1/trading/offers/heartbeat",
            json={"node_id": node_id, "chain_id": "ait-hub", "lease_token": token},
        )
        assert resp.status_code == 200
