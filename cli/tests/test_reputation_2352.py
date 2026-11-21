"""#2352: reputation writes must prefer the stored admin credential.

``aitbc reputation create-profile`` / ``feedback`` used to send only the
``client`` credential slot, so an operator/admin wallet stored under
``admin@default`` could never pass the coordinator's self-or-admin /
admin-or-client gates (403 "can only modify your own reputation profile").
The write commands now resolve ``credential="admin"`` — admin slot first,
client JWT fallback — matching the dispute/governance precedent (#2246).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.reputation as reputation_mod
from aitbc_cli import auth as auth_pkg
from aitbc_cli.utils.error_handling import CLIError

JWT = "eyJhbGciOi.fake.token"


class _FakeClient:
    """Captures constructor kwargs; returns canned write responses."""

    captured: dict[str, Any] = {}

    def __init__(self, base_url: str, timeout: int, **kwargs: Any):
        type(self).captured = {"base_url": base_url, "timeout": timeout, **kwargs}

    def get(self, path: str, params: Any = None) -> dict[str, Any]:
        return {}

    def post(self, path: str, json: Any = None) -> dict[str, Any]:
        return {"agent_id": "agent-1", "id": "fb-1", "trust_score": 0}


@pytest.fixture
def wired(monkeypatch):
    """Patch config, credential store and HTTP client for reputation commands."""
    monkeypatch.setattr(
        reputation_mod,
        "get_config",
        lambda: SimpleNamespace(coordinator_api_url="http://coord:8203", api_key=None),
    )
    monkeypatch.setattr(reputation_mod, "AITBCHTTPClient", _FakeClient)
    _FakeClient.captured = {}
    return _FakeClient


def test_write_commands_use_admin_credential(wired, monkeypatch):
    """create-profile and feedback resolve credential="admin" (admin slot,
    client fallback) so an admin JWT reaches the self-or-admin gate."""
    seen: list[str] = []
    real_kwargs = reputation_mod.auth_client_kwargs

    def spy(*args: Any, **kwargs: Any):
        seen.append(kwargs.get("credential", "client"))
        return real_kwargs(*args, **kwargs)

    monkeypatch.setattr(reputation_mod, "auth_client_kwargs", spy)
    monkeypatch.setattr(auth_pkg.AuthManager, "get_admin_token", lambda self, **kw: JWT)

    runner = CliRunner()
    result = runner.invoke(reputation_mod.reputation, ["create-profile", "--agent-id", "agent-1"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        reputation_mod.reputation,
        ["feedback", "--agent-id", "agent-1", "--job-id", "job-1"],
    )
    assert result.exit_code == 0, result.output
    assert seen == ["admin", "admin"]
    assert wired.captured["headers"] == {"Authorization": f"Bearer {JWT}"}


def test_read_commands_keep_client_credential(wired, monkeypatch):
    """Reads stay on the client slot — the routes are public anyway."""
    seen: list[str] = []
    real_kwargs = reputation_mod.auth_client_kwargs

    def spy(*args: Any, **kwargs: Any):
        seen.append(kwargs.get("credential", "client"))
        return real_kwargs(*args, **kwargs)

    monkeypatch.setattr(reputation_mod, "auth_client_kwargs", spy)
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: JWT)

    runner = CliRunner()
    result = runner.invoke(reputation_mod.reputation, ["metrics"])
    assert result.exit_code == 0, result.output
    assert seen == ["client"]


def test_expired_admin_token_aborts_with_login_hint(wired, monkeypatch):
    """An expired stored admin JWT fails fast with a re-login hint, not a 401."""

    def _expired(self, **kw):
        raise auth_pkg.ExpiredAdminToken("The stored admin credential has expired. Run `aitbc auth login` to refresh it.")

    monkeypatch.setattr(auth_pkg.AuthManager, "get_admin_token", _expired)
    with pytest.raises(CLIError, match="auth login"):
        reputation_mod._coordinator_client(None, credential="admin")
