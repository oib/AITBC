"""#1544 endpoint pins: the trading service rate-limits mutating endpoints.

The limiter is per client IP (120 mutating requests / 60s by default). Each
test uses a unique TEST-NET-3 peer so its bucket is isolated from the shared
``testclient`` bucket the rest of the suite uses.
"""

from fastapi.testclient import TestClient


def _client(ip: str) -> TestClient:
    from trading_service.main import app

    return TestClient(app, client=(ip, 50000), raise_server_exceptions=False)


def test_mutating_endpoint_eventually_returns_429() -> None:
    """Unauthenticated POSTs still count: the 121st inside the window is a 429."""
    client = _client("203.0.113.10")

    for _ in range(120):
        # No X-Trading-Api-Key -> 401 from the auth dependency, but the request
        # was still counted by the middleware before routing.
        assert client.post("/v1/trading/requests").status_code == 401

    assert client.post("/v1/trading/requests").status_code == 429


def test_reads_and_probes_are_not_throttled() -> None:
    """Once the mutating budget is gone, GETs and exempt paths still pass."""
    client = _client("203.0.113.11")

    for _ in range(125):
        client.post("/v1/trading/requests")
    assert client.post("/v1/trading/requests").status_code == 429

    # GET endpoints are outside the mutating-methods scope entirely.
    assert client.get("/v1/trading/status").status_code != 429
    # Probe paths are exempt outright.
    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 200
