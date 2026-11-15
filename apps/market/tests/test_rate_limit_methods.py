"""#1678: the market RateLimitMiddleware counts only mutating methods.

Before this change every GET burned the same per-IP budget as POSTs, so
read polling (dashboards, explorers) was throttled alongside writes.
trading and pool-hub already pass ``methods={POST, PUT, PATCH, DELETE}``;
market now does too.

The pin is on the middleware *configuration* plus the shared middleware's
method scoping — driving 121 real requests through the app just to see a
429 would hammer the shared throwaway sqlite for no extra signal (the
trading suite already pins the 429 itself).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_market_rate_limiter_scoped_to_mutating_methods() -> None:
    """The app must register RateLimitMiddleware with methods= mutating-only."""
    from market_service.main import app

    limiters = [m for m in app.user_middleware if m.cls.__name__ == "RateLimitMiddleware"]
    assert limiters, "market app lost its RateLimitMiddleware"
    methods = limiters[0].kwargs.get("methods")
    assert methods == frozenset({"POST", "PUT", "PATCH", "DELETE"})


def test_shared_middleware_ignores_non_mutating_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    """RateLimitMiddleware(methods=...) counts only those methods — the
    contract market/trading/pool-hub all rely on.

    The suite conftest disables rate limiting globally (#1976); this pin
    needs the limiter live, so it opts back in.
    """
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "true")
    from aitbc.rate_limiting import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        rate=2,
        per=60,
        methods={"POST", "PUT", "PATCH", "DELETE"},
        exclude_paths=[],
    )

    @app.get("/x")
    async def get_x():
        return {"ok": True}

    @app.post("/x")
    async def post_x():
        return {"ok": True}

    client = TestClient(app, client=("203.0.113.30", 50000))

    # Unlimited GETs — reads are outside the methods scope entirely.
    for _ in range(10):
        assert client.get("/x").status_code == 200

    # The third POST inside the window is the 429.
    assert client.post("/x").status_code == 200
    assert client.post("/x").status_code == 200
    assert client.post("/x").status_code == 429


def test_market_limiter_keys_on_client_ip() -> None:
    """#1946: market binds loopback behind nginx — without
    key_func=client_ip_for_rate_limit every proxied caller shares the
    127.0.0.1 bucket and one client can 429 the whole service."""
    from aitbc.rate_limiting import client_ip_for_rate_limit
    from market_service.main import app

    limiters = [m for m in app.user_middleware if m.cls.__name__ == "RateLimitMiddleware"]
    assert limiters, "market app lost its RateLimitMiddleware"
    assert limiters[0].kwargs.get("key_func") is client_ip_for_rate_limit
