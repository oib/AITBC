"""#1952 RPC-GATE-OPS-META-1: inventory pin for operational vs public RPC reads.

Validator FAIL on the first attempt (5be485f6ba): gating ``/proposer``,
``/info``, ``/status``, and ``/network-info`` breaks keyless join bootstrap
(setup.sh/update.sh), fleet-config-check, stress lib, and governance_parameter_change
with no caller threading in the same diff.

#1945 already gates internal ops-state reads. #1952 closes the inventory by
pinning the hybrid posture on the full prompt list — gated ops-state vs public
join-bootstrap and chain-stat reads — on both ``/rpc`` and ``/v1`` mounts.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc_chain.rpc import escrow_routes  # noqa: F401 — registers gated deps
from aitbc_chain.rpc.routers import core, islands  # noqa: F401
from aitbc_chain.rpc.router import router

KEY = "peer-read-key-1952"

# #1945-gated internal ops-state (inventory items that require peer credential).
GATED = [
    "/sync/config",
    "/chains",
    "/islands",
    "/islands/isl-1",
    "/genesis_allocations",
]

# Join-bootstrap + public chain-stat (must stay keyless until #1941-family callers land).
PUBLIC_OPS_META = [
    "/proposer",
    "/network-info",
    "/info",
    "/status",
]

PUBLIC_CHAIN = [
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
def test_ops_state_reads_reject_missing_key(client, path, prefix):
    assert client.get(f"{prefix}{path}").status_code == 403


@pytest.mark.parametrize("path", GATED)
def test_ops_state_reads_accept_peer_key(client, path):
    resp = client.get(f"/rpc{path}", headers={"X-API-Key": KEY})
    assert resp.status_code != 403


@pytest.mark.parametrize("path", PUBLIC_OPS_META + PUBLIC_CHAIN)
def test_bootstrap_and_chain_reads_stay_public(client, path):
    assert client.get(f"/rpc{path}").status_code != 403


def test_network_info_head_stays_public_for_probes(client):
    assert client.head("/rpc/network-info").status_code != 403
