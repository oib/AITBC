"""#1945 RPC-OPS-METADATA-1: node self-description GETs require peer credential.

Hybrid posture extended: chain-data, join-bootstrap, and public chain-stat
reads stay public (`/rpc/proposer`, `/rpc/network-info` — setup.sh/update.sh
curl them before a node holds any credential; `/rpc/info`, `/rpc/status` —
payload is public chain stats consumed keyless by fleet-config-check and the
stress suite). Internal ops-state reads are gated by ``verify_rpc_fleet_read_key``
on the shared router so `/v1` is covered too.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc_chain.rpc import escrow_routes  # noqa: F401 — registers gated deps
from aitbc_chain.rpc.routers import core, islands  # noqa: F401
from aitbc_chain.rpc.router import router

KEY = "peer-read-key-1945"

GATED = [
    "/genesis_allocations",
    "/sync/config",
    "/chains",
    "/islands",
    "/islands/isl-1",
]

PUBLIC = [
    "/proposer",
    "/network-info",
    "/info",
    "/status",
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
def test_ops_metadata_reject_missing_key(client, path, prefix):
    assert client.get(f"{prefix}{path}").status_code == 403


@pytest.mark.parametrize("path", GATED)
def test_ops_metadata_reject_wrong_key(client, path):
    assert client.get(f"/rpc{path}", headers={"X-API-Key": "wrong"}).status_code == 403


@pytest.mark.parametrize("path", GATED)
def test_ops_metadata_accept_peer_key(client, path):
    resp = client.get(f"/rpc{path}", headers={"X-API-Key": KEY})
    assert resp.status_code != 403


@pytest.mark.parametrize("path", PUBLIC)
def test_bootstrap_and_chain_reads_stay_public(client, path):
    assert client.get(f"/rpc{path}").status_code != 403
