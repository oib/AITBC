"""#1544: RateLimitMiddleware ``methods``/``include_paths`` scoping + service wiring.

The audit found trading and pool-hub had no rate limiting on mutating
endpoints. The shared middleware gained two opt-in scopes so a service can
limit only mutating methods (read polling is never throttled) and stack a
tighter limiter on a few anonymous write paths. These tests pin both the
mechanism and the wiring.
"""

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc.rate_limiting import RateLimitMiddleware

REPO_ROOT = Path(__file__).resolve().parents[1]

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _scoped_app(rate: int = 2, per: int = 60, **kwargs: object) -> FastAPI:
    """Minimal app: one mutating route, one read route, one exempt path."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rate=rate, per=per, **kwargs)  # type: ignore[arg-type]

    @app.post("/mutate")
    async def mutate() -> dict[str, str]:
        return {"ok": "mutated"}

    @app.get("/read")
    async def read() -> dict[str, str]:
        return {"ok": "read"}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return app


@pytest.fixture(autouse=True)
def _rate_limiting_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("NODE_ENV", raising=False)


class TestMethodsScope:
    """``methods`` limits only the listed HTTP methods."""

    def test_mutating_methods_are_limited_reads_are_not(self) -> None:
        client = TestClient(_scoped_app(rate=3, methods=MUTATING))

        for _ in range(3):
            assert client.post("/mutate").status_code == 200
        assert client.post("/mutate").status_code == 429

        # GETs are not counted at all — read polling can never trip the limit.
        for _ in range(10):
            assert client.get("/read").status_code == 200

    def test_exempt_paths_bypass_even_for_mutating_methods(self) -> None:
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            rate=1,
            per=60,
            methods=MUTATING,
            exclude_paths=["/health"],
        )

        @app.post("/health")
        async def health_post() -> dict[str, str]:
            return {"ok": "health"}

        @app.post("/mutate")
        async def mutate() -> dict[str, str]:
            return {"ok": "mutated"}

        client = TestClient(app)
        assert client.post("/health").status_code == 200
        assert client.post("/health").status_code == 200
        assert client.post("/mutate").status_code == 200
        assert client.post("/mutate").status_code == 429

    def test_default_still_limits_every_method(self) -> None:
        """Backward compatibility: no ``methods`` means all requests count."""
        client = TestClient(_scoped_app())

        assert client.get("/read").status_code == 200
        assert client.get("/read").status_code == 200
        assert client.get("/read").status_code == 429


class TestIncludePathsScope:
    """``include_paths`` limits only the listed exact paths."""

    def test_only_listed_paths_are_counted(self) -> None:
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            rate=2,
            per=60,
            methods=MUTATING,
            include_paths=["/strict"],
        )

        @app.post("/strict")
        async def strict() -> dict[str, str]:
            return {"ok": "strict"}

        @app.post("/other")
        async def other() -> dict[str, str]:
            return {"ok": "other"}

        client = TestClient(app)
        assert client.post("/strict").status_code == 200
        assert client.post("/strict").status_code == 200
        assert client.post("/strict").status_code == 429
        # Unlisted paths pass through this limiter entirely.
        for _ in range(5):
            assert client.post("/other").status_code == 200


def _registered_middleware(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_middleware"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "RateLimitMiddleware"
    ]


def _kwarg(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


class TestServiceWiring:
    """Static pins: trading and pool-hub must keep a rate limiter registered."""

    def test_trading_registers_mutating_scoped_limiter(self) -> None:
        calls = _registered_middleware(REPO_ROOT / "apps/trading/src/trading_service/main.py")
        assert calls, "trading_service.main.py registers no RateLimitMiddleware (#1544)"
        call = calls[0]
        methods = _kwarg(call, "methods")
        assert methods is not None, "trading limiter must scope to mutating methods"
        assert _kwarg(call, "key_func") is not None
        excluded = _kwarg(call, "exclude_paths")
        assert excluded is not None

    def test_poolhub_registers_general_and_anonymous_limiters(self) -> None:
        calls = _registered_middleware(REPO_ROOT / "apps/pool-hub/src/poolhub/app/main.py")
        assert len(calls) >= 2, (
            "pool-hub needs the general mutating limiter plus the tighter anonymous-endpoint limiter (#1544)"
        )
        include = [_kwarg(c, "include_paths") for c in calls]
        assert any(v is not None for v in include), "expected an include_paths-scoped limiter"
        for call in calls:
            assert _kwarg(call, "key_func") is not None
