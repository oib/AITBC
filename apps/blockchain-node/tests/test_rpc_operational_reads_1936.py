"""#1936 RPC-PUBLIC-READ-SURFACE-1: operational reads require a peer credential.

Hybrid posture (operator ruling): chain-data reads stay public; operational
reads — AI job lists/stats and GPU/edge registrations — are gated at the rpc
layer by ``verify_rpc_fleet_read_key`` (fleet keys only, #1966) so both the ``/rpc`` and ``/v1`` mounts are
covered. Websockets are already gated where operational (``/subscribe/ws``
lease check, ``/rpc/gossip/ws`` publish peer credential + validator-topic
challenge); public-topic gossip subscribe carries only public chain data.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc_chain.rpc import ai_services, escrow_routes, gpu_resources  # noqa: F401
from aitbc_chain.rpc.router import router

KEY = "peer-read-key-1936"

GATED = [
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
]

PUBLIC = [
    "/pending",
    "/market/listings",
    "/market/listing/1",
]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", KEY)
    app = FastAPI()
    app.include_router(router, prefix="/rpc")
    app.include_router(router, prefix="/v1")
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", GATED)
@pytest.mark.parametrize("prefix", ["/rpc", "/v1"])
def test_operational_reads_reject_missing_key(client, path, prefix):
    assert client.get(f"{prefix}{path}").status_code == 403


@pytest.mark.parametrize("path", GATED)
def test_operational_reads_reject_wrong_key(client, path):
    assert client.get(f"/rpc{path}", headers={"X-API-Key": "wrong"}).status_code == 403


@pytest.mark.parametrize("path", GATED)
def test_operational_reads_accept_peer_key(client, path):
    resp = client.get(f"/rpc{path}", headers={"X-API-Key": KEY})
    assert resp.status_code != 403


@pytest.mark.parametrize("path", PUBLIC)
def test_chain_data_reads_stay_public(client, path):
    assert client.get(f"/rpc{path}").status_code != 403


ISSUED = "aitbc-peer-issued-join-key-1966"


@pytest.mark.parametrize("path", GATED)
def test_operational_reads_reject_issued_join_key(client, monkeypatch, path):
    """#1966: POST /rpc/join is anonymous, so an issued key must not unlock
    cross-user operational reads."""
    from aitbc_chain.rpc import peer_keys

    monkeypatch.setattr(peer_keys, "is_issued_key", lambda key: key == ISSUED)
    assert client.get(f"/rpc{path}", headers={"X-API-Key": ISSUED}).status_code == 403


def test_subscribers_issued_key_sees_only_own_node(client, monkeypatch):
    """#1983: fake at the lease-tracker seam — real get_subscribers performs
    the node_id filter; no filtering logic duplicated in the fake."""
    from aitbc_chain.lease_tracker import SubscriberInfo
    from aitbc_chain.rpc import peer_keys
    from aitbc_chain.rpc import subscription as sub_mod

    async def fake_valid_subscribers(chain_id=None):
        return [
            SubscriberInfo(node_id=n, transport="ws", expiry=9_999_999_999.0, chain_id="c", client_ip="1.2.3.4")
            for n in ("mine-1", "other-2")
        ]

    monkeypatch.setattr(sub_mod.lease_tracker, "get_valid_subscribers", fake_valid_subscribers)
    monkeypatch.setattr(peer_keys, "is_issued_key", lambda key: key == ISSUED)
    monkeypatch.setattr(peer_keys, "peer_key_node_scope", lambda key: "mine-1" if key == ISSUED else None)

    own = client.get("/rpc/subscribers", headers={"X-API-Key": ISSUED}).json()
    assert [s["node_id"] for s in own["subscribers"]] == ["mine-1"] and own["count"] == 1
    fleet = client.get("/rpc/subscribers", headers={"X-API-Key": KEY}).json()
    assert fleet["count"] == 2
    assert {s["node_id"] for s in fleet["subscribers"]} == {"mine-1", "other-2"}
