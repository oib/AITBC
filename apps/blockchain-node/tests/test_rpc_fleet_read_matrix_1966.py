"""#1966/#1982 — fleet-read auth matrix for cross-user operational /rpc reads.

Ported from D's test-only additions on verify-1982-auth-regression-tests
(@ 46d8a6aa0f), reshaped into the dedicated matrix module per #1983 so the
shared 1936 fixture file stays untouched. Covers:

1. Issued join keys reject cross-user reads — including /islands/{id} —
   on BOTH the /rpc and /v1 mounts.
2. A key present ONLY in BLOCKCHAIN_RPC_API_KEY_PEERS (no node admin key)
   is accepted by the fleet-read gate, with helper-level positive checks
   and a pure operational read reaching 200.
3. A live anonymous /rpc/join credential (scratch PEER_KEYS_DB) works for
   its own lease but is 403 on cross-user reads.
"""

from __future__ import annotations


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc_chain.rpc import ai_services, escrow_routes, gpu_resources  # noqa: F401
from aitbc_chain.rpc.router import router

KEY = "peer-read-key-1936"
FLEET_PEER_ONLY = "fleet-peer-only-1982"
ISSUED = "aitbc-peer-issued-join-key-1966"

# Cross-user operational reads gated by verify_rpc_fleet_read_key (#1966).
GATED_PATHS = [
    "/ai/jobs",
    "/ai/job/job-1",
    "/ai/stats",
    "/gpus",
    "/gpu/info/gpu-1",
    "/gpu/allocations/gpu-1",
    "/edge/info/node-1",
    "/edge/nodes",
    "/genesis_allocations",
    "/sync/config",
    "/chains",
    "/islands",
    "/islands/isl-1",
]
MOUNTS = ["/rpc", "/v1"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", KEY)
    app = FastAPI()
    app.include_router(router, prefix="/rpc")
    app.include_router(router, prefix="/v1")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def fleet_peer_only_client(monkeypatch):
    """Fleet read auth must accept BLOCKCHAIN_RPC_API_KEY_PEERS without the node admin key."""
    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", "node-admin-key-not-used-in-tests")
    monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({FLEET_PEER_ONLY}))
    app = FastAPI()
    app.include_router(router, prefix="/rpc")
    app.include_router(router, prefix="/v1")
    return TestClient(app, raise_server_exceptions=False)


class TestIssuedKeyRejectedEverywhere:
    @pytest.mark.parametrize("path", GATED_PATHS)
    @pytest.mark.parametrize("prefix", MOUNTS)
    def test_issued_key_rejected_on_both_mounts(self, client, monkeypatch, path, prefix):
        from aitbc_chain.rpc import peer_keys

        monkeypatch.setattr(peer_keys, "is_issued_key", lambda key: key == ISSUED)
        resp = client.get(f"{prefix}{path}", headers={"X-API-Key": ISSUED})
        assert resp.status_code == 403, f"{prefix}{path}"

    @pytest.mark.parametrize("path", GATED_PATHS)
    @pytest.mark.parametrize("prefix", MOUNTS)
    def test_live_issued_join_key_rejected(self, client, monkeypatch, tmp_path, path, prefix):
        """A real peer_keys.issue() credential — not a patched predicate —
        stays off the fleet-read gate (#1871 pattern)."""
        monkeypatch.setenv("PEER_KEYS_DB", str(tmp_path / "peer_keys.db"))
        from aitbc_chain.rpc import peer_keys

        issued = peer_keys.issue("joiner-1982.example.net", "10.9.9.9")
        resp = client.get(f"{prefix}{path}", headers={"X-API-Key": issued})
        assert resp.status_code == 403, f"{prefix}{path}"


class TestFleetPeerOnlyAccepted:
    @pytest.mark.parametrize("path", GATED_PATHS)
    @pytest.mark.parametrize("prefix", MOUNTS)
    def test_fleet_peer_only_key_not_rejected(self, fleet_peer_only_client, path, prefix):
        resp = fleet_peer_only_client.get(f"{prefix}{path}", headers={"X-API-Key": FLEET_PEER_ONLY})
        assert resp.status_code != 403, f"{prefix}{path}"

    def test_helper_accepts_fleet_peer_only(self, fleet_peer_only_client, monkeypatch):
        from aitbc_chain.rpc.escrow_routes_helpers import rpc_fleet_key_accepted

        assert rpc_fleet_key_accepted(FLEET_PEER_ONLY) is True
        assert rpc_fleet_key_accepted("node-admin-key-not-used-in-tests") is True
        assert rpc_fleet_key_accepted(ISSUED) is False
        assert rpc_fleet_key_accepted(None) is False
        assert rpc_fleet_key_accepted("bogus") is False

    def test_pure_operational_read_reaches_200(self, fleet_peer_only_client):
        resp = fleet_peer_only_client.get("/rpc/sync/config", headers={"X-API-Key": FLEET_PEER_ONLY})
        assert resp.status_code == 200, resp.text


class TestMissingWrongAndAdminKeys:
    """Ported from D's verify-1966-matrix-d: the gate must reject absent and
    bogus credentials outright, and the node admin key must pass every gated
    route on both mounts (not just the fleet-peer-only slot)."""

    @pytest.mark.parametrize("path", GATED_PATHS)
    @pytest.mark.parametrize("prefix", MOUNTS)
    def test_missing_key_is_403(self, client, path, prefix):
        assert client.get(f"{prefix}{path}").status_code == 403, f"{prefix}{path}"

    @pytest.mark.parametrize("path", GATED_PATHS)
    @pytest.mark.parametrize("prefix", MOUNTS)
    def test_wrong_key_is_403(self, client, path, prefix):
        resp = client.get(f"{prefix}{path}", headers={"X-API-Key": "matrix-wrong-key"})
        assert resp.status_code == 403, f"{prefix}{path}"

    @pytest.mark.parametrize("path", GATED_PATHS)
    @pytest.mark.parametrize("prefix", MOUNTS)
    def test_admin_key_passes_fleet_gate(self, client, path, prefix):
        resp = client.get(f"{prefix}{path}", headers={"X-API-Key": KEY})
        assert resp.status_code != 403, f"{prefix}{path}"

    @pytest.mark.parametrize("prefix", MOUNTS)
    def test_admin_key_sync_config_200(self, client, prefix):
        resp = client.get(f"{prefix}/sync/config", headers={"X-API-Key": KEY})
        assert resp.status_code == 200, resp.text


class TestLiveJoinCredential:
    """Anonymous /rpc/join issues a credential that must work for its own
    lease yet never unlock cross-user operational reads."""

    @pytest.fixture
    def join_client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PEER_KEYS_DB", str(tmp_path / "peer_keys.db"))
        monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
        from aitbc_chain.app import create_app

        with TestClient(create_app()) as c:
            yield c

    def test_joined_key_own_lease_ok_cross_user_reads_403(self, join_client, monkeypatch):
        response = join_client.post("/rpc/join", json={"node_id": "matrix-node.example.net"})
        assert response.status_code == 200, response.text
        key = response.json()["peer_key"]

        async def fake_register(**kwargs):
            return 9_999_999_999.0

        monkeypatch.setattr("aitbc_chain.rpc.subscription.lease_tracker.register_subscriber", fake_register)
        own = join_client.post(
            "/rpc/subscribe",
            json={"node_id": "matrix-node.example.net"},
            headers={"X-API-Key": key},
        )
        assert own.status_code == 200, own.text

        for path in ("/ai/jobs", "/gpus", "/islands", "/sync/config", "/chains"):
            resp = join_client.get(f"/rpc{path}", headers={"X-API-Key": key})
            assert resp.status_code == 403, f"/rpc{path}"
