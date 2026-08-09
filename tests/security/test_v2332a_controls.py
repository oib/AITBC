"""V23-32a: the two controls feature_flags.json reported as enabled at 100% rollout.

``strict_cors_enforcement`` and ``enable_marketplace_rate_limiting`` were both marked
``enabled: true``, ``rollout_percentage: 100.0``, dated 2026-05-24, in a manifest no code
read. Neither existed. These tests are the difference between a claim and a control.
"""

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc.middleware.cors import setup_cors
from aitbc.rate_limiting import RateLimitMiddleware

REPO_ROOT = Path(__file__).parents[2]

SKIP_DIRS = {".claude", "harness", "node_modules", "graphify-out", "tmp", "__pycache__", ".venv", "venv"}


# --------------------------------------------------------------------------------------
# CORS: omitting the allowlist must fail, not default to wildcard
# --------------------------------------------------------------------------------------


def test_setup_cors_requires_explicit_origins() -> None:
    """Saying nothing about CORS must not be a way to get ``["*"]``."""
    app = FastAPI()

    with pytest.raises(ValueError, match="requires allow_origins"):
        setup_cors(app)


def test_setup_cors_still_allows_deliberate_wildcard() -> None:
    """A public API can still opt in — the requirement is that it be written down."""
    app = FastAPI()
    setup_cors(app, allow_origins=["*"], allow_credentials=False)


def _iter_app_sources() -> list[Path]:
    apps = REPO_ROOT / "apps"
    return [p for p in apps.rglob("*.py") if not SKIP_DIRS.intersection(p.parts) and "test" not in p.name]


def test_no_service_calls_setup_cors_without_origins() -> None:
    """Static check, so this is caught at review rather than at whichever app starts first."""
    offenders: list[str] = []

    for path in _iter_app_sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setup_cors"):
                continue
            has_origins = any(kw.arg == "allow_origins" for kw in node.keywords) or len(node.args) >= 2
            if not has_origins:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert not offenders, f"setup_cors called without an explicit allowlist: {offenders}"


def test_coordinator_config_rejects_wildcard_origins() -> None:
    """coordinator-api sends credentials, so '*' there is not 'public' — it is 'any site,
    authenticated as the user'. Its two call sites build CORSMiddleware directly and so
    bypass the setup_cors guard; the config validator is what covers them."""
    pytest.importorskip("coordinator_api", reason="coordinator-api not on the path")
    from coordinator_api.config import Settings  # type: ignore[import-not-found]

    with pytest.raises(ValueError, match=r"cannot contain"):
        Settings(allow_origins=["*"])


# --------------------------------------------------------------------------------------
# Rate limiting: the marketplace had none
# --------------------------------------------------------------------------------------


def _set_environment(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Pin the environment ``aitbc.utils.env`` will read.

    It checks ENVIRONMENT, then APP_ENV, then NODE_ENV, so setting only one of them leaves
    the answer dependent on what the developer happens to have exported.
    """
    monkeypatch.setenv("ENVIRONMENT", name)
    monkeypatch.setenv("APP_ENV", name)
    monkeypatch.delenv("NODE_ENV", raising=False)


def _app_with_limit(rate: int = 3, **kwargs: object) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rate=rate, per=60, **kwargs)

    @app.get("/thing")
    async def thing() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return app


def test_requests_over_the_limit_get_429_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AITBC_ENABLE_RATE_LIMITING", raising=False)
    client = TestClient(_app_with_limit(rate=3))

    assert [client.get("/thing").status_code for _ in range(3)] == [200, 200, 200]

    blocked = client.get("/thing")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"


def test_the_429_body_is_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """The middleware used to build its body with an f-string into a JSON literal, so a
    quote or backslash in the message produced malformed JSON. Assert on the parsed body."""
    monkeypatch.delenv("AITBC_ENABLE_RATE_LIMITING", raising=False)
    message = 'Rate limit exceeded: try "later" \\ again'
    client = TestClient(_app_with_limit(rate=1, error_message=message))

    client.get("/thing")
    blocked = client.get("/thing")

    assert blocked.status_code == 429
    assert blocked.json() == {"detail": message}


def test_excluded_paths_are_not_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probes poll from a fixed address on a fixed interval. If they consume the budget, the
    orchestrator exhausts it and then reads its own 429 as the service being unhealthy."""
    monkeypatch.delenv("AITBC_ENABLE_RATE_LIMITING", raising=False)
    client = TestClient(_app_with_limit(rate=2, exclude_paths=["/health"]))

    for _ in range(10):
        assert client.get("/health").status_code == 200

    assert client.get("/thing").status_code == 200
    assert client.get("/thing").status_code == 200
    assert client.get("/thing").status_code == 429


def test_the_disable_switch_is_honoured_by_the_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    """The decorator consulted AITBC_ENABLE_RATE_LIMITING and the middleware did not, so the
    switch worked or was ignored depending on which mechanism a service happened to use."""
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    _set_environment(monkeypatch, "development")
    client = TestClient(_app_with_limit(rate=1))

    assert [client.get("/thing").status_code for _ in range(5)] == [200] * 5


def test_production_cannot_disable_the_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same rule the decorator has always had: the switch is a development convenience."""
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    _set_environment(monkeypatch, "production")
    client = TestClient(_app_with_limit(rate=1))

    assert client.get("/thing").status_code == 200
    assert client.get("/thing").status_code == 429


def test_marketplace_app_has_rate_limiting_wired_up() -> None:
    """The finding was not "the limit is wrong", it was "there is no limit"."""
    marketplace_main = REPO_ROOT / "apps/marketplace/src/marketplace_service/main.py"
    tree = ast.parse(marketplace_main.read_text(encoding="utf-8"))

    added = {
        node.args[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_middleware"
        and node.args
        and isinstance(node.args[0], ast.Name)
    }

    assert "RateLimitMiddleware" in added, (
        "apps/marketplace has no rate limiting middleware. It had none at all when "
        "feature_flags.json reported enable_marketplace_rate_limiting as on at 100% rollout "
        "(V23-32a); do not remove it without replacing the control."
    )
