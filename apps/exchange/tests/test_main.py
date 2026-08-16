"""FastAPI app instantiation and route sanity checks for simple_exchange."""

from fastapi.testclient import TestClient

from apps.exchange.simple_exchange.main import app


def test_app_instantiates_and_health_responds():
    """The FastAPI app exposes the catch-all routes and /health still returns 200."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


def test_unknown_post_returns_404():
    """Unknown POST routes must 404, not 401, before auth is checked."""
    client = TestClient(app)
    response = client.post("/no-such-route", json={})
    assert response.status_code == 404
