"""#1936 RPC-PUBLIC-READ-SURFACE-1: operational reads require a peer credential.

Hybrid posture (operator ruling): chain-data reads stay public; operational
reads — AI job lists/stats and GPU/edge registrations — are gated at the rpc
layer by ``verify_rpc_peer_key`` so both the ``/rpc`` and ``/v1`` mounts are
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
