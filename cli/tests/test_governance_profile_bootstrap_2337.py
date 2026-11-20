"""#2337 pins: `aitbc governance profile *` wraps the coordinator-api DAO
profile routes (init/delegate/power/show) — the bootstrap path for
governance voting power that economic-proposal votes tally from."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from aitbc_cli.commands.governance import governance


def _fake_client(captured: dict):
    client = MagicMock()

    def _post(path, json=None, **kw):
        captured.setdefault("posts", []).append((path, json))
        return {"success": True, "profile_id": "prof-1", "voting_power": 42.5}

    def _get_json(path, **kw):
        captured["get"] = path
        return {"profile_id": "prof-1", "user_id": "u1", "voting_power": 42.5}

    client.post = _post
    client.get_json = _get_json
    return client


def _run(args, captured):
    runner = CliRunner()
    with patch("aitbc_cli.commands.governance._coordinator_client", return_value=_fake_client(captured)):
        return runner.invoke(governance, args)


def test_profile_init_posts_admin_body():
    captured: dict = {}
    result = _run(["profile", "init", "--user-id", "0xAlice", "--voting-power", "42.5", "--format", "json"], captured)
    assert result.exit_code == 0, result.output
    path, body = captured["posts"][0]
    assert path == "/v1/governance/profiles"
    assert body == {"user_id": "0xAlice", "initial_voting_power": 42.5}


def test_profile_delegate_posts_delegatee():
    captured: dict = {}
    result = _run(
        ["profile", "delegate", "--profile-id", "prof-1", "--delegatee-id", "prof-2", "--format", "json"],
        captured,
    )
    assert result.exit_code == 0, result.output
    path, body = captured["posts"][0]
    assert path == "/v1/governance/profiles/prof-1/delegate"
    assert body == {"delegatee_id": "prof-2"}


def test_profile_power_posts_voting_power():
    captured: dict = {}
    result = _run(
        ["profile", "power", "--profile-id", "prof-1", "--voting-power", "250", "--format", "json"],
        captured,
    )
    assert result.exit_code == 0, result.output
    path, body = captured["posts"][0]
    assert path == "/v1/governance/profiles/prof-1/voting-power"
    assert body == {"voting_power": 250.0}


def test_profile_show_reads_enhanced_route():
    captured: dict = {}
    result = _run(["profile", "show", "--user-id", "0xAlice", "--format", "json"], captured)
    assert result.exit_code == 0, result.output
    assert captured["get"] == "/v1/governance-enhanced/profiles/0xAlice"


def test_profile_init_requires_user_id():
    result = CliRunner().invoke(governance, ["profile", "init"])
    assert result.exit_code != 0
