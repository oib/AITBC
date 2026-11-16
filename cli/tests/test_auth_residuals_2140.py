"""#2140 pins: CLI-AUTH-RESIDUALS-1.

Item 1 — near-expiry pre-warning: ``warn_within_seconds`` on
``AuthManager.get_client_token``/``get_admin_token`` and
``auth_client_kwargs`` warns once per token before the JWT dies, instead of
surfacing only a bare 401 after expiry.

Item 2 — dashboard shop degradation: ``dashboard shop`` skips the
MINER-level ``/v1/miners/*`` calls when the resolved coordinator header is
a Bearer JWT (client/admin role can only 403 there), degrading to the
shop-scoped endpoint set rather than firing doomed requests.
"""

from __future__ import annotations

import base64
import json
import time
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.dashboard as dashboard_mod
from aitbc_cli import auth as auth_pkg
from aitbc_cli.auth import AuthManager, ExpiredClientToken, _NEAR_EXPIRY_WARNED
from aitbc_cli.commands import dashboard, monitor  # noqa: F401 — register commands
from aitbc_cli.core.main import cli
from aitbc_cli.utils.http_client import auth_client_kwargs


def _jwt(claims: dict[str, Any]) -> str:
    def seg(obj: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'HS256'})}.{seg(claims)}.sig"


@pytest.fixture(autouse=True)
def _clear_warn_dedup():
    _NEAR_EXPIRY_WARNED.clear()
    yield
    _NEAR_EXPIRY_WARNED.clear()


# ---------------------------------------------------------------------------
# item 1 — near-expiry warning
# ---------------------------------------------------------------------------


def test_get_client_token_warns_once_when_near_expiry(monkeypatch, capsys):
    token = _jwt({"exp": time.time() + 3600, "sub": "u"})
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, *a, **kw: token)
    mgr = AuthManager()
    assert mgr.get_client_token(warn_within_seconds=86400) == token
    mgr.get_client_token(warn_within_seconds=86400)
    out = capsys.readouterr().out
    assert out.count("aitbc auth login") == 1
    assert "expires in" in out


def test_get_client_token_no_warn_when_far_from_expiry(monkeypatch, capsys):
    token = _jwt({"exp": time.time() + 30 * 86400, "sub": "u"})
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, *a, **kw: token)
    assert AuthManager().get_client_token(warn_within_seconds=86400) == token
    assert "expires in" not in capsys.readouterr().out


def test_get_client_token_no_exp_claim_stays_silent(monkeypatch, capsys):
    """Pre-#1185 fleet tokens carry no exp — not 'near expiry' either."""
    token = _jwt({"sub": "u"})
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, *a, **kw: token)
    assert AuthManager().get_client_token(warn_within_seconds=86400) == token
    assert "expires in" not in capsys.readouterr().out


def test_get_client_token_expired_raises_before_warn(monkeypatch):
    token = _jwt({"exp": time.time() - 10, "sub": "u"})
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, *a, **kw: token)
    with pytest.raises(ExpiredClientToken):
        AuthManager().get_client_token(warn_within_seconds=86400)


def test_get_admin_token_warns_near_expiry(monkeypatch, capsys):
    token = _jwt({"exp": time.time() + 7200, "sub": "u"})
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, kind, *a, **kw: token if kind == "admin" else None)
    assert AuthManager().get_admin_token(warn_within_seconds=86400) == token
    assert "expires in" in capsys.readouterr().out


def test_auth_client_kwargs_warns_on_resolved_jwt(monkeypatch, capsys):
    token = _jwt({"exp": time.time() + 3600, "sub": "u"})
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: token)
    kwargs = auth_client_kwargs(credential="client", warn_within_seconds=86400)
    assert kwargs == {"headers": {"Authorization": f"Bearer {token}"}}
    assert "expires in" in capsys.readouterr().out


def test_auth_client_kwargs_warns_on_explicit_key_too(monkeypatch, capsys):
    """An explicit --api-key JWT near expiry warns as well — it is the sent credential."""
    token = _jwt({"exp": time.time() + 3600, "sub": "u"})
    kwargs = auth_client_kwargs(explicit_key=token, warn_within_seconds=86400)
    assert kwargs == {"headers": {"Authorization": f"Bearer {token}"}}
    assert "expires in" in capsys.readouterr().out


def test_auth_client_kwargs_no_warn_by_default(monkeypatch, capsys):
    token = _jwt({"exp": time.time() + 3600, "sub": "u"})
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: token)
    auth_client_kwargs(credential="client")
    assert "expires in" not in capsys.readouterr().out


def test_auth_client_kwargs_non_jwt_key_no_warn(capsys):
    kwargs = auth_client_kwargs(explicit_key="plain-key", warn_within_seconds=86400)
    assert kwargs == {"api_key": "plain-key"}
    assert "expires in" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# item 2 — dashboard shop degrades to shop-scoped endpoints
# ---------------------------------------------------------------------------


def _shop_ctx() -> dict[str, Any]:
    config = SimpleNamespace(
        api_key=None,
        blockchain_rpc_url="http://rpc.test",
        coordinator_api_url="http://coord.test:8203",
        gpu_service_url="http://gpu.test",
        hub_discovery_url=None,
        node_id="n1",
        wallet_daemon_url="http://wallet.test",
        wallet_api_key=None,
    )
    return {
        "config": config,
        "url": None,
        "api_key": None,
        "chain_id": "ait-devnet",
        "output_format": "json",
    }


def _run_shop(monkeypatch, ctx_obj: dict[str, Any]) -> tuple[Any, list[str]]:
    """Invoke ``dashboard shop`` with all network seams stubbed; return
    (result, paths passed to _safe_post_or_get)."""
    miner_posts: list[str] = []

    def spy_post(client: Any, path: str, body: dict | None = None):
        miner_posts.append(path)
        return None

    class _FakeClient:
        def __init__(self, *a: Any, **kw: Any):
            pass

        def get_json(self, path: str, params: dict | None = None):
            return {}

        def get(self, path: str, params: dict | None = None):
            return {}

        def post_json(self, path: str, body: dict | None = None):
            return {}

    monkeypatch.setattr(dashboard_mod, "AITBCHTTPClient", _FakeClient)
    monkeypatch.setattr(dashboard_mod, "_safe_post_or_get", spy_post)
    monkeypatch.setattr(dashboard_mod, "_safe_get", lambda c, p, params=None: {})
    monkeypatch.setattr(dashboard_mod, "_enrich_jobs_with_escrow", lambda jobs, url: None)
    monkeypatch.setattr(dashboard_mod, "_live_wallet_balance", lambda *a, **kw: {"balance_ait": "0"})
    monkeypatch.setattr(dashboard_mod, "_warn_unauthorized_once", lambda c: None)

    result = CliRunner().invoke(cli, ["dashboard", "shop", "--miner-id", "m1"], obj=ctx_obj)
    return result, miner_posts


def test_shop_skips_miner_calls_with_client_jwt(monkeypatch):
    """Bearer-JWT fallback → /v1/miners/* calls are skipped entirely."""
    token = _jwt({"exp": time.time() + 86400, "sub": "u"})
    monkeypatch.setattr(dashboard_mod, "_miner_env", lambda: {})
    monkeypatch.setattr(auth_pkg.AuthManager, "get_client_token", lambda self, *a, **kw: token)
    result, miner_posts = _run_shop(monkeypatch, _shop_ctx())
    assert result.exit_code == 0, result.output
    assert miner_posts == []


def test_shop_calls_miners_with_api_key(monkeypatch):
    """Miner API key present → /v1/miners/* calls still fire."""
    monkeypatch.setattr(dashboard_mod, "_miner_env", lambda: {"MINER_API_KEY": "mk", "MINER_ID": "m1"})
    monkeypatch.setattr(auth_pkg.AuthManager, "get_client_token", lambda self, *a, **kw: None)
    result, miner_posts = _run_shop(monkeypatch, _shop_ctx())
    assert result.exit_code == 0, result.output
    assert any("/v1/miners/m1/jobs" in p for p in miner_posts)
    assert any("/v1/miners/m1/earnings" in p for p in miner_posts)
