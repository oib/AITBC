"""Tests for ``aitbc auth login --credential-name``.

`aitbc monitor sweepers` looks up the credential stored under ``admin``, but
login used to store every token under the hardcoded name ``client`` -- there
was no CLI path to store a named admin credential. These tests pin the flag
and its default.
"""

from __future__ import annotations

from click.testing import CliRunner

from aitbc_cli.commands import auth as auth_mod
from aitbc_cli.core.main import cli

# A throwaway key that only has to be a valid secp256k1 scalar for
# Account.from_key -- it never controls funds.
_PRIVATE_KEY = "0x" + "11" * 32


class _FakeClient:
    def post(self, path, json=None, **kw):
        if path.endswith("/auth/nonce"):
            return {"nonce": "n-1"}
        if path.endswith("/login"):
            return {"session_token": "tok-123"}
        raise AssertionError(f"unexpected endpoint {path}")


def _stub_login_flow(monkeypatch, stored: list[tuple[str, str, str]]):
    """Bypass wallet resolution and coordinator HTTP; capture store_credential."""
    monkeypatch.setattr(auth_mod, "_resolve_private_key", lambda *a, **kw: _PRIVATE_KEY)
    monkeypatch.setattr(auth_mod, "AITBCHTTPClient", lambda *a, **kw: _FakeClient())

    def _store(self, name, token, environment="default"):
        stored.append((name, token, environment))
        return True

    monkeypatch.setattr(auth_mod.AuthManager, "store_credential", _store)


def test_login_stores_under_client_by_default(monkeypatch):
    stored: list[tuple[str, str, str]] = []
    _stub_login_flow(monkeypatch, stored)
    result = CliRunner().invoke(
        cli, ["auth", "login", "--private-key", _PRIVATE_KEY, "--coordinator-url", "http://coord.test"]
    )
    assert result.exit_code == 0, result.output
    assert stored == [("client", "tok-123", "default")]


def test_login_credential_name_admin(monkeypatch):
    stored: list[tuple[str, str, str]] = []
    _stub_login_flow(monkeypatch, stored)
    result = CliRunner().invoke(
        cli,
        [
            "auth",
            "login",
            "--private-key",
            _PRIVATE_KEY,
            "--coordinator-url",
            "http://coord.test",
            "--credential-name",
            "admin",
        ],
    )
    assert result.exit_code == 0, result.output
    assert stored == [("admin", "tok-123", "default")]


def test_logout_honours_credential_name(monkeypatch):
    deleted: list[str] = []

    def _delete(self, name, environment="default"):
        deleted.append(name)
        return True

    monkeypatch.setattr(auth_mod.AuthManager, "delete_credential", _delete)
    result = CliRunner().invoke(cli, ["auth", "logout", "--credential-name", "admin"])
    assert result.exit_code == 0, result.output
    assert deleted == ["admin"]
