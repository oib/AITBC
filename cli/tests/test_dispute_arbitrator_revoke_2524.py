"""AUDIT-DISPUTE-REVOKE-FLAG-1 (#2524): `dispute arbitrator authorize`
must route `--revoke` to /rpc/disputes/arbitrators/revoke.

Before the fix the CLI always posted to /authorize with
``authorized=false`` on revoke, and the node ignored the flag — granting
authorization when the operator asked for revocation. The grant path must
keep posting ``authorized: true`` to /authorize; the revoke path must post
to /revoke without an ``authorized`` field (RevokeArbitratorRequest has
none).
"""

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.dispute as dispute_mod
from aitbc_cli.commands.dispute import dispute

ARB = "0x" + "ab" * 20


class _RecordingClient:
    def __init__(self):
        self.posts: list[tuple[str, dict]] = []

    def post(self, path, json=None):
        self.posts.append((path, json))
        return {"success": True, "status": "ok", "message": "done"}

    def close(self):
        pass


@pytest.fixture
def runner():
    return CliRunner()


def _patch(monkeypatch, client):
    monkeypatch.setattr(dispute_mod, "_chain_client", lambda *a, **kw: client)
    monkeypatch.setattr(
        dispute_mod,
        "get_config",
        lambda *a, **kw: SimpleNamespace(
            blockchain_rpc_url="http://rpc",
            blockchain_rpc_api_key=None,
            timeout=10,
            wallet_address=None,
        ),
    )


def test_authorize_grant_posts_authorize_route(runner, monkeypatch):
    client = _RecordingClient()
    _patch(monkeypatch, client)
    result = runner.invoke(
        dispute,
        ["arbitrator", "authorize", ARB, "--signature", "0xsig", "--format", "json"],
        obj={},
    )
    assert result.exit_code == 0, result.output
    assert client.posts == [
        ("/rpc/disputes/arbitrators/authorize", {"arbitrator_address": ARB, "authorized": True, "owner_signature": "0xsig"})
    ]
    assert json.loads(result.output)["success"] is True


def test_authorize_revoke_posts_revoke_route(runner, monkeypatch):
    client = _RecordingClient()
    _patch(monkeypatch, client)
    result = runner.invoke(
        dispute,
        ["arbitrator", "authorize", ARB, "--revoke", "--signature", "0xsig", "--format", "json"],
        obj={},
    )
    assert result.exit_code == 0, result.output
    # The revoke route's request model carries no `authorized` flag.
    assert client.posts == [("/rpc/disputes/arbitrators/revoke", {"arbitrator_address": ARB, "owner_signature": "0xsig"})]
    assert "authorized" not in client.posts[0][1]


def test_authorize_revoke_without_signature(runner, monkeypatch):
    client = _RecordingClient()
    _patch(monkeypatch, client)
    result = runner.invoke(dispute, ["arbitrator", "authorize", ARB, "--revoke"], obj={})
    assert result.exit_code == 0, result.output
    assert client.posts == [("/rpc/disputes/arbitrators/revoke", {"arbitrator_address": ARB})]
