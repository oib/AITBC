"""#2356: grant CLI flags that the server ignores must say so.

`grant create --developer-id` and `grant vote --voting-power` were accepted
(and developer-id was even required) while the coordinator binds identity to
the auth principal and derives power from the governance profile — grants
filtered by the arg came back empty and votes tallied 0.0 with a 200.
"""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from aitbc_cli.commands.grant import create, vote


class _Client:
    def __init__(self):
        self.posts: list[tuple[str, dict]] = []

    def post(self, path, json=None):
        self.posts.append((path, json or {}))
        return {"id": "g1", "status": "voting"}

    def get_json(self, path, params=None):
        return []

    def close(self):
        pass


def test_create_warns_developer_id_ignored():
    client = _Client()
    with patch("aitbc_cli.commands.grant._get_client", return_value=client):
        result = CliRunner().invoke(
            create,
            ["--developer-id", "dev-1", "--title", "T", "--requested-amount", "10"],
            obj={"output_format": "json"},
        )
    assert result.exit_code == 0, result.output
    assert "--developer-id is ignored" in result.output
    # the arg is still sent (schema requires the field) but the server binds caller
    assert client.posts[0][1]["developer_id"] == "dev-1"


def test_create_without_developer_id_still_works():
    client = _Client()
    with patch("aitbc_cli.commands.grant._get_client", return_value=client):
        result = CliRunner().invoke(
            create,
            ["--title", "T", "--requested-amount", "10"],
            obj={"output_format": "json"},
        )
    assert result.exit_code == 0, result.output
    assert "ignored" not in result.output


def test_vote_warns_voting_power_ignored():
    client = _Client()
    with patch("aitbc_cli.commands.grant._get_client", return_value=client):
        result = CliRunner().invoke(
            vote,
            ["--grant-id", "g1", "--vote", "for", "--voting-power", "1.0"],
            obj={"output_format": "json"},
        )
    assert result.exit_code == 0, result.output
    assert "--voting-power is ignored" in result.output
