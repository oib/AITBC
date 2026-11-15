"""#1966 fleet-read auth matrix — operational GETs on ``/rpc`` and ``/v1``.

Regression harness for ``verify_rpc_fleet_read_key`` (#1982): cross-user
operational reads accept only the node admin key or a ``BLOCKCHAIN_RPC_API_KEY_PEERS``
fleet peer, never a self-serve issued join credential. Lease-scoped routes
(``/subscribers``) still accept an issued key for its own ``node_id`` only.

Uses real auth dependencies and env/fixture patterns; stubs only downstream
lease/subscriber I/O where handlers would otherwise touch Redis/DB.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aitbc_chain.app import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc_chain.rpc import ai_services, escrow_routes, gpu_resources  # noqa: F401
from aitbc_chain.rpc.router import router
from aitbc_chain.rpc.routers import core, islands  # noqa: F401

ADMIN_KEY = "matrix-admin-key-1966"
FLEET_PEER_ONLY = "matrix-fleet-peer-only-1966"
WRONG_KEY = "matrix-wrong-key"

# Mirror #1936 GATED set + island detail from #1945.
GATED_OPERATIONAL_READS = [
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

PREFIXES = ("/rpc", "/v1")

POSITIVE_FLEET_READ = "/sync/config"


@pytest.fixture
def matrix_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """App with only the admin RPC key configured."""
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", ADMIN_KEY)
    monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset())
    app = FastAPI()
    app.include_router(router, prefix="/rpc")
    app.include_router(router, prefix="/v1")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def fleet_peer_only_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Fleet peer present only in ``_RPC_API_PEER_KEYS``, not the admin slot."""
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", "matrix-unused-admin-slot")
    monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({FLEET_PEER_ONLY}))
    app = FastAPI()
    app.include_router(router, prefix="/rpc")
    app.include_router(router, prefix="/v1")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def peer_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PEER_KEYS_DB", str(tmp_path / "peer_keys.db"))
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    return tmp_path


@pytest.fixture
def join_client(peer_db: Path) -> TestClient:
    with TestClient(create_app()) as client:
        yield client


def _join(client: TestClient, node_id: str) -> str:
    response = client.post("/rpc/join", json={"node_id": node_id})
    assert response.status_code == 200, response.text
    return response.json()["peer_key"]


@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("path", GATED_OPERATIONAL_READS)
def test_matrix_missing_key_is_403(matrix_client: TestClient, prefix: str, path: str) -> None:
    assert matrix_client.get(f"{prefix}{path}").status_code == 403


@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("path", GATED_OPERATIONAL_READS)
def test_matrix_wrong_key_is_403(matrix_client: TestClient, prefix: str, path: str) -> None:
    assert matrix_client.get(f"{prefix}{path}", headers={"X-API-Key": WRONG_KEY}).status_code == 403


@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("path", GATED_OPERATIONAL_READS)
def test_matrix_admin_key_passes_fleet_gate(matrix_client: TestClient, prefix: str, path: str) -> None:
    resp = matrix_client.get(f"{prefix}{path}", headers={"X-API-Key": ADMIN_KEY})
    assert resp.status_code != 403


@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("path", GATED_OPERATIONAL_READS)
def test_matrix_fleet_peer_only_passes_fleet_gate(fleet_peer_only_client: TestClient, prefix: str, path: str) -> None:
    resp = fleet_peer_only_client.get(f"{prefix}{path}", headers={"X-API-Key": FLEET_PEER_ONLY})
    assert resp.status_code != 403


@pytest.mark.parametrize("prefix", PREFIXES)
def test_matrix_admin_key_sync_config_200(matrix_client: TestClient, prefix: str) -> None:
    resp = matrix_client.get(f"{prefix}{POSITIVE_FLEET_READ}", headers={"X-API-Key": ADMIN_KEY})
    assert resp.status_code == 200


@pytest.mark.parametrize("prefix", PREFIXES)
def test_matrix_fleet_peer_only_sync_config_200(fleet_peer_only_client: TestClient, prefix: str) -> None:
    resp = fleet_peer_only_client.get(f"{prefix}{POSITIVE_FLEET_READ}", headers={"X-API-Key": FLEET_PEER_ONLY})
    assert resp.status_code == 200


@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("path", GATED_OPERATIONAL_READS)
def test_matrix_live_issued_key_rejects_operational_reads(
    matrix_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, prefix: str, path: str
) -> None:
    """Scratch ``PEER_KEYS_DB`` credential from ``peer_keys.issue`` (#1871)."""
    monkeypatch.setenv("PEER_KEYS_DB", str(tmp_path / "peer_keys.db"))
    from aitbc_chain.rpc import peer_keys

    issued = peer_keys.issue("matrix-issued.example.net", "10.10.10.10")
    assert matrix_client.get(f"{prefix}{path}", headers={"X-API-Key": issued}).status_code == 403


@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("path", GATED_OPERATIONAL_READS)
def test_matrix_anonymous_join_credential_rejects_operational_reads(join_client: TestClient, prefix: str, path: str) -> None:
    """POST ``/rpc/join`` (anonymous) must not unlock fleet-read gates."""
    issued = _join(join_client, "matrix-join-node.example.net")
    assert join_client.get(f"{prefix}{path}", headers={"X-API-Key": issued}).status_code == 403


def test_matrix_issued_key_subscribers_own_scope_only(join_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Issued keys remain valid for lease-scoped reads of their own ``node_id``.

    Fake sits at the lease_tracker seam (#1983): real ``get_subscribers``
    applies the ``node_id`` filter — no filtering logic duplicated here.
    """
    from aitbc_chain.lease_tracker import SubscriberInfo
    from aitbc_chain.rpc import subscription as sub_mod

    node_id = "matrix-sub-own.example.net"
    issued = _join(join_client, node_id)

    async def fake_valid_subscribers(chain_id: str | None = None):
        _ = chain_id
        return [
            SubscriberInfo(
                node_id=n,
                transport="ws",
                expiry=9_999_999_999.0,
                chain_id="c",
                client_ip=ip,
            )
            for n, ip in ((node_id, "10.0.0.1"), ("other-peer.example.net", "10.0.0.2"))
        ]

    monkeypatch.setattr(sub_mod.lease_tracker, "get_valid_subscribers", fake_valid_subscribers)

    own = join_client.get("/rpc/subscribers", headers={"X-API-Key": issued})
    assert own.status_code == 200, own.text
    payload = own.json()
    assert payload["count"] == 1
    assert [s["node_id"] for s in payload["subscribers"]] == [node_id]

    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", ADMIN_KEY)
    fleet = join_client.get("/rpc/subscribers", headers={"X-API-Key": ADMIN_KEY})
    assert fleet.status_code == 200, fleet.text
    assert fleet.json()["count"] == 2


@pytest.mark.parametrize("prefix", PREFIXES)
def test_matrix_admin_subscribers_full_list(matrix_client: TestClient, monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
    from aitbc_chain.lease_tracker import SubscriberInfo
    from aitbc_chain.rpc import subscription as sub_mod

    async def fake_valid_subscribers(chain_id: str | None = None):
        _ = chain_id
        return [
            SubscriberInfo(node_id=n, transport="ws", expiry=9_999_999_999.0, chain_id="c", client_ip=ip)
            for n, ip in (("a", "1.1.1.1"), ("b", "2.2.2.2"))
        ]

    monkeypatch.setattr(sub_mod.lease_tracker, "get_valid_subscribers", fake_valid_subscribers)

    resp = matrix_client.get(f"{prefix}/subscribers", headers={"X-API-Key": ADMIN_KEY})
    assert resp.status_code == 200
    assert resp.json()["count"] == 2
