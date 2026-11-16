"""#2138 pins: monitor/dashboard surface the auth-login hint on coordinator 401s.

The fleet's stale-JWT 401s (#2090/#2094) printed raw network errors on
``monitor``/``dashboard`` while ``ai``/``tee`` already had the #2095 hint.
These pins cover: the client-credential expiry pre-check
(``AuthManager.get_client_token`` → ``ExpiredClientToken``), the
rejected-vs-missing hint split, the shop dashboard's client-credential
fallback for ANY-level endpoints, and the warn-once 401 hint in the
dashboard safe-GET helpers.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any, cast

import pytest
import requests
from click.testing import CliRunner

import aitbc_cli.commands.dashboard as dashboard_mod
import aitbc_cli.commands.monitor as monitor_mod
from aitbc_cli import auth as auth_pkg
from aitbc_cli.auth import AuthManager, ExpiredClientToken
from aitbc_cli.commands import dashboard, monitor  # noqa: F401 — register commands
from aitbc_cli.core.main import cli
from aitbc_cli.utils.error_handling import LOGIN_HINT, LOGIN_REJECTED_HINT
from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError


def _jwt(payload: dict) -> str:
    def seg(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'HS256', 'typ': 'JWT'})}.{seg(payload)}.sig"


def _network_error(status: int) -> NetworkError:
    resp = requests.models.Response()
    resp.status_code = status
    resp.url = "http://node.test/v1/monitoring/metrics"
    err = NetworkError(f"GET request failed: {status} Client Error")
    err.__cause__ = requests.HTTPError(f"{status} Client Error", response=resp)
    return err


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# AuthManager.get_client_token — expiry pre-check
# ---------------------------------------------------------------------------


def test_get_client_token_returns_stored_token(monkeypatch):
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, *a, **kw: "plain-api-key")
    assert AuthManager().get_client_token() == "plain-api-key"


def test_get_client_token_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, *a, **kw: None)
    assert AuthManager().get_client_token() is None


def test_get_client_token_expired_jwt_raises(monkeypatch):
    expired = _jwt({"exp": 1, "sub": "u", "type": "access"})
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, *a, **kw: expired)
    with pytest.raises(ExpiredClientToken, match="auth login"):
        AuthManager().get_client_token()


def test_get_client_token_unexpired_jwt_returns(monkeypatch):
    fresh = _jwt({"exp": 4_000_000_000, "sub": "u", "type": "access"})
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, *a, **kw: fresh)
    assert AuthManager().get_client_token() == fresh


def test_get_client_token_no_exp_claim_returns(monkeypatch):
    """Pre-#1185 fleet tokens carry no exp — they are not 'expired'."""
    noexp = _jwt({"sub": "u", "type": "access"})
    monkeypatch.setattr(AuthManager, "get_credential", lambda self, *a, **kw: noexp)
    assert AuthManager().get_client_token() == noexp


# ---------------------------------------------------------------------------
# monitor._login_hint — rejected vs missing
# ---------------------------------------------------------------------------


class _Ctx:
    def __init__(self, obj: dict[str, Any]):
        self.obj = obj


def _config(api_key: str | None = None):
    return SimpleNamespace(api_key=api_key, coordinator_api_url="http://node.test:8203")


def test_monitor_login_hint_rejected_with_stored_credential(monkeypatch):
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: "tok")
    ctx = _Ctx({"config": _config(), "output_format": "table"})
    assert monitor_mod._login_hint(ctx) == LOGIN_REJECTED_HINT


def test_monitor_login_hint_missing_without_credential(monkeypatch):
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: None)
    ctx = _Ctx({"config": _config(), "output_format": "table"})
    assert monitor_mod._login_hint(ctx) == LOGIN_HINT


def test_monitor_login_hint_rejected_with_api_key(monkeypatch):
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: None)
    ctx = _Ctx({"config": _config(), "api_key": "k", "output_format": "table"})
    assert monitor_mod._login_hint(ctx) == LOGIN_REJECTED_HINT


# ---------------------------------------------------------------------------
# monitor commands — 401 surfaces the hint
# ---------------------------------------------------------------------------


def _stub_monitor_store_empty(monkeypatch):
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: None)
    monkeypatch.setattr(auth_pkg.AuthManager, "get_client_token", lambda self, *a, **kw: None)


def test_monitor_metrics_401_prints_login_hint(runner, monkeypatch):
    _stub_monitor_store_empty(monkeypatch)

    def _boom(self, endpoint, **kw):
        raise _network_error(401)

    monkeypatch.setattr(monitor_mod.AITBCHTTPClient, "get", _boom, raising=True)
    result = runner.invoke(cli, ["--output", "json", "monitor", "metrics", "--period", "1h"])
    assert LOGIN_HINT in result.output
    assert LOGIN_REJECTED_HINT not in result.output


def test_monitor_sweepers_401_aborts_with_hint(runner, monkeypatch):
    _stub_monitor_store_empty(monkeypatch)
    monkeypatch.setattr(auth_pkg.AuthManager, "get_admin_token", lambda self, *a, **kw: None)

    def _boom(self, endpoint, **kw):
        raise _network_error(401)

    monkeypatch.setattr(monitor_mod.AITBCHTTPClient, "get", _boom, raising=True)
    result = runner.invoke(cli, ["monitor", "sweepers"])
    assert result.exit_code != 0
    assert LOGIN_HINT in result.output


def test_monitor_metrics_expired_client_fails_fast(runner, monkeypatch):
    """An expired stored client JWT raises before any request is made."""
    monkeypatch.setattr(
        auth_pkg.AuthManager,
        "get_client_token",
        lambda self, *a, **kw: (_ for _ in ()).throw(
            ExpiredClientToken("The stored client credential has expired. Run `aitbc auth login` to refresh it.")
        ),
    )

    def _boom(self, endpoint, **kw):  # pragma: no cover - must not be reached
        raise AssertionError("request should not be attempted")

    monkeypatch.setattr(monitor_mod.AITBCHTTPClient, "get", _boom, raising=True)
    result = runner.invoke(cli, ["--output", "json", "monitor", "metrics", "--period", "1h"])
    assert "auth login" in result.output


# ---------------------------------------------------------------------------
# dashboard — client fallback + warn-once hint
# ---------------------------------------------------------------------------


def test_coord_headers_prefers_miner_over_client(monkeypatch):
    monkeypatch.setattr(dashboard_mod, "_miner_env", lambda: {"MINER_API_KEY": "mk", "MINER_ID": "m1"})
    monkeypatch.setattr(auth_pkg.AuthManager, "get_client_token", lambda self, *a, **kw: "ct")
    headers = dashboard_mod._coord_headers({"api_key": None})
    assert headers is not None and headers.get("X-Api-Key") == "mk"


def test_coord_headers_falls_back_to_client(monkeypatch):
    monkeypatch.setattr(dashboard_mod, "_miner_env", lambda: {})
    monkeypatch.setattr(auth_pkg.AuthManager, "get_client_token", lambda self, *a, **kw: "ct")
    headers = dashboard_mod._coord_headers({})
    assert headers == {"Authorization": "Bearer ct"}


def test_coord_headers_none_when_no_credential(monkeypatch):
    monkeypatch.setattr(dashboard_mod, "_miner_env", lambda: {})
    monkeypatch.setattr(auth_pkg.AuthManager, "get_client_token", lambda self, *a, **kw: None)
    assert dashboard_mod._coord_headers({}) is None


def test_auth_headers_client_uses_get_client_token(monkeypatch):
    monkeypatch.setattr(auth_pkg.AuthManager, "get_client_token", lambda self, *a, **kw: "ct")
    assert dashboard_mod._auth_headers({}) == {"Authorization": "Bearer ct"}


def test_warn_unauthorized_once_picks_hint_by_credential(monkeypatch, capsys):
    dashboard_mod._AUTH_HINT_SHOWN = False

    class _C:
        headers = {"Authorization": "Bearer x"}

    dashboard_mod._warn_unauthorized_once(cast(AITBCHTTPClient, _C()))
    out = capsys.readouterr().out
    assert LOGIN_REJECTED_HINT in out

    dashboard_mod._AUTH_HINT_SHOWN = False

    class _C2:
        headers = {}

    dashboard_mod._warn_unauthorized_once(cast(AITBCHTTPClient, _C2()))
    out = capsys.readouterr().out
    assert LOGIN_HINT in out


def test_warn_unauthorized_once_is_once(monkeypatch, capsys):
    dashboard_mod._AUTH_HINT_SHOWN = False

    class _C:
        headers = {}

    dashboard_mod._warn_unauthorized_once(cast(AITBCHTTPClient, _C()))
    dashboard_mod._warn_unauthorized_once(cast(AITBCHTTPClient, _C()))
    assert capsys.readouterr().out.count(LOGIN_HINT) == 1
    dashboard_mod._AUTH_HINT_SHOWN = False


def test_safe_get_401_warns_with_rejected_hint(monkeypatch, capsys):
    dashboard_mod._AUTH_HINT_SHOWN = False

    class _C:
        headers = {"Authorization": "Bearer x"}

        def get_json(self, path, params=None):
            raise _network_error(401)

    assert dashboard_mod._safe_get(cast(AITBCHTTPClient, _C()), "/v1/jobs") is None
    assert LOGIN_REJECTED_HINT in capsys.readouterr().out
    dashboard_mod._AUTH_HINT_SHOWN = False
