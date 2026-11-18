"""OPS-NOISE-3: a chain-rpc endpoint must not see /api/* requests.

node_client's stub /api/auth fired on every connect and
get_chain_stats hit /api/chains/<id>/stats — neither route exists on
the chain rpc, feeding 404s into rpc_client_errors_total.
"""

import httpx
import pytest

from aitbc_cli.core.config import NodeConfig
from aitbc_cli.core.node_client import NodeClient, _endpoint_has_api_surface


def _cfg(endpoint: str) -> NodeConfig:
    return NodeConfig(id="n0", endpoint=endpoint)


@pytest.fixture
def fake_client(monkeypatch):
    """Patch AsyncClient construction; returns the recorded call list."""
    calls: list[str] = []
    orig = httpx.AsyncClient

    def _mk(*args, **kwargs):
        def _h(req: httpx.Request) -> httpx.Response:
            q = req.url.query.decode() if req.url.query else ""
            calls.append(f"{req.method} {req.url.path}?{q}")
            return httpx.Response(200, json={"height": 42, "session_id": "s"})

        return orig(transport=httpx.MockTransport(_h))

    monkeypatch.setattr(httpx, "AsyncClient", _mk)
    return calls


@pytest.mark.asyncio
async def test_no_api_auth_on_rpc_endpoint(fake_client):
    nc = NodeClient(_cfg("http://127.0.0.1:8202"))
    async with nc:
        pass
    assert not any("/api/auth" in c for c in fake_client)


@pytest.mark.asyncio
async def test_api_auth_still_runs_on_api_endpoint(fake_client):
    nc = NodeClient(_cfg("http://node.test/api"))
    nc._dev_mocks_enabled = True
    async with nc:
        pass
    assert any("/api/auth" in c for c in fake_client)


@pytest.mark.asyncio
async def test_chain_stats_uses_rpc_head(fake_client):
    nc = NodeClient(_cfg("http://127.0.0.1:8202"))
    async with nc:
        stats = await nc.get_chain_stats("ait-hub")
    assert any(c.startswith("GET /rpc/head") for c in fake_client)
    assert not any("/api/chains" in c for c in fake_client)
    assert stats["block_height"] == 42
    assert stats["source"] == "rpc-head"


def test_api_surface_is_path_based():
    # An api-* hostname does NOT mean the endpoint has an /api surface.
    assert not _endpoint_has_api_surface("http://api-gateway:8201")
    assert not _endpoint_has_api_surface("http://127.0.0.1:8202")
    assert _endpoint_has_api_surface("http://node.test/api")
    assert _endpoint_has_api_surface("http://node.test/api/")
    assert _endpoint_has_api_surface("http://node.test/api/v1")


@pytest.mark.asyncio
async def test_get_node_info_uses_public_routes_on_rpc_endpoint(monkeypatch):
    """#2230: chain-rpc nodes have no /api/node/info — compose from /health + /head."""
    calls: list[str] = []

    def _h(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.method} {req.url.path}")
        if req.url.path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "supported_chains": ["ait-drill-1"],
                    "proposer_id": "0xPROP",
                    "node_wallet": "0xWALLET",
                },
            )
        if req.url.path == "/rpc/head":
            return httpx.Response(200, json={"height": 10812})
        return httpx.Response(404, json={"detail": "not found"})

    orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: orig(transport=httpx.MockTransport(_h)))

    nc = NodeClient(_cfg("http://127.0.0.1:8202/rpc"))
    async with nc:
        info = await nc.get_node_info()

    assert not any("/api/" in c for c in calls)
    assert info["status"] == "ok"
    assert info["proposer_id"] == "0xPROP"
    assert info["node_wallet"] == "0xWALLET"
    assert info["hosted_chains"]["ait-drill-1"]["block_height"] == 10812
    # No fabricated telemetry keys.
    assert "cpu_usage" not in info
    assert "uptime_days" not in info


def test_bridge_rpc_url_appends_rpc_mount():
    from aitbc_cli.commands.node.bridge import _bridge_rpc_url

    assert _bridge_rpc_url("http://localhost:8202") == "http://localhost:8202/rpc"
    assert _bridge_rpc_url("http://localhost:8202/") == "http://localhost:8202/rpc"
    assert _bridge_rpc_url("http://localhost:8202/rpc") == "http://localhost:8202/rpc"
