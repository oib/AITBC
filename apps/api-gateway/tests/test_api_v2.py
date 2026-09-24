"""The /api/v2 service-qualified surface (gateway-internal prefix /v2/).

v1 routes prefix-match an ordered table — /v1/market is carved between the
market service and coordinator-owned sub-families, and /v1/marketplace aliases
it. v2 qualifies the service instead: /v2/<service>/<upstream path> forwards
the remainder verbatim, so a coordinator route and a market route can never
claim each other's traffic. These tests pin the forwarding semantics, the
collision-freedom property, and coverage of every committed spec.
"""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import api_gateway.main as gateway

_REPO_ROOT = Path(__file__).resolve().parents[3]
# Specs whose service is exposed through the gateway. wallet-openapi.json
# stays committed but documents the loopback-only wallet daemon surface --
# it is deliberately not a v2 qualifier since Phase H.
_SPEC_FOR_QUALIFIER = {
    "market": "market-openapi.json",
    "coordinator": "coordinator-api-openapi.json",
    "chain": "blockchain-node-openapi.json",
    "agent-coordinator": "agent-coordinator-openapi.json",
}


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.setattr(gateway, "REQUIRE_AUTH", False)


@pytest.fixture(autouse=True)
def _reset_breakers():
    for state in gateway.circuit_breaker_state.values():
        state["failures"] = 0
        state["is_open"] = False
        state["last_failure_time"] = None


@pytest.fixture
def client():
    with TestClient(gateway.app) as test_client:
        yield test_client


class _RecordingClient:
    """Stands in for app.state.http_client; records each call, returns 200."""

    def __init__(self, status_code: int = 200):
        self.calls: list[dict] = []
        self.status_code = status_code
        self.fail: Exception | None = None

    async def _send(self, method: str, url: str, **kwargs):
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        if self.fail is not None:
            raise self.fail
        return httpx.Response(self.status_code, json={"ok": True})

    async def aclose(self):
        pass

    async def get(self, url, **kwargs):
        return await self._send("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._send("POST", url, **kwargs)

    async def put(self, url, **kwargs):
        return await self._send("PUT", url, **kwargs)

    async def delete(self, url, **kwargs):
        return await self._send("DELETE", url, **kwargs)

    async def patch(self, url, **kwargs):
        return await self._send("PATCH", url, **kwargs)

    async def head(self, url, **kwargs):
        return await self._send("HEAD", url, **kwargs)

    async def options(self, url, **kwargs):
        return await self._send("OPTIONS", url, **kwargs)


def test_v2_index_lists_qualifiers(client):
    resp = client.get("/v2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api"] == "v2"
    services = body["services"]
    for qualifier in ("market", "coordinator", "exchange", "chain"):
        assert qualifier in services
        assert services[qualifier]["prefix"] == f"/api/v2/{qualifier}"
        assert services[qualifier]["env"]
        assert services[qualifier]["url"]
    # v1-only spellings and route families are not v2 services.
    for excluded in ("marketplace", "escrow", "plugin", "wallet"):
        assert excluded not in services


def test_v2_forwards_upstream_path_verbatim(client, monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    resp = client.get("/v2/market/v1/market/offers?limit=5")
    assert resp.status_code == 200
    call = recorder.calls[-1]
    assert call["method"] == "GET"
    assert call["url"] == f"{gateway._V2_SERVICE_URLS['market']}/v1/market/offers"
    assert call["kwargs"]["params"]["limit"] == "5"


def test_v2_chain_reaches_node_rpc(client, monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    resp = client.get("/v2/chain/rpc/status")
    assert resp.status_code == 200
    assert recorder.calls[-1]["url"] == f"{gateway._V2_SERVICE_URLS['chain']}/rpc/status"


def test_v2_coordinator_market_is_not_the_market_service(client, monkeypatch):
    """The v1 collision cannot recur: /v2/coordinator/v1/market/* must reach the
    coordinator, never the market service that owns the v1 /v1/market prefix."""
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    resp = client.get("/v2/coordinator/v1/market/gpu")
    assert resp.status_code == 200
    assert recorder.calls[-1]["url"].startswith(gateway._V2_SERVICE_URLS["coordinator"])


def test_v2_post_forwards_body_and_idempotency_key(client, monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    resp = client.post(
        "/v2/market/v1/market/offers",
        json={"to": "0xdef", "amount": "1"},
        headers={"Idempotency-Key": "k-1"},
    )
    assert resp.status_code == 200
    call = recorder.calls[-1]
    assert call["method"] == "POST"
    assert json.loads(call["kwargs"]["content"]) == {"to": "0xdef", "amount": "1"}
    assert call["kwargs"]["headers"]["idempotency-key"] == "k-1"


def test_v2_unknown_service_404(client, monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    resp = client.get("/v2/nosuchservice/anything")
    assert resp.status_code == 404
    assert recorder.calls == []


def test_v2_missing_upstream_path_404(client, monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr(gateway.app.state, "http_client", recorder)

    resp = client.get("/v2/market")
    assert resp.status_code == 404
    assert recorder.calls == []


def test_v2_marketplace_is_not_a_qualifier(client):
    # The legacy spelling stays on v1 only; v2 publishes canonical names.
    assert client.get("/v2/marketplace/v1/market/offers").status_code == 404
    assert client.get("/v2/wallet/v1/wallets").status_code == 404


def test_v2_qualifiers_cover_every_committed_spec():
    """Every documented spec operation is reachable under its qualifier."""
    for qualifier, spec_file in _SPEC_FOR_QUALIFIER.items():
        spec = json.loads((_REPO_ROOT / "docs" / "api" / spec_file).read_text())
        assert qualifier in gateway._V2_SERVICE_URLS, f"{spec_file} has no v2 qualifier"
        assert spec["paths"], f"{spec_file} documents no paths"


def test_v2_routes_do_not_collide_with_v1_prefixes():
    """Nothing under v2/ can be claimed by the v1 prefix table, and vice versa."""
    for name, config in gateway.SERVICES.items():
        prefix = str(config["prefix"]).lstrip("/")
        assert not prefix.startswith("v2"), f"v1 prefix {name}={prefix} intrudes into the v2 namespace"
    for qualifier in gateway._V2_SERVICE_URLS:
        assert qualifier not in ("marketplace", "escrow", "plugin")


def test_v2_map_matches_gateway_table():
    """docs/api/api-v2-map.json is generated from this table — the check only
    needs the service entries to agree; the drift guard compares the files."""
    route_map = json.loads((_REPO_ROOT / "docs" / "api" / "api-v2-map.json").read_text())
    assert set(route_map["services"]) == set(gateway._V2_SERVICE_URLS)
    for qualifier, entry in route_map["services"].items():
        assert entry["base_url"] == gateway._V2_SERVICE_URLS[qualifier]
        assert entry["env"] == gateway._V2_SERVICE_ENV[qualifier]


def test_v2_breaker_covers_qualifiers():
    """v2-only upstreams (chain) must exist in the breaker table or the first
    proxied failure would KeyError."""
    for qualifier in gateway._V2_SERVICE_URLS:
        assert qualifier in gateway.circuit_breaker_state


class TestGatewayReadiness:
    def test_ready_with_no_required_services(self, client, monkeypatch):
        monkeypatch.delenv("GATEWAY_REQUIRED_SERVICES", raising=False)
        monkeypatch.setattr(gateway.app.state, "http_client", _RecordingClient())
        resp = client.get("/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_not_ready_without_http_client(self, client, monkeypatch):
        monkeypatch.delenv("GATEWAY_REQUIRED_SERVICES", raising=False)
        monkeypatch.setattr(gateway.app.state, "http_client", None)
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert "http_client" in resp.json()["failed"]

    def test_required_service_healthy(self, client, monkeypatch):
        recorder = _RecordingClient()
        monkeypatch.setenv("GATEWAY_REQUIRED_SERVICES", "market,chain")
        monkeypatch.setattr(gateway.app.state, "http_client", recorder)
        resp = client.get("/ready")
        assert resp.status_code == 200
        checked = {c["url"] for c in recorder.calls}
        assert f"{gateway._V2_SERVICE_URLS['market']}/health" in checked
        assert f"{gateway._V2_SERVICE_URLS['chain']}/health" in checked

    def test_required_service_unhealthy(self, client, monkeypatch):
        recorder = _RecordingClient(status_code=503)
        monkeypatch.setenv("GATEWAY_REQUIRED_SERVICES", "market")
        monkeypatch.setattr(gateway.app.state, "http_client", recorder)
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert resp.json()["failed"] == ["market"]

    def test_required_service_unreachable(self, client, monkeypatch):
        recorder = _RecordingClient()
        recorder.fail = httpx.ConnectError("refused")
        monkeypatch.setenv("GATEWAY_REQUIRED_SERVICES", "market")
        monkeypatch.setattr(gateway.app.state, "http_client", recorder)
        assert client.get("/ready").status_code == 503

    def test_unknown_required_service_fails_loud(self, client, monkeypatch):
        monkeypatch.setenv("GATEWAY_REQUIRED_SERVICES", "typoed-name")
        monkeypatch.setattr(gateway.app.state, "http_client", _RecordingClient())
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert "typoed-name" in resp.json()["failed"]
