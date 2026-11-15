"""#1966/#1981 — /rpc/subscribers scopes issued join keys to their own node.

Contract: fleet/admin keys keep the full valid-subscriber list; an issued
join key sees ONLY its own valid rows (count recomputed); a missing or
revoked scope fails closed with 403 — never an unfiltered fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aitbc_chain.app import create_app
from aitbc_chain.lease_tracker import SubscriberInfo
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


def _subs(node_id: str, chain_id: str = "chain-a", expiry: float = 9_999_999_999.0) -> SubscriberInfo:
    return SubscriberInfo(
        node_id=node_id,
        transport="ws",
        expiry=expiry,
        chain_id=chain_id,
        client_ip="10.0.0.1",
    )


@pytest.fixture
def fleet_rows(monkeypatch: pytest.MonkeyPatch):
    """Three valid leases: two on chain-a (own + other node), one on chain-b."""
    rows = [
        _subs("node-own"),
        _subs("node-other"),
        _subs("node-own", chain_id="chain-b"),
    ]

    async def fake_get_valid(chain_id: str | None = None):
        if chain_id is None:
            return list(rows)
        return [s for s in rows if s.chain_id == chain_id]

    monkeypatch.setattr(
        "aitbc_chain.rpc.subscription.lease_tracker.get_valid_subscribers",
        fake_get_valid,
    )
    return rows


class TestIssuedKeyScope:
    def test_issued_key_sees_only_its_own_rows(self, client: TestClient, fleet_rows) -> None:
        key = _join(client, "node-own")

        response = client.get("/rpc/subscribers", headers={"X-API-Key": key})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["count"] == 2
        assert {s["node_id"] for s in data["subscribers"]} == {"node-own"}
        # chain-b lease of the same node is still its own row — both chains visible
        assert {s["chain_id"] for s in data["subscribers"]} == {"chain-a", "chain-b"}

    def test_other_enrolled_node_stays_absent(self, client: TestClient, fleet_rows) -> None:
        key = _join(client, "node-other")

        data = client.get("/rpc/subscribers", headers={"X-API-Key": key}).json()
        assert data["count"] == 1
        assert data["subscribers"][0]["node_id"] == "node-other"

    def test_chain_id_filter_still_applies(self, client: TestClient, fleet_rows) -> None:
        key = _join(client, "node-own")

        data = client.get("/rpc/subscribers?chain_id=chain-b", headers={"X-API-Key": key}).json()
        assert data["count"] == 1
        assert data["subscribers"][0]["chain_id"] == "chain-b"

        data = client.get("/rpc/subscribers?chain_id=chain-c", headers={"X-API-Key": key}).json()
        assert data["count"] == 0
        assert data["subscribers"] == []

    def test_expired_or_absent_own_lease_yields_empty(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_get_valid(chain_id: str | None = None):
            return []  # lease_tracker drops expired leases before this point

        monkeypatch.setattr(
            "aitbc_chain.rpc.subscription.lease_tracker.get_valid_subscribers",
            fake_get_valid,
        )
        key = _join(client, "node-own")

        data = client.get("/rpc/subscribers", headers={"X-API-Key": key}).json()
        assert data["count"] == 0
        assert data["subscribers"] == []

    def test_node_with_no_lease_sees_empty_not_others(self, client: TestClient, fleet_rows) -> None:
        key = _join(client, "node-newcomer")

        data = client.get("/rpc/subscribers", headers={"X-API-Key": key}).json()
        assert data["count"] == 0
        assert data["subscribers"] == []


class TestFleetAndAdminKeys:
    def test_fleet_peer_key_sees_full_list(self, client: TestClient, fleet_rows, monkeypatch: pytest.MonkeyPatch) -> None:
        from aitbc_chain.rpc import escrow_routes

        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"fleet-peer-key"}))

        data = client.get("/rpc/subscribers", headers={"X-API-Key": "fleet-peer-key"}).json()
        assert data["count"] == 3
        assert {s["node_id"] for s in data["subscribers"]} == {"node-own", "node-other"}

    def test_admin_key_sees_full_list(self, client: TestClient, fleet_rows, monkeypatch: pytest.MonkeyPatch) -> None:
        from aitbc_chain.rpc import escrow_routes

        monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", "admin-key")

        data = client.get("/rpc/subscribers", headers={"X-API-Key": "admin-key"}).json()
        assert data["count"] == 3

    def test_fleet_key_chain_filter_unchanged(self, client: TestClient, fleet_rows, monkeypatch: pytest.MonkeyPatch) -> None:
        from aitbc_chain.rpc import escrow_routes

        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"fleet-peer-key"}))

        data = client.get("/rpc/subscribers?chain_id=chain-a", headers={"X-API-Key": "fleet-peer-key"}).json()
        assert data["count"] == 2


class TestFailClosed:
    def test_missing_key_is_403(self, client: TestClient, fleet_rows) -> None:
        assert client.get("/rpc/subscribers").status_code == 403

    def test_unknown_key_is_403(self, client: TestClient, fleet_rows) -> None:
        assert client.get("/rpc/subscribers", headers={"X-API-Key": "bogus"}).status_code == 403

    def test_revoked_key_is_403(self, client: TestClient, fleet_rows, peer_db: Path) -> None:
        from aitbc_chain.rpc import peer_keys

        key = _join(client, "node-own")
        assert peer_keys.revoke("node-own") is True

        assert client.get("/rpc/subscribers", headers={"X-API-Key": key}).status_code == 403

    def test_scope_lookup_race_returns_none_is_403(
        self, client: TestClient, fleet_rows, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Key authenticates at verify time but scope resolution returns None
        (revoked between the two lookups) — must fail closed, not fall through."""
        key = _join(client, "node-own")
        monkeypatch.setattr(
            "aitbc_chain.rpc.routers.subscription.peer_keys.peer_key_node_scope",
            lambda _key: None,
        )

        response = client.get("/rpc/subscribers", headers={"X-API-Key": key})
        assert response.status_code == 403

    def test_scope_lookup_error_is_403(self, client: TestClient, fleet_rows, monkeypatch: pytest.MonkeyPatch) -> None:
        key = _join(client, "node-own")

        def boom(_key):
            raise RuntimeError("peer_keys db gone")

        monkeypatch.setattr(
            "aitbc_chain.rpc.routers.subscription.peer_keys.peer_key_node_scope",
            boom,
        )
        # An exception here is NOT a scope — it propagates to the app's
        # unhandled-error path (503), still fail-closed: no unfiltered list.
        response = client.get("/rpc/subscribers", headers={"X-API-Key": key})
        assert response.status_code in (403, 500, 503)
