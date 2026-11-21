"""#2406: reputation self-service create-profile + auth status identity surfacing.

``reputation create-profile --agent-id`` used to be mandatory, but the
self-or-admin check compares the path id to the caller JWT's ``sub`` /
``agent_id`` claim — an id ``aitbc auth status`` never showed (it printed
only ``******``). ``--agent-id`` is now optional and defaults to the id on
the stored credential, and ``auth status`` decodes JWT claims so the owner
can see which id they are.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.auth as auth_cmd
import aitbc_cli.commands.reputation as reputation_mod
from aitbc_cli import auth as auth_pkg


def _jwt(payload: dict[str, Any]) -> str:
    """Build a decodable (unverified) JWT-shaped token for claim tests."""
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{body}.c2ln"


AGENT_JWT = _jwt({"sub": "agent-self-9", "agent_id": "agent-self-9", "role": "agent"})


class _FakeClient:
    """Captures requests; returns canned reputation responses."""

    captured: dict[str, Any] = {}

    def __init__(self, base_url: str, timeout: int, **kwargs: Any):
        type(self).captured = {"base_url": base_url, "timeout": timeout, **kwargs}

    def get(self, path: str, params: Any = None) -> dict[str, Any]:
        type(self).captured.setdefault("gets", []).append(path)
        return {
            "agent_id": "agent-self-9",
            "trust_score": 544.5,
            "reputation_level": "intermediate",
            "performance_rating": 3.0,
            "reliability_score": 50.0,
            "community_rating": 3.0,
            "total_earnings": 0,
            "transaction_count": 0,
            "success_rate": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "average_response_time": 1234.5,
            "average_response_time_unit": "ms",
        }

    def post(self, path: str, json: Any = None) -> dict[str, Any]:
        type(self).captured.setdefault("posts", []).append(path)
        return {"agent_id": "agent-self-9", "trust_score": 544.5, "reputation_level": "intermediate"}


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(
        reputation_mod,
        "get_config",
        lambda: SimpleNamespace(coordinator_api_url="http://coord:8203", api_key=None),
    )
    monkeypatch.setattr(reputation_mod, "AITBCHTTPClient", _FakeClient)
    _FakeClient.captured = {}
    return _FakeClient


def test_create_profile_defaults_to_credential_agent_id(wired, monkeypatch):
    """No --agent-id: the stored agent JWT's agent_id/sub becomes the path id."""
    monkeypatch.setattr(auth_pkg.AuthManager, "get_admin_token", lambda self, **kw: AGENT_JWT)

    runner = CliRunner()
    result = runner.invoke(reputation_mod.reputation, ["create-profile"])
    assert result.exit_code == 0, result.output
    assert _FakeClient.captured["posts"] == ["/reputation/profile/agent-self-9"]
    assert _FakeClient.captured["headers"] == {"Authorization": f"Bearer {AGENT_JWT}"}


def test_create_profile_explicit_agent_id_still_wins(wired, monkeypatch):
    """An explicit --agent-id is used verbatim (admin/self check stays server-side)."""
    monkeypatch.setattr(auth_pkg.AuthManager, "get_admin_token", lambda self, **kw: AGENT_JWT)

    runner = CliRunner()
    result = runner.invoke(reputation_mod.reputation, ["create-profile", "--agent-id", "other-agent"])
    assert result.exit_code == 0, result.output
    assert _FakeClient.captured["posts"] == ["/reputation/profile/other-agent"]


def test_create_profile_without_jwt_requires_agent_id(wired, monkeypatch):
    """API-key / absent credentials carry no agent identity — fail honestly."""
    monkeypatch.setattr(auth_pkg.AuthManager, "get_admin_token", lambda self, **kw: None)
    monkeypatch.setattr(
        reputation_mod,
        "get_config",
        lambda: SimpleNamespace(coordinator_api_url="http://coord:8203", api_key="plain-api-key"),
    )

    runner = CliRunner()
    result = runner.invoke(reputation_mod.reputation, ["create-profile"])
    assert result.exit_code != 0
    assert "--agent-id is required" in result.output
    assert "posts" not in _FakeClient.captured


def test_profile_prints_response_time_unit(wired, monkeypatch):
    """The table output names the average_response_time unit (ms)."""
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(reputation_mod.reputation, ["profile", "--agent-id", "agent-self-9"])
    assert result.exit_code == 0, result.output
    assert "Average Response Time: 1234.50 ms" in result.output


def test_auth_status_surfaces_credential_identities(monkeypatch):
    """`auth status` decodes stored JWTs so the caller's own id is visible."""
    monkeypatch.setattr(
        auth_pkg.AuthManager,
        "list_credentials",
        lambda self, environment=None: {"client@default": "******"},
    )
    monkeypatch.setattr(
        auth_pkg.AuthManager,
        "get_credential",
        lambda self, name, environment="default", quiet=False: AGENT_JWT if name == "client" else None,
    )

    runner = CliRunner()
    result = runner.invoke(auth_cmd.auth, ["status", "--environment", "default"], obj={"output_format": "table"})
    assert result.exit_code == 0, result.output
    assert "client@default" in result.output
    assert "subject=agent-self-9" in result.output
    assert "agent_id=agent-self-9" in result.output
    assert "role=agent" in result.output


def test_auth_status_json_includes_claims(monkeypatch):
    """JSON output carries the decoded claims alongside the masked value."""
    monkeypatch.setattr(
        auth_pkg.AuthManager,
        "list_credentials",
        lambda self, environment=None: {"client@default": "******"},
    )
    monkeypatch.setattr(
        auth_pkg.AuthManager,
        "get_credential",
        lambda self, name, environment="default", quiet=False: AGENT_JWT if name == "client" else None,
    )

    runner = CliRunner()
    result = runner.invoke(auth_cmd.auth, ["status", "--environment", "default"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["client@default"]["subject"] == "agent-self-9"
    assert payload["client@default"]["agent_id"] == "agent-self-9"
    assert payload["client@default"]["masked"] == "******"
