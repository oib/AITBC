"""#1952 RPC-GATE-OPS-META-1: operational self-description GETs require peer credential.

Extends #1936/#1945 hybrid posture: chain-data reads stay public; operational
ops-metadata routes are gated by ``verify_rpc_peer_key`` so both ``/rpc`` and
``/v1`` mounts are covered.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc_chain.rpc import escrow_routes  # noqa: F401 — registers gated deps
from aitbc_chain.rpc.routers import core, islands  # noqa: F401
from aitbc_chain.rpc.router import router

KEY = "peer-read-key-1952"

GATED = [
    "/info",
    "/status",
    "/network-info",
    "/proposer",
    "/sync/config",
    "/chains",
    "/islands",
    "/islands/isl-1",
    "/genesis_allocations",
]

PUBLIC = [
    "/head",
    "/height",
    "/pending",
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
def test_ops_meta_reads_reject_missing_key(client, path, prefix):
    assert client.get(f"{prefix}{path}").status_code == 403


@pytest.mark.parametrize("path", GATED)
def test_ops_meta_reads_reject_wrong_key(client, path):
    assert client.get(f"/rpc{path}", headers={"X-API-Key": "wrong"}).status_code == 403


@pytest.mark.parametrize("path", GATED)
def test_ops_meta_reads_accept_peer_key(client, path):
    resp = client.get(f"/rpc{path}", headers={"X-API-Key": KEY})
    assert resp.status_code != 403


@pytest.mark.parametrize("path", PUBLIC)
def test_chain_data_reads_stay_public(client, path):
    assert client.get(f"/rpc{path}").status_code != 403


def test_network_info_head_requires_peer_key(client):
    assert client.head("/rpc/network-info").status_code == 403
    assert client.head("/rpc/network-info", headers={"X-API-Key": KEY}).status_code != 403
