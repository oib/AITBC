"""CLI-AUTHHINT-1: a missing credential prints one login-hint line and exits non-zero.

Before: commands printed ``No stored credential found for 'client' in
'default'`` (a non-quiet store read) and then a raw 401. Now the lookup is
quiet and a 401 on an authenticated endpoint aborts with the single hint
line; anonymous-OK endpoints are unaffected (no early credential gate).
"""

import pytest
import requests
from click.testing import CliRunner

import aitbc_cli.commands.ai as ai_mod
from aitbc_cli import auth as auth_pkg
from aitbc_cli.commands.ai import ai
from aitbc_cli.utils.error_handling import LOGIN_HINT, LOGIN_REJECTED_HINT, is_unauthorized
from aitbc_cli.utils.http_client import NetworkError


@pytest.fixture
def runner():
    return CliRunner()


def _http_error(status: int) -> requests.HTTPError:
    resp = requests.models.Response()
    resp.status_code = status
    resp.url = "http://node.test/v1/jobs"
    return requests.HTTPError(f"{status} Client Error", response=resp)


def _network_error(status: int) -> NetworkError:
    err = NetworkError(f"GET request failed: {_http_error(status)}")
    err.__cause__ = _http_error(status)
    return err


def test_is_unauthorized_detects_401():
    assert is_unauthorized(_network_error(401))
    assert not is_unauthorized(_network_error(500))
    assert not is_unauthorized(ValueError("x"))


def test_hint_is_one_line_and_names_login():
    assert "\n" not in LOGIN_HINT
    assert "aitbc auth login --wallet <name>" in LOGIN_HINT


class _BoomClient:
    error: NetworkError

    def __init__(self, *a, **kw):
        pass

    def get(self, path, params=None):
        raise self.error

    def post(self, *a, **kw):
        raise self.error

    def close(self):
        pass


def _stub_jobs(monkeypatch, error):
    class C(_BoomClient):
        pass

    C.error = error
    monkeypatch.setattr(ai_mod, "AITBCHTTPClient", C)


def _stub_empty_store(monkeypatch):
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: None)


def _stub_stored_token(monkeypatch, token):
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: token)


def test_ai_jobs_401_prints_login_hint(runner, monkeypatch):
    _stub_jobs(monkeypatch, _network_error(401))
    _stub_empty_store(monkeypatch)
    result = runner.invoke(ai, obj={"output_format": "table"}, args=["jobs"])
    assert result.exit_code != 0
    assert LOGIN_HINT in result.output
    assert LOGIN_REJECTED_HINT not in result.output
    assert "No stored credential found" not in result.output


def test_ai_jobs_401_with_stored_credential_prints_rejected_hint(runner, monkeypatch):
    """#2095: a stored-but-rejected token must not claim 'No login'."""
    _stub_jobs(monkeypatch, _network_error(401))
    _stub_stored_token(monkeypatch, "eyJhbGciOi.fake.token")
    result = runner.invoke(ai, obj={"output_format": "table"}, args=["jobs"])
    assert result.exit_code != 0
    assert LOGIN_REJECTED_HINT in result.output
    assert LOGIN_HINT not in result.output


def test_ai_jobs_401_with_api_key_prints_rejected_hint(runner, monkeypatch):
    _stub_jobs(monkeypatch, _network_error(401))
    _stub_empty_store(monkeypatch)
    result = runner.invoke(ai, obj={"output_format": "table", "api_key": "k"}, args=["jobs"])
    assert result.exit_code != 0
    assert LOGIN_REJECTED_HINT in result.output


class _Ctx:
    def __init__(self, obj):
        self.obj = obj


def test_auth_headers_jwt_goes_bearer(monkeypatch):
    _stub_stored_token(monkeypatch, "eyJhbGciOi.fake.token")
    assert ai_mod._auth_headers(_Ctx({})) == {"Authorization": "Bearer eyJhbGciOi.fake.token"}


def test_auth_headers_api_key_goes_x_api_key(monkeypatch):
    """#2095 nit: a non-JWT stored credential is an API key, not a Bearer token."""
    _stub_stored_token(monkeypatch, "deadbeef")
    assert ai_mod._auth_headers(_Ctx({})) == {"X-API-Key": "deadbeef"}


def test_auth_headers_explicit_api_key_non_jwt(monkeypatch):
    _stub_empty_store(monkeypatch)
    assert ai_mod._auth_headers(_Ctx({"api_key": "deadbeef"})) == {"X-API-Key": "deadbeef"}


def test_ai_jobs_500_keeps_network_error(runner, monkeypatch):
    _stub_jobs(monkeypatch, _network_error(500))
    result = runner.invoke(ai, obj={"output_format": "table"}, args=["jobs"])
    assert result.exit_code != 0
    assert LOGIN_HINT not in result.output
    assert "Network error" in result.output


def test_zk_health_makes_no_credential_store_call(monkeypatch):
    """zk's _auth_headers reads ctx.obj only — no AuthManager store access."""
    import aitbc_cli.commands.zk as zk_mod
    from aitbc_cli import auth as auth_pkg

    class _Exploding:
        def get_credential(self, *a, **kw):
            raise AssertionError("store must not be read")

    monkeypatch.setattr(auth_pkg, "AuthManager", _Exploding)

    class _Ctx:
        obj = {"api_key": None}

    assert zk_mod._auth_headers(_Ctx()) is None
