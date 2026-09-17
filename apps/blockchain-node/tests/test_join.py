"""Self-serve island joining: POST /rpc/join issues peer keys bound to a node_id.

The key property under test is the binding: an issued key authorizes
/rpc/subscribe, /rpc/heartbeat and /rpc/lease/{node_id} for *its own* node_id
only — never another node's. Env-configured peer keys
(BLOCKCHAIN_RPC_API_KEY_PEERS) are fleet-internal and stay unbound.
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


def _join(client: TestClient, node_id: str, contact: str | None = None) -> dict:
    body: dict = {"node_id": node_id}
    if contact:
        body["contact"] = contact
    response = client.post("/rpc/join", json=body)
    assert response.status_code == 200, response.text
    return response.json()


class TestJoinIssuance:
    def test_join_issues_a_node_bound_key(self, client: TestClient) -> None:
        data = _join(client, "follower-one.example.net", contact="op@example.net")

        assert data["node_id"] == "follower-one.example.net"
        assert data["peer_key"].startswith("aitbc-peer-")
        assert data["env_snippet"] == f"BLOCKCHAIN_RPC_API_KEY={data['peer_key']}"
        assert data["bootstrap_env_url"].endswith("/agent/bootstrap.env")
        assert data["genesis_json_url"].endswith("/agent/genesis.json")

    def test_join_rejects_a_bad_node_id(self, client: TestClient) -> None:
        for bad in ("", "x", "a" * 70, "has space", "semi;colon", "-leading"):
            response = client.post("/rpc/join", json={"node_id": bad})
            assert response.status_code == 400, bad

    def test_join_rejects_missing_node_id(self, client: TestClient) -> None:
        assert client.post("/rpc/join", json={}).status_code == 400

    def test_a_taken_node_id_cannot_be_reclaimed(self, client: TestClient) -> None:
        _join(client, "follower-two.example.net")

        response = client.post("/rpc/join", json={"node_id": "follower-two.example.net"})
        assert response.status_code == 409


class TestIssuedKeyAuthorization:
    def test_issued_key_subscribes_its_own_node(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        key = _join(client, "follower-three.example.net")["peer_key"]

        async def fake_register(**kwargs):
            return 9999999999.0

        monkeypatch.setattr("aitbc_chain.rpc.subscription.lease_tracker.register_subscriber", fake_register)

        response = client.post(
            "/rpc/subscribe",
            json={"node_id": "follower-three.example.net"},
            headers={"X-API-Key": key},
        )
        assert response.status_code == 200, response.text
        assert response.json()["node_id"] == "follower-three.example.net"

    def test_issued_key_cannot_subscribe_another_node(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        key = _join(client, "follower-four.example.net")["peer_key"]

        called = False

        async def fake_register(**kwargs):
            nonlocal called
            called = True
            return 0.0

        monkeypatch.setattr("aitbc_chain.rpc.subscription.lease_tracker.register_subscriber", fake_register)

        response = client.post(
            "/rpc/subscribe",
            json={"node_id": "someone-else.example.net"},
            headers={"X-API-Key": key},
        )
        assert response.status_code == 403
        assert not called

    def test_issued_key_cannot_revoke_another_lease(self, client: TestClient) -> None:
        key = _join(client, "follower-five.example.net")["peer_key"]

        response = client.delete("/rpc/lease/victim-node", headers={"X-API-Key": key})
        assert response.status_code == 403

    def test_unknown_key_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/rpc/subscribe",
            json={"node_id": "follower-six.example.net"},
            headers={"X-API-Key": "aitbc-peer-forged"},
        )
        assert response.status_code == 403

    def test_missing_key_is_rejected(self, client: TestClient) -> None:
        response = client.post("/rpc/subscribe", json={"node_id": "follower-seven.example.net"})
        assert response.status_code == 403

    def test_env_peer_key_stays_unbound(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fleet keys in BLOCKCHAIN_RPC_API_KEY_PEERS manage any lease — they are
        operator-managed internal keys, not self-serve credentials."""
        from aitbc_chain.rpc import escrow_routes

        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"fleet-peer-key"}))

        async def fake_register(**kwargs):
            return 9999999999.0

        monkeypatch.setattr("aitbc_chain.rpc.subscription.lease_tracker.register_subscriber", fake_register)

        response = client.post(
            "/rpc/subscribe",
            json={"node_id": "any-node.example.net"},
            headers={"X-API-Key": "fleet-peer-key"},
        )
        assert response.status_code == 200, response.text

    def test_revoked_key_is_rejected(self, client: TestClient, peer_db: Path) -> None:
        from aitbc_chain.rpc import peer_keys

        key = _join(client, "follower-eight.example.net")["peer_key"]
        assert peer_keys.revoke("follower-eight.example.net") is True

        response = client.post(
            "/rpc/subscribe",
            json={"node_id": "follower-eight.example.net"},
            headers={"X-API-Key": key},
        )
        assert response.status_code == 403

    def test_revoked_node_can_rejoin(self, client: TestClient, peer_db: Path) -> None:
        from aitbc_chain.rpc import peer_keys

        _join(client, "follower-nine.example.net")
        peer_keys.revoke("follower-nine.example.net")

        data = _join(client, "follower-nine.example.net")
        assert data["peer_key"].startswith("aitbc-peer-")


class TestPeerKeyStore:
    def test_only_the_hash_is_stored(self, peer_db: Path) -> None:
        from aitbc_chain.rpc import peer_keys

        key = peer_keys.issue("store-test", "10.0.0.1")
        raw = (peer_db / "peer_keys.db").read_bytes()
        assert key.encode() not in raw

    def test_lookup_and_scope(self, peer_db: Path) -> None:
        from aitbc_chain.rpc import peer_keys

        key = peer_keys.issue("scoped-node", "10.0.0.2", contact="x@y.z")
        assert peer_keys.is_issued_key(key)
        assert peer_keys.peer_key_node_scope(key) == "scoped-node"
        assert peer_keys.lookup(key).issued_ip == "10.0.0.2"

        peer_keys.revoke("scoped-node")
        assert not peer_keys.is_issued_key(key)
        assert peer_keys.peer_key_node_scope(key) is None

    def test_node_id_uniqueness_is_db_enforced(self, peer_db: Path) -> None:
        import sqlite3

        from aitbc_chain.rpc import peer_keys

        peer_keys.issue("unique-node", "10.0.0.3")
        with pytest.raises(sqlite3.IntegrityError):
            peer_keys.issue("unique-node", "10.0.0.4")

        # Revoking frees the node_id for a later re-join.
        peer_keys.revoke("unique-node")
        peer_keys.issue("unique-node", "10.0.0.4")
