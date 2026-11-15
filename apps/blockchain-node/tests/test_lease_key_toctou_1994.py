"""#1994 RPC-LEASE-KEY-TOCTOU-1 — lease/mutation routes must fail closed on an
unresolvable issued-key scope.

The pre-fix check order re-ran ``is_issued_key`` inside
``_enforce_key_node_binding`` AFTER ``verify_rpc_peer_key`` had already
accepted the key. A key revoked in that gap read as "not issued", skipped
the node_id binding, and was treated as an unbound fleet key on
``POST /subscribe``, ``POST /heartbeat``, ``GET|DELETE /lease/{node_id}``
and ``/subscribe/ws``. The fix classifies once: fleet keys unbound, every
other authenticated key must resolve an ACTIVE scope via
``peer_key_node_scope`` — ``None`` fails closed with 403.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aitbc_chain.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def peer_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PEER_KEYS_DB", str(tmp_path / "peer_keys.db"))
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    return tmp_path


@pytest.fixture
def client(peer_db: Path):
    with TestClient(create_app()) as c:
        yield c


def _join(client: TestClient, node_id: str) -> str:
    response = client.post("/rpc/join", json={"node_id": node_id})
    assert response.status_code == 200, response.text
    return response.json()["peer_key"]


def _revoke_during_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate revocation between verify_rpc_peer_key's is_issued_key and the
    route's binding check: verify sees an issued key, the binding check then
    sees the post-revocation world (is_issued_key False, scope None)."""
    from aitbc_chain.rpc import peer_keys

    calls = {"n": 0}
    real_issued = peer_keys.is_issued_key

    def flaky_is_issued(key: str) -> bool:
        calls["n"] += 1
        # First lookup (inside verify_rpc_peer_key) sees the live key;
        # every later lookup sees the revoked world.
        return real_issued(key) if calls["n"] == 1 else False

    monkeypatch.setattr(peer_keys, "is_issued_key", flaky_is_issued)
    monkeypatch.setattr(peer_keys, "peer_key_node_scope", lambda key: None)


class TestRevokedMidFlightFailsClosed:
    """The old code skipped the binding when is_issued_key flipped False —
    these pins FAIL on the unfixed code (request proceeds to the handler)."""

    def test_subscribe_revoked_mid_flight_403(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        key = _join(client, "toctou-node-a.example.net")
        _revoke_during_flight(monkeypatch)

        called = False

        async def fake_register(**kwargs):
            nonlocal called
            called = True
            return 0.0

        monkeypatch.setattr("aitbc_chain.rpc.subscription.lease_tracker.register_subscriber", fake_register)

        response = client.post(
            "/rpc/subscribe",
            json={"node_id": "toctou-node-a.example.net"},
            headers={"X-API-Key": key},
        )
        assert response.status_code == 403
        assert not called

    def test_heartbeat_revoked_mid_flight_403(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        key = _join(client, "toctou-node-b.example.net")
        _revoke_during_flight(monkeypatch)

        response = client.post(
            "/rpc/heartbeat",
            json={"node_id": "toctou-node-b.example.net"},
            headers={"X-API-Key": key},
        )
        assert response.status_code == 403

    def test_lease_get_revoked_mid_flight_403(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        key = _join(client, "toctou-node-c.example.net")
        _revoke_during_flight(monkeypatch)

        response = client.get("/rpc/lease/toctou-node-c.example.net", headers={"X-API-Key": key})
        assert response.status_code == 403

    def test_lease_delete_revoked_mid_flight_403(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        key = _join(client, "toctou-node-d.example.net")
        _revoke_during_flight(monkeypatch)

        response = client.delete("/rpc/lease/toctou-node-d.example.net", headers={"X-API-Key": key})
        assert response.status_code == 403


class TestBindingStillEnforced:
    def test_issued_key_other_node_still_403(self, client: TestClient) -> None:
        key = _join(client, "binding-own.example.net")
        response = client.post(
            "/rpc/subscribe",
            json={"node_id": "binding-other.example.net"},
            headers={"X-API-Key": key},
        )
        assert response.status_code == 403

    def test_fleet_peer_key_stays_unbound(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        from aitbc_chain.rpc import escrow_routes

        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"fleet-key-1994"}))

        async def fake_register(**kwargs):
            return 9_999_999_999.0

        monkeypatch.setattr("aitbc_chain.rpc.subscription.lease_tracker.register_subscriber", fake_register)

        response = client.post(
            "/rpc/subscribe",
            json={"node_id": "any-node.example.net"},
            headers={"X-API-Key": "fleet-key-1994"},
        )
        assert response.status_code == 200, response.text
