"""#1544 endpoint pins: pool-hub rate-limits mutating endpoints.

Two stacked limiters: a general mutating-endpoint budget (120/60s) and a
tighter one (30/60s) scoped to the anonymous write paths ``/v1/match`` and
``/v1/miners/register``. Each test uses a unique TEST-NET-3 peer so its
bucket is isolated.
"""

from fastapi.testclient import TestClient


def _client(ip: str) -> TestClient:
    from poolhub.app.main import app

    return TestClient(app, client=(ip, 50000), raise_server_exceptions=False)


def test_anonymous_match_endpoint_hits_tight_limit_first() -> None:
    """POST /v1/match is anonymous: the 31st call in the window is a 429."""
    client = _client("203.0.113.20")

    for _ in range(30):
        # The endpoint itself fails without a database, but the middleware
        # counts the request before routing — any non-429 status is fine here.
        assert client.post("/v1/match", json={}).status_code != 429

    assert client.post("/v1/match", json={}).status_code == 429


def test_other_mutating_paths_use_general_budget() -> None:
    """A non-anonymous mutating path is not bound by the 30/min anonymous cap."""
    client = _client("203.0.113.21")

    # /v1/miners/register is also anonymous-scoped; use an authenticated-only
    # path instead — heartbeat fails auth (401) but still counts generally.
    statuses = {client.post("/v1/miners/heartbeat", json={}).status_code for _ in range(35)}
    assert 429 not in statuses
