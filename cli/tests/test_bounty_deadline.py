"""#2368: `bounty deploy --deadline-height` reaches the signed body, and
`bounty status` surfaces the deadline carried on the BOUNTY_LOCK payload.
"""

import json

from click.testing import CliRunner

from aitbc_cli.commands import bounty as bounty_mod


def test_deploy_sends_deadline_height(monkeypatch):
    captured = {}

    def _fake_post_signed(ctx, path, fields, **kwargs):
        captured["path"] = path
        captured["fields"] = dict(fields)
        return {"success": True}

    monkeypatch.setattr(bounty_mod, "post_signed", _fake_post_signed)
    runner = CliRunner()
    result = runner.invoke(
        bounty_mod.bounty,
        obj={"output_format": "json"},
        args=[
            "deploy",
            "--bounty-id",
            "b-1",
            "--amount",
            "10",
            "--deadline-height",
            "12345",
            "--rpc-url",
            "http://127.0.0.1:8202",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["path"] == "/rpc/bounty/deploy"
    assert captured["fields"]["deadline_height"] == 12345


def test_deploy_omits_deadline_height_by_default(monkeypatch):
    captured = {}

    def _fake_post_signed(ctx, path, fields, **kwargs):
        captured["fields"] = dict(fields)
        return {"success": True}

    monkeypatch.setattr(bounty_mod, "post_signed", _fake_post_signed)
    runner = CliRunner()
    result = runner.invoke(
        bounty_mod.bounty,
        obj={"output_format": "json"},
        args=["deploy", "--bounty-id", "b-1", "--amount", "10", "--rpc-url", "http://127.0.0.1:8202", "--json"],
    )
    assert result.exit_code == 0, result.output
    # None is passed through; post_signed drops it before signing.
    assert captured["fields"]["deadline_height"] is None


class _LockClient:
    """Stand-in answering /rpc/transactions with a deadline-carrying lock."""

    def __init__(self, base_url=None, timeout=None):
        pass

    def get_json(self, path, params=None):
        assert path == "/rpc/transactions"
        tx_type = (params or {}).get("transaction_type")
        if tx_type == "BOUNTY_LOCK":
            return [
                {
                    "tx_hash": "0x" + "cd" * 32,
                    "type": tx_type,
                    "block_height": 99,
                    "payload": {"bounty_id": "bounty-hit", "deadline_height": 777},
                }
            ]
        return []


def test_status_surfaces_deadline_height(monkeypatch):
    monkeypatch.setattr(bounty_mod, "AITBCHTTPClient", _LockClient)
    runner = CliRunner()
    result = runner.invoke(
        bounty_mod.bounty,
        obj={"output_format": "json"},
        args=["status", "--bounty-id", "bounty-hit", "--rpc-url", "http://127.0.0.1:8202", "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["deadline_height"] == 777
