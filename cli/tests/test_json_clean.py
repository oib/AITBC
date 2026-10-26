"""CLI-JSON-CLEAN-1: under --output json, stdout must parse as JSON."""

import json
from click.testing import CliRunner

import aitbc_cli.commands.transactions as tx


class _C:
    def __init__(self, **kw):
        pass

    def get(self, path, **kw):
        return {"transactions": [], "ok": True}


def test_pending_json_clean(monkeypatch):
    monkeypatch.setattr(tx, "AITBCHTTPClient", _C)
    monkeypatch.setattr(tx, "_resolve_transaction_rpc_url", lambda x: "http://x")
    r = CliRunner().invoke(tx.pending, obj={"output_format": "json"})
    assert r.exit_code == 0
    json.loads(r.output)


def test_pending_table_keeps_lines(monkeypatch):
    monkeypatch.setattr(tx, "AITBCHTTPClient", _C)
    monkeypatch.setattr(tx, "_resolve_transaction_rpc_url", lambda x: "http://x")
    r = CliRunner().invoke(tx.pending, obj={"output_format": "table"})
    assert r.exit_code == 0
