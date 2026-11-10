"""
Test Trading service main application
"""

import pytest
from fastapi.testclient import TestClient

from trading_service.dependencies import require_trading_api_key

GATE_KEY = "gate-test-key"


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "trading"


def test_metrics_endpoint(client):
    """Test Prometheus metrics endpoint"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


def test_trading_status(client):
    """Test trading status endpoint"""
    response = client.get("/v1/trading/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "trading"


def test_get_trade_requests(client):
    """Test get trade requests endpoint"""
    response = client.get("/v1/trading/requests")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_trade_matches(client):
    """Test get trade matches endpoint"""
    response = client.get("/v1/trading/matches")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_trade_agreements(client):
    """Test get trade agreements endpoint"""
    response = client.get("/v1/trading/agreements")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_trading_analytics(client):
    """Test get trading analytics endpoint"""
    response = client.get("/v1/trading/analytics")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


@pytest.fixture
def anon_client():
    from trading_service.main import app

    return TestClient(app)


@pytest.fixture
def gate_key(monkeypatch):
    monkeypatch.setattr(require_trading_api_key, "expected_key", GATE_KEY)
    return GATE_KEY


def test_protected_route_rejects_missing_key(anon_client, gate_key):
    response = anon_client.get("/v1/trading/inter-chain", params={"limit": 1})
    assert response.status_code == 401


def test_protected_route_rejects_wrong_key(anon_client, gate_key):
    response = anon_client.get(
        "/v1/trading/inter-chain",
        params={"limit": 1},
        headers={"X-Trading-Api-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_protected_route_rejects_rpc_key_header(anon_client, gate_key):
    response = anon_client.get(
        "/v1/trading/inter-chain",
        params={"limit": 1},
        headers={"X-API-Key": gate_key},
    )
    assert response.status_code == 401


def test_protected_route_accepts_trading_key(client, gate_key):
    response = client.get(
        "/v1/trading/inter-chain",
        params={"limit": 1},
        headers={"X-Trading-Api-Key": gate_key},
    )
    assert response.status_code == 200


def test_settlement_status_unknown_trade_is_404_not_401(client, gate_key):
    response = client.get(
        "/v1/trading/trades/nonexistent-auth-test/settlement-status",
        headers={"X-Trading-Api-Key": gate_key},
    )
    assert response.status_code == 404


def test_gate_returns_501_when_server_key_unconfigured(anon_client, monkeypatch):
    monkeypatch.setattr(require_trading_api_key, "expected_key", None)
    response = anon_client.get(
        "/v1/trading/inter-chain",
        params={"limit": 1},
        headers={"X-Trading-Api-Key": "anything"},
    )
    assert response.status_code == 501


def test_health_is_public(anon_client):
    response = anon_client.get("/health")
    assert response.status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/v1/trading/requests"),
        ("post", "/v1/transactions"),
        ("post", "/v1/trading/inter-chain/create"),
        ("post", "/v1/trading/trades/some-trade/settle"),
        ("post", "/v1/trading/trades/some-trade/lock-escrow"),
        ("post", "/v1/trading/offers/subscribe"),
    ],
)
def test_mutating_routes_reject_missing_key(anon_client, gate_key, method, path):
    """Every trading write router is included with
    ``dependencies=[Depends(require_trading_api_key)]`` — a mutating call
    with no ``X-Trading-Api-Key`` must 401 at the router gate before any
    handler or body validation runs. The existing pins only exercised a
    GET; these cover the money-moving POST surface."""
    response = getattr(anon_client, method)(path, json={})
    assert response.status_code == 401, f"{method.upper()} {path}: {response.status_code}"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/trading/requests",
        "/v1/transactions",
        "/v1/trading/inter-chain",
        "/v1/trading/offers/sync-status",
        "/v1/trading/offers/subscription-status",
        "/v1/trading/trades/nonexistent-auth-test/settlement-status",
    ],
)
def test_every_protected_router_rejects_missing_key(anon_client, gate_key, path):
    assert anon_client.get(path).status_code == 401


# ---------------------------------------------------------------------------
# #1674: inter-chain create input bounds (v7 money-edge fuzz)
# ---------------------------------------------------------------------------

_INTER_CHAIN_CREATE = {
    "source_chain": "chain-a",
    "dest_chain": "chain-b",
    "sender": "0xsender",
    "recipient": "0xrecipient",
    "amount": 100,
}


@pytest.mark.parametrize(
    "override",
    [
        {"amount": -1},
        {"amount": 0},
        {"amount": 10**15 + 1},
        {"amount": 1e18},  # float — StrictInt rejects
        {"amount": True},  # bool — StrictInt rejects
        {"amount": "100"},  # str — StrictInt rejects
        {"quantity": -1},
        {"quantity": 0},
        {"quantity": 10**9 + 1},
        {"quantity": 1e18},
        {"quantity": True},
        # NB: explicit null is accepted as "unset" (-> quantity 0), identical
        # to omitting the field — StrictInt | None cannot distinguish them.
        {"price": -1},
        {"price": "1e30"},
    ],
)
def test_inter_chain_create_rejects_bad_money_input(client, override):
    """#1674: quantity/amount/price must be finite, in-range, correctly typed."""
    response = client.post("/v1/trading/inter-chain/create", json={**_INTER_CHAIN_CREATE, **override})
    assert response.status_code in (400, 422), f"{override}: {response.status_code} {response.text[:200]}"


def test_inter_chain_create_accepts_valid_input(client):
    """#1674 invariant: a sane payload still creates the trade."""
    response = client.post(
        "/v1/trading/inter-chain/create",
        json={**_INTER_CHAIN_CREATE, "quantity": 3, "price": "1.5"},
    )
    assert response.status_code == 200, response.text[:300]
    assert response.json()["status"] == "pending"


# ---------------------------------------------------------------------------
# #1676: literal NaN/Infinity JSON must answer a serializable 422, not 500
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field", ["amount", "quantity"])
def test_non_json_float_literals_answer_422_not_500(client, literal, field):
    """Python's json parser accepts NaN/Infinity; pydantic rejects them for
    typed fields, and the 422 body used to echo ``input: nan`` back into
    JSONResponse — which cannot serialize it, producing a 500."""
    body = (
        b'{"source_chain":"a","dest_chain":"b","sender":"s","recipient":"r",'
        + f'"amount":100,"{field}":{literal}'.encode()
        + b"}"
    )
    response = client.post(
        "/v1/trading/inter-chain/create",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, f"{field}={literal}: {response.status_code} {response.text[:200]}"
    # The body must be valid JSON — the whole point of the fix.
    detail = response.json()["detail"]
    assert detail and all("loc" in err for err in detail)
